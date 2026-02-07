#!/usr/bin/env python3
"""
Portfolio Momentum Allocation Backtest

Tests dynamic portfolio allocation strategies based on flow momentum lifecycle:
- Allocations increase as momentum builds (Days 1→7)
- Allocations peak around Day 7-14
- Allocations decrease after Day 14 (mean reversion zone)

Compares multiple allocation curves against equal-weight benchmark.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from scipy import stats
from sqlalchemy import select

from app.core.database import get_db_context
from app.models.subnet import SubnetSnapshot


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DailyData:
    netuid: int
    date: datetime
    price: float
    pool_reserve: float


@dataclass
class SubnetSignalState:
    """Tracks momentum signal state for a subnet."""
    netuid: int
    in_signal: bool = False  # Is FAI in top quintile?
    days_in_signal: int = 0
    fai_value: float = 0.0
    fai_quintile: int = 0  # 1-5, where 5 is top


@dataclass
class PortfolioState:
    """Daily portfolio snapshot."""
    date: datetime
    total_value: float
    allocations: Dict[int, float]  # netuid -> allocation weight
    daily_return: float
    cumulative_return: float


# =============================================================================
# ALLOCATION CURVES
# =============================================================================

def allocation_curve_equal_weight(days_in_signal: int, n_subnets: int) -> float:
    """Equal weight regardless of signal state."""
    return 1.0 / n_subnets


def allocation_curve_linear_buildup(days_in_signal: int, n_subnets: int) -> float:
    """
    Linear increase from Day 1-14, then flat.
    Base: equal weight. Signal multiplier: 1x at day 0, 3x at day 14+
    """
    base = 1.0 / n_subnets
    if days_in_signal <= 0:
        return base * 0.5  # Below average if not in signal
    elif days_in_signal <= 14:
        multiplier = 1.0 + (days_in_signal / 14) * 2.0  # 1x to 3x
        return base * multiplier
    else:
        return base * 3.0  # Stay at 3x after day 14


def allocation_curve_peak_at_14(days_in_signal: int, n_subnets: int) -> float:
    """
    Build up to Day 14, then decline (matching our alpha window findings).
    """
    base = 1.0 / n_subnets
    if days_in_signal <= 0:
        return base * 0.3  # Underweight if not in signal
    elif days_in_signal <= 7:
        # Days 1-7: Build from 1x to 2x
        multiplier = 1.0 + (days_in_signal / 7) * 1.0
        return base * multiplier
    elif days_in_signal <= 14:
        # Days 7-14: Build from 2x to 4x (peak)
        multiplier = 2.0 + ((days_in_signal - 7) / 7) * 2.0
        return base * multiplier
    elif days_in_signal <= 21:
        # Days 14-21: Decline from 4x to 2x
        multiplier = 4.0 - ((days_in_signal - 14) / 7) * 2.0
        return base * multiplier
    else:
        # Day 21+: Stay at 1x (back to neutral)
        return base * 1.0


def allocation_curve_aggressive_early(days_in_signal: int, n_subnets: int) -> float:
    """
    Aggressive allocation early (Days 1-7), quick exit after Day 14.
    """
    base = 1.0 / n_subnets
    if days_in_signal <= 0:
        return base * 0.2  # Heavily underweight if not in signal
    elif days_in_signal <= 3:
        # Days 1-3: Rapid buildup to 3x
        multiplier = 1.0 + (days_in_signal / 3) * 2.0
        return base * multiplier
    elif days_in_signal <= 7:
        # Days 3-7: Peak at 4x
        multiplier = 3.0 + ((days_in_signal - 3) / 4) * 1.0
        return base * multiplier
    elif days_in_signal <= 14:
        # Days 7-14: Maintain at 4x
        return base * 4.0
    elif days_in_signal <= 21:
        # Days 14-21: Rapid decline to 0.5x
        multiplier = 4.0 - ((days_in_signal - 14) / 7) * 3.5
        return base * multiplier
    else:
        # Day 21+: Minimal allocation
        return base * 0.5


def allocation_curve_conservative(days_in_signal: int, n_subnets: int) -> float:
    """
    Conservative: Small overweight for signal, quick to exit.
    """
    base = 1.0 / n_subnets
    if days_in_signal <= 0:
        return base * 0.7
    elif days_in_signal <= 14:
        # Days 1-14: Moderate overweight (1.5x)
        return base * 1.5
    else:
        # Day 14+: Back to underweight
        return base * 0.7


def allocation_curve_momentum_quintile(days_in_signal: int, fai_quintile: int, n_subnets: int) -> float:
    """
    Allocation based on both days in signal AND current FAI quintile.
    """
    base = 1.0 / n_subnets

    # Base multiplier by quintile
    quintile_mult = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}
    q_mult = quintile_mult.get(fai_quintile, 1.0)

    # Days modifier
    if days_in_signal <= 0:
        days_mult = 0.5
    elif days_in_signal <= 7:
        days_mult = 1.0 + (days_in_signal / 7) * 0.5  # 1x to 1.5x
    elif days_in_signal <= 14:
        days_mult = 1.5  # Peak period
    elif days_in_signal <= 21:
        days_mult = 1.5 - ((days_in_signal - 14) / 7) * 0.5  # 1.5x to 1x
    else:
        days_mult = 0.8

    return base * q_mult * days_mult


# =============================================================================
# DATA LOADING & METRICS
# =============================================================================

async def load_data() -> Dict[int, List[DailyData]]:
    """Load all historical data."""
    async with get_db_context() as db:
        stmt = (
            select(SubnetSnapshot)
            .where(SubnetSnapshot.alpha_price_tao > 0)
            .where(SubnetSnapshot.pool_tao_reserve > 0)
            .order_by(SubnetSnapshot.netuid, SubnetSnapshot.timestamp)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        by_subnet: Dict[int, List[DailyData]] = defaultdict(list)
        for row in rows:
            data = DailyData(
                netuid=row.netuid,
                date=row.timestamp.replace(tzinfo=None),
                price=float(row.alpha_price_tao),
                pool_reserve=float(row.pool_tao_reserve),
            )
            by_subnet[row.netuid].append(data)

        return dict(by_subnet)


def compute_fai(snapshots: List[DailyData], idx: int) -> Optional[float]:
    """
    Compute Flow Acceleration Index at a given index.
    FAI = flow_1d / (flow_7d / 7)
    """
    if idx < 7:
        return None

    current = snapshots[idx]
    prev_1d = snapshots[idx - 1]
    prev_7d = snapshots[idx - 7]

    flow_1d = current.pool_reserve - prev_1d.pool_reserve
    flow_7d = current.pool_reserve - prev_7d.pool_reserve

    if flow_7d == 0:
        return None

    avg_daily_7d = flow_7d / 7
    if avg_daily_7d == 0:
        return None

    return flow_1d / avg_daily_7d


def get_fai_quintile(fai: float, all_fais: List[float]) -> int:
    """Determine which quintile a FAI value falls into."""
    if not all_fais or fai is None:
        return 3  # Middle quintile as default

    percentiles = [np.percentile(all_fais, p) for p in [20, 40, 60, 80]]

    if fai < percentiles[0]:
        return 1
    elif fai < percentiles[1]:
        return 2
    elif fai < percentiles[2]:
        return 3
    elif fai < percentiles[3]:
        return 4
    else:
        return 5


# =============================================================================
# PORTFOLIO SIMULATION
# =============================================================================

async def run_portfolio_simulation(
    allocation_curve,
    curve_name: str,
    all_data: Dict[int, List[DailyData]],
    viable_netuids: List[int],
    start_date: datetime,
    end_date: datetime,
) -> Dict:
    """
    Run portfolio simulation with given allocation curve.
    """
    n_subnets = len(viable_netuids)

    # Build date-indexed data for each subnet
    subnet_by_date: Dict[int, Dict[datetime, DailyData]] = {}
    for netuid in viable_netuids:
        if netuid in all_data:
            subnet_by_date[netuid] = {d.date.date(): d for d in all_data[netuid]}

    # Get all unique dates
    all_dates = set()
    for netuid in viable_netuids:
        if netuid in subnet_by_date:
            all_dates.update(subnet_by_date[netuid].keys())

    dates = sorted([d for d in all_dates if start_date.date() <= d <= end_date.date()])

    if len(dates) < 30:
        return {'error': 'Insufficient dates'}

    # Initialize signal states
    signal_states: Dict[int, SubnetSignalState] = {
        netuid: SubnetSignalState(netuid=netuid) for netuid in viable_netuids
    }

    # Track portfolio
    portfolio_value = 1.0  # Start with 1.0 (100%)
    portfolio_history = []

    # For FAI quintile calculation, we need rolling FAI values
    all_fai_values = []

    for i, date in enumerate(dates):
        if i < 7:  # Need history for FAI calculation
            continue

        # Calculate FAI for all subnets on this date
        daily_fais = {}
        for netuid in viable_netuids:
            if netuid not in all_data:
                continue

            snapshots = all_data[netuid]
            # Find index for this date
            date_to_idx = {s.date.date(): j for j, s in enumerate(snapshots)}
            if date not in date_to_idx:
                continue

            idx = date_to_idx[date]
            fai = compute_fai(snapshots, idx)
            if fai is not None:
                daily_fais[netuid] = fai
                all_fai_values.append(fai)

        # Determine top quintile threshold
        if daily_fais:
            fai_values = list(daily_fais.values())
            top_quintile_threshold = np.percentile(fai_values, 80) if len(fai_values) >= 5 else np.median(fai_values)

            # Update signal states
            for netuid in viable_netuids:
                state = signal_states[netuid]
                fai = daily_fais.get(netuid)

                if fai is not None:
                    state.fai_value = fai
                    state.fai_quintile = get_fai_quintile(fai, fai_values)

                    # Check if in top quintile
                    if fai >= top_quintile_threshold:
                        if state.in_signal:
                            state.days_in_signal += 1
                        else:
                            state.in_signal = True
                            state.days_in_signal = 1
                    else:
                        state.in_signal = False
                        state.days_in_signal = 0

        # Calculate allocations based on signal states
        raw_allocations = {}
        for netuid in viable_netuids:
            state = signal_states[netuid]

            if curve_name == 'quintile_based':
                alloc = allocation_curve_momentum_quintile(
                    state.days_in_signal, state.fai_quintile, n_subnets
                )
            else:
                alloc = allocation_curve(state.days_in_signal, n_subnets)

            raw_allocations[netuid] = alloc

        # Normalize allocations to sum to 1.0
        total_alloc = sum(raw_allocations.values())
        allocations = {k: v / total_alloc for k, v in raw_allocations.items()}

        # Calculate daily return
        daily_return = 0.0
        returns_counted = 0

        for netuid in viable_netuids:
            if netuid not in all_data:
                continue

            snapshots = all_data[netuid]
            date_to_idx = {s.date.date(): j for j, s in enumerate(snapshots)}

            if date not in date_to_idx:
                continue

            idx = date_to_idx[date]
            if idx == 0:
                continue

            prev_price = snapshots[idx - 1].price
            curr_price = snapshots[idx].price

            if prev_price > 0:
                subnet_return = (curr_price - prev_price) / prev_price
                weighted_return = subnet_return * allocations.get(netuid, 0)
                daily_return += weighted_return
                returns_counted += 1

        # Update portfolio value
        portfolio_value *= (1 + daily_return)

        portfolio_history.append(PortfolioState(
            date=datetime.combine(date, datetime.min.time()),
            total_value=portfolio_value,
            allocations=allocations.copy(),
            daily_return=daily_return,
            cumulative_return=portfolio_value - 1.0,
        ))

    # Calculate metrics
    if not portfolio_history:
        return {'error': 'No portfolio history generated'}

    daily_returns = [p.daily_return for p in portfolio_history]
    final_value = portfolio_history[-1].total_value
    total_return = final_value - 1.0

    # Annualized metrics
    n_days = len(daily_returns)
    annualized_return = (1 + total_return) ** (365 / n_days) - 1 if n_days > 0 else 0
    volatility = np.std(daily_returns) * np.sqrt(365) if daily_returns else 0
    sharpe = annualized_return / volatility if volatility > 0 else 0

    # Max drawdown
    peak = 1.0
    max_dd = 0.0
    for p in portfolio_history:
        if p.total_value > peak:
            peak = p.total_value
        dd = (peak - p.total_value) / peak
        if dd > max_dd:
            max_dd = dd

    # Win rate
    win_rate = np.mean(np.array(daily_returns) > 0) if daily_returns else 0

    return {
        'curve_name': curve_name,
        'n_subnets': n_subnets,
        'n_days': n_days,
        'final_value': float(final_value),
        'total_return': float(total_return),
        'annualized_return': float(annualized_return),
        'volatility': float(volatility),
        'sharpe_ratio': float(sharpe),
        'max_drawdown': float(max_dd),
        'win_rate': float(win_rate),
        'history': portfolio_history,
    }


# =============================================================================
# MAIN BACKTEST
# =============================================================================

async def run_portfolio_backtest():
    """Run comprehensive portfolio allocation backtest."""

    print("=" * 80)
    print("PORTFOLIO MOMENTUM ALLOCATION BACKTEST")
    print("=" * 80)
    print()

    # Load data
    print("Loading data...")
    all_data = await load_data()
    print(f"Loaded {len(all_data)} subnets")

    # Select "viable" subnets (for this test, use top 30 by data availability)
    # In production, this would come from viability scoring
    subnets_by_history = sorted(all_data.keys(), key=lambda x: len(all_data[x]), reverse=True)
    viable_netuids = subnets_by_history[:30]
    print(f"Using {len(viable_netuids)} viable subnets: {viable_netuids}")
    print()

    # Determine date range
    all_dates = []
    for netuid in viable_netuids:
        for snap in all_data[netuid]:
            all_dates.append(snap.date)

    start_date = min(all_dates) + timedelta(days=37)  # Need history for metrics
    end_date = max(all_dates) - timedelta(days=1)
    print(f"Backtest period: {start_date.date()} to {end_date.date()}")
    print()

    # Define allocation curves to test
    curves = [
        (allocation_curve_equal_weight, "equal_weight"),
        (allocation_curve_linear_buildup, "linear_buildup"),
        (allocation_curve_peak_at_14, "peak_at_14"),
        (allocation_curve_aggressive_early, "aggressive_early"),
        (allocation_curve_conservative, "conservative"),
        (allocation_curve_momentum_quintile, "quintile_based"),
    ]

    # Run simulations
    results = []
    for curve_func, curve_name in curves:
        print(f"Running simulation: {curve_name}...")
        result = await run_portfolio_simulation(
            curve_func, curve_name, all_data, viable_netuids, start_date, end_date
        )
        if 'error' not in result:
            results.append(result)
            print(f"  Total Return: {result['total_return']*100:+.2f}%")
            print(f"  Sharpe Ratio: {result['sharpe_ratio']:.2f}")
        else:
            print(f"  Error: {result['error']}")
        print()

    # ==========================================================================
    # RESULTS COMPARISON
    # ==========================================================================

    print("=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)
    print()

    print(f"{'Strategy':<20} {'Total Ret':>12} {'Ann. Ret':>12} {'Vol':>10} {'Sharpe':>8} {'MaxDD':>10} {'WinRate':>10}")
    print("-" * 92)

    # Sort by Sharpe ratio
    results.sort(key=lambda x: x['sharpe_ratio'], reverse=True)

    for r in results:
        print(f"{r['curve_name']:<20} "
              f"{r['total_return']*100:>+11.2f}% "
              f"{r['annualized_return']*100:>+11.2f}% "
              f"{r['volatility']*100:>9.2f}% "
              f"{r['sharpe_ratio']:>8.2f} "
              f"{r['max_drawdown']*100:>9.2f}% "
              f"{r['win_rate']*100:>9.1f}%")

    print()

    # ==========================================================================
    # DETAILED ANALYSIS OF BEST STRATEGY
    # ==========================================================================

    best = results[0]
    benchmark = next((r for r in results if r['curve_name'] == 'equal_weight'), None)

    print("=" * 80)
    print(f"BEST STRATEGY: {best['curve_name']}")
    print("=" * 80)
    print()

    print(f"Performance Metrics:")
    print(f"  Total Return: {best['total_return']*100:+.2f}%")
    print(f"  Annualized Return: {best['annualized_return']*100:+.2f}%")
    print(f"  Volatility: {best['volatility']*100:.2f}%")
    print(f"  Sharpe Ratio: {best['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown: {best['max_drawdown']*100:.2f}%")
    print(f"  Win Rate: {best['win_rate']*100:.1f}%")
    print()

    if benchmark:
        print("vs Equal Weight Benchmark:")
        print(f"  Return Improvement: {(best['total_return'] - benchmark['total_return'])*100:+.2f}%")
        print(f"  Sharpe Improvement: {best['sharpe_ratio'] - benchmark['sharpe_ratio']:+.2f}")
        print(f"  Max DD Improvement: {(benchmark['max_drawdown'] - best['max_drawdown'])*100:+.2f}%")
        print()

    # ==========================================================================
    # ALLOCATION DYNAMICS ANALYSIS
    # ==========================================================================

    print("=" * 80)
    print("ALLOCATION DYNAMICS ANALYSIS")
    print("=" * 80)
    print()

    # Analyze allocation concentration over time
    history = best['history']

    # Sample allocation snapshots
    sample_indices = [0, len(history)//4, len(history)//2, 3*len(history)//4, -1]

    print("Allocation Concentration Over Time:")
    print("-" * 60)

    for idx in sample_indices:
        if idx < 0:
            idx = len(history) + idx
        if idx >= len(history):
            continue

        snapshot = history[idx]
        allocs = sorted(snapshot.allocations.values(), reverse=True)

        top_5_weight = sum(allocs[:5]) if len(allocs) >= 5 else sum(allocs)
        top_10_weight = sum(allocs[:10]) if len(allocs) >= 10 else sum(allocs)
        max_weight = allocs[0] if allocs else 0
        min_weight = allocs[-1] if allocs else 0

        print(f"  {snapshot.date.date()}:")
        print(f"    Top 5 weight: {top_5_weight*100:.1f}%")
        print(f"    Top 10 weight: {top_10_weight*100:.1f}%")
        print(f"    Max single position: {max_weight*100:.1f}%")
        print(f"    Min single position: {min_weight*100:.1f}%")
        print()

    # ==========================================================================
    # RECOMMENDED ALLOCATION CURVE PARAMETERS
    # ==========================================================================

    print("=" * 80)
    print("RECOMMENDED ALLOCATION PARAMETERS")
    print("=" * 80)
    print()

    if best['curve_name'] == 'peak_at_14':
        print("Best Strategy: PEAK AT DAY 14")
        print()
        print("Allocation Curve:")
        print("  Days 0 (not in signal): 0.3x base weight")
        print("  Days 1-7:  Linear increase from 1.0x to 2.0x")
        print("  Days 7-14: Linear increase from 2.0x to 4.0x (PEAK)")
        print("  Days 14-21: Linear decrease from 4.0x to 2.0x")
        print("  Days 21+: 1.0x (back to neutral)")

    elif best['curve_name'] == 'aggressive_early':
        print("Best Strategy: AGGRESSIVE EARLY")
        print()
        print("Allocation Curve:")
        print("  Days 0 (not in signal): 0.2x base weight")
        print("  Days 1-3: Rapid buildup from 1.0x to 3.0x")
        print("  Days 3-7: Continue to 4.0x (PEAK)")
        print("  Days 7-14: Maintain at 4.0x")
        print("  Days 14-21: Rapid decline from 4.0x to 0.5x")
        print("  Days 21+: 0.5x (minimal allocation)")

    elif best['curve_name'] == 'quintile_based':
        print("Best Strategy: QUINTILE-BASED DYNAMIC")
        print()
        print("Allocation combines FAI quintile AND days in signal:")
        print("  Quintile multipliers: Q1=0.2x, Q2=0.5x, Q3=1.0x, Q4=1.5x, Q5=2.5x")
        print("  Days modifier:")
        print("    Days 0: 0.5x")
        print("    Days 1-7: 1.0x to 1.5x")
        print("    Days 7-14: 1.5x (peak)")
        print("    Days 14-21: 1.5x to 1.0x")
        print("    Days 21+: 0.8x")

    print()
    print("=" * 80)
    print("IMPLEMENTATION NOTES")
    print("=" * 80)
    print()
    print("1. ENTRY SIGNAL: FAI enters top quintile (daily flow > 1.5x weekly average)")
    print("2. POSITION SIZING: Use allocation curve based on days since entry")
    print("3. REBALANCING: Daily rebalancing recommended (TaoStats SDK supports batch)")
    print("4. EXIT SIGNAL: Either FAI drops below top quintile OR days > 21")
    print("5. RISK MANAGEMENT: Cap max single position at 10% regardless of curve")
    print()


if __name__ == "__main__":
    asyncio.run(run_portfolio_backtest())
