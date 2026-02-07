#!/usr/bin/env python3
"""
Viability Cutoff Backtest

Tests the 4-factor viability model combined with FAI trading algorithm
to find the optimal viability score cutoff.

4-Factor Viability Model:
- FAI (40%) - Flow Acceleration Index
- Emission Share (25%) - Fundamental value accrual
- TAO Reserve (20%) - Liquidity for safe entry/exit
- Max Drawdown 30D (15%) - Risk control (inverted)

Hard Failure Gates:
- Age < 14 days
- Holders < 50
- Owner take > 18%
- Startup mode = true
- Severe outflow (7d flow < -50% reserve)

Goal: Find single cutoff score that maximizes risk-adjusted returns.
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import numpy as np

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tao_treasury")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# =============================================================================
# VIABILITY MODEL CONFIGURATION
# =============================================================================

VIABILITY_WEIGHTS = {
    "fai": 0.40,
    "emission_share": 0.25,
    "tao_reserve": 0.20,
    "max_drawdown_30d": 0.15,  # Inverted - lower is better
}

# Hard failure thresholds
HARD_FAILURES = {
    "min_age_days": 14,
    "min_holders": 50,
    "max_owner_take": 0.18,
    "max_negative_flow_ratio": 0.50,  # 7d flow < -50% of reserve
}

# Trading parameters (from momentum research)
HOLDING_PERIOD_DAYS = 14
FAI_QUINTILE_MULTIPLIERS = {
    1: 0.2,   # Q1: Lowest FAI
    2: 0.5,
    3: 1.0,
    4: 1.5,
    5: 2.5,   # Q5: Highest FAI
}


# =============================================================================
# DATA LOADING
# =============================================================================

async def load_all_data():
    """Load subnet snapshots and enriched data."""
    async with async_session() as db:
        # Get all subnet snapshots with required fields
        query = text("""
        SELECT
            ss.netuid,
            ss.timestamp::date as snap_date,
            ss.alpha_price_tao,
            s.name,
            s.age_days,
            s.holder_count,
            s.owner_take,
            s.startup_mode,
            s.emission_share,
            s.pool_tao_reserve,
            s.taoflow_1d,
            s.taoflow_7d
        FROM subnet_snapshots ss
        JOIN subnets s ON ss.netuid = s.netuid
        WHERE ss.alpha_price_tao IS NOT NULL
          AND ss.alpha_price_tao > 0
          AND ss.netuid != 0
        ORDER BY ss.timestamp ASC
        """)

        result = await db.execute(query)
        rows = result.fetchall()

        if not rows:
            print("No snapshot data found")
            return None

        # Convert to list of dicts
        data = []
        for row in rows:
            data.append({
                'netuid': row[0],
                'date': row[1],
                'alpha_price_tao': float(row[2]) if row[2] else 0,
                'name': row[3] or f"SN{row[0]}",
                'age_days': int(row[4]) if row[4] else 0,
                'holder_count': int(row[5]) if row[5] else 0,
                'owner_take': float(row[6]) if row[6] else 0,
                'startup_mode': bool(row[7]) if row[7] is not None else False,
                'emission_share': float(row[8]) if row[8] else 0,
                'pool_tao_reserve': float(row[9]) if row[9] else 0,
                'taoflow_1d': float(row[10]) if row[10] else 0,
                'taoflow_7d': float(row[11]) if row[11] else 0,
            })

        print(f"Loaded {len(data)} snapshots")

        # Get unique dates and subnets
        dates = sorted(set(d['date'] for d in data))
        netuids = set(d['netuid'] for d in data)
        print(f"Date range: {dates[0]} to {dates[-1]}")
        print(f"Unique subnets: {len(netuids)}")

        return data


# =============================================================================
# VIABILITY CALCULATIONS
# =============================================================================

def calculate_fai(flow_1d: float, flow_7d: float) -> float:
    """Calculate Flow Acceleration Index."""
    if flow_7d == 0:
        return 1.0  # Neutral if no 7d flow
    avg_daily_7d = flow_7d / 7
    if avg_daily_7d == 0:
        return 1.0
    return flow_1d / avg_daily_7d


def compute_max_drawdown(prices: list) -> float:
    """Compute max drawdown from a price list."""
    if len(prices) < 2:
        return 0.0

    peak = prices[0]
    max_dd = 0.0

    for price in prices:
        if price > peak:
            peak = price
        if peak > 0:
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd

    return max_dd


def check_hard_failures(row: dict, drawdown_30d: float) -> list:
    """Check hard failure conditions. Returns list of failure reasons."""
    failures = []

    # Age check
    if row['age_days'] < HARD_FAILURES['min_age_days']:
        failures.append(f"Age {row['age_days']}d < {HARD_FAILURES['min_age_days']}d")

    # Holder count
    if row['holder_count'] < HARD_FAILURES['min_holders']:
        failures.append(f"Holders {row['holder_count']} < {HARD_FAILURES['min_holders']}")

    # Owner take
    if row['owner_take'] > HARD_FAILURES['max_owner_take']:
        failures.append(f"Owner take {row['owner_take']:.1%} > {HARD_FAILURES['max_owner_take']:.0%}")

    # Startup mode
    if row['startup_mode'] is True:
        failures.append("Startup mode")

    # Severe outflow
    if row['pool_tao_reserve'] > 0:
        flow_ratio = row['taoflow_7d'] / row['pool_tao_reserve']
        if flow_ratio < -HARD_FAILURES['max_negative_flow_ratio']:
            failures.append(f"Severe outflow {flow_ratio:.1%}")

    return failures


def percentile_rank(values: list, target: float) -> float:
    """Compute percentile rank (0-100) of target within values."""
    if len(values) <= 1:
        return 50.0
    sorted_vals = sorted(values)
    rank = sum(1 for v in sorted_vals if v < target)
    return (rank / (len(sorted_vals) - 1)) * 100.0


def percentile_rank_inverted(values: list, target: float) -> float:
    """Inverted percentile: lower values get higher percentile."""
    if len(values) <= 1:
        return 50.0
    # For inverted, we want lower values to have higher percentile
    sorted_vals = sorted(values, reverse=True)
    rank = sum(1 for v in sorted_vals if v > target)
    return (rank / (len(sorted_vals) - 1)) * 100.0


def compute_viability_score(
    fai: float,
    emission_share: float,
    tao_reserve: float,
    drawdown_30d: float,
    all_fai: list,
    all_emission: list,
    all_reserve: list,
    all_drawdown: list,
) -> tuple:
    """
    Compute viability score (0-100) based on 4-factor model.
    Returns (score, factor_breakdown).
    """
    # Compute percentiles
    fai_pctile = percentile_rank(all_fai, fai)
    emission_pctile = percentile_rank(all_emission, emission_share)
    reserve_pctile = percentile_rank(all_reserve, tao_reserve)
    drawdown_pctile = percentile_rank_inverted(all_drawdown, drawdown_30d)

    # Weighted composite
    score = (
        fai_pctile * VIABILITY_WEIGHTS['fai'] +
        emission_pctile * VIABILITY_WEIGHTS['emission_share'] +
        reserve_pctile * VIABILITY_WEIGHTS['tao_reserve'] +
        drawdown_pctile * VIABILITY_WEIGHTS['max_drawdown_30d']
    )

    factors = {
        'fai_raw': fai,
        'fai_pctile': fai_pctile,
        'emission_pctile': emission_pctile,
        'reserve_pctile': reserve_pctile,
        'drawdown_pctile': drawdown_pctile,
    }

    return score, factors


# =============================================================================
# BACKTEST ENGINE
# =============================================================================

def get_fai_quintile(fai: float, all_fai: list) -> int:
    """Get FAI quintile (1-5) for position sizing."""
    if len(all_fai) < 5:
        return 3  # Default to middle quintile

    sorted_fai = sorted(all_fai)
    n = len(sorted_fai)
    quintiles = [
        sorted_fai[int(n * 0.2)],
        sorted_fai[int(n * 0.4)],
        sorted_fai[int(n * 0.6)],
        sorted_fai[int(n * 0.8)],
    ]

    if fai <= quintiles[0]:
        return 1
    elif fai <= quintiles[1]:
        return 2
    elif fai <= quintiles[2]:
        return 3
    elif fai <= quintiles[3]:
        return 4
    else:
        return 5


async def run_backtest(data: list, viability_cutoff: float) -> dict:
    """
    Run backtest with given viability cutoff.

    Strategy:
    1. Filter subnets by hard failures
    2. Filter by viability score >= cutoff
    3. Apply FAI quintile-based allocation
    4. Hold for 14 days, measure returns
    """

    # Index data by date and netuid
    by_date = defaultdict(list)
    for row in data:
        by_date[row['date']].append(row)

    # Also build price history by netuid for drawdown calc
    prices_by_netuid = defaultdict(list)
    for row in sorted(data, key=lambda x: x['date']):
        prices_by_netuid[row['netuid']].append({
            'date': row['date'],
            'price': row['alpha_price_tao']
        })

    # Get unique dates for weekly rebalancing
    unique_dates = sorted(by_date.keys())

    # Weekly rebalance dates (every 7 days)
    rebalance_dates = unique_dates[::7]

    trades = []

    for rebal_date in rebalance_dates[:-3]:  # Leave room for holding period
        date_rows = by_date[rebal_date]

        if len(date_rows) < 10:
            continue

        # Calculate FAI and 30d drawdown for all subnets
        subnet_data = []
        for row in date_rows:
            netuid = row['netuid']

            # Calculate FAI
            fai = calculate_fai(row['taoflow_1d'], row['taoflow_7d'])

            # Calculate 30d drawdown
            price_history = prices_by_netuid[netuid]
            recent_prices = [
                p['price'] for p in price_history
                if p['date'] <= rebal_date and p['date'] >= rebal_date - timedelta(days=30)
            ]
            drawdown_30d = compute_max_drawdown(recent_prices) if recent_prices else 0

            # Check hard failures
            hard_failures = check_hard_failures(row, drawdown_30d)

            if len(hard_failures) == 0:
                subnet_data.append({
                    **row,
                    'fai': fai,
                    'drawdown_30d': drawdown_30d,
                })

        if len(subnet_data) < 5:
            continue

        # Compute viability scores
        all_fai = [s['fai'] for s in subnet_data]
        all_emission = [s['emission_share'] for s in subnet_data]
        all_reserve = [s['pool_tao_reserve'] for s in subnet_data]
        all_drawdown = [s['drawdown_30d'] for s in subnet_data]

        for subnet in subnet_data:
            score, _ = compute_viability_score(
                subnet['fai'], subnet['emission_share'], subnet['pool_tao_reserve'],
                subnet['drawdown_30d'], all_fai, all_emission, all_reserve, all_drawdown
            )
            subnet['viability_score'] = score

        # Filter by viability cutoff
        viable_subnets = [s for s in subnet_data if s['viability_score'] >= viability_cutoff]

        if len(viable_subnets) < 3:
            continue

        # Assign FAI quintiles for position sizing
        viable_fai = [s['fai'] for s in viable_subnets]

        for subnet in viable_subnets:
            subnet['fai_quintile'] = get_fai_quintile(subnet['fai'], viable_fai)

        # Calculate forward returns (14 days)
        exit_date = rebal_date + timedelta(days=HOLDING_PERIOD_DAYS)

        for subnet in viable_subnets:
            netuid = subnet['netuid']
            entry_price = subnet['alpha_price_tao']

            # Find exit price
            price_history = prices_by_netuid[netuid]
            exit_prices = [p['price'] for p in price_history if p['date'] >= exit_date]

            if not exit_prices:
                continue

            exit_price = exit_prices[0]
            raw_return = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

            # Weight by FAI quintile
            quintile = subnet['fai_quintile']
            weight = FAI_QUINTILE_MULTIPLIERS[quintile]
            weighted_return = raw_return * weight

            trades.append({
                'entry_date': rebal_date,
                'exit_date': exit_date,
                'netuid': netuid,
                'name': subnet['name'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'raw_return': raw_return,
                'fai': subnet['fai'],
                'fai_quintile': quintile,
                'weight': weight,
                'weighted_return': weighted_return,
                'viability_score': subnet['viability_score'],
            })

    if not trades:
        return {
            'cutoff': viability_cutoff,
            'total_trades': 0,
            'avg_return': 0,
            'win_rate': 0,
            'sharpe': 0,
        }

    # Compute metrics
    weighted_returns = [t['weighted_return'] for t in trades]
    viability_scores = [t['viability_score'] for t in trades]

    avg_return = statistics.mean(weighted_returns)
    win_rate = sum(1 for r in weighted_returns if r > 0) / len(weighted_returns)
    std_return = statistics.stdev(weighted_returns) if len(weighted_returns) > 1 else 0.01
    sharpe = avg_return / std_return * (26 ** 0.5) if std_return > 0 else 0  # Annualized

    unique_subnets = len(set(t['netuid'] for t in trades))

    return {
        'cutoff': viability_cutoff,
        'total_trades': len(trades),
        'unique_subnets': unique_subnets,
        'avg_return': avg_return,
        'median_return': statistics.median(weighted_returns),
        'win_rate': win_rate,
        'std_return': std_return,
        'sharpe': sharpe,
        'avg_viability': statistics.mean(viability_scores),
        'min_viability': min(viability_scores),
        'trades': trades,
    }


async def main():
    print("=" * 70)
    print("VIABILITY CUTOFF BACKTEST")
    print("=" * 70)
    print()
    print("4-Factor Viability Model:")
    for factor, weight in VIABILITY_WEIGHTS.items():
        print(f"  {factor}: {weight:.0%}")
    print()
    print("Hard Failure Gates:")
    for gate, threshold in HARD_FAILURES.items():
        print(f"  {gate}: {threshold}")
    print()

    # Load data
    data = await load_all_data()
    if data is None:
        return

    print()
    print("=" * 70)
    print("TESTING VIABILITY CUTOFFS")
    print("=" * 70)

    # Test different cutoffs
    cutoffs = [20, 30, 40, 50, 60, 70, 80]
    results = []

    for cutoff in cutoffs:
        print(f"\nTesting cutoff: {cutoff}...")
        result = await run_backtest(data, cutoff)
        results.append(result)

        print(f"  Trades: {result['total_trades']}")
        print(f"  Avg Return: {result['avg_return']:.2%}")
        print(f"  Win Rate: {result['win_rate']:.1%}")
        print(f"  Sharpe: {result['sharpe']:.2f}")

    # Summary table
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Cutoff':>8} {'Trades':>8} {'Subnets':>8} {'Avg Ret':>10} {'Win Rate':>10} {'Sharpe':>8} {'Avg Viab':>10}")
    print("-" * 70)

    for r in results:
        print(f"{r['cutoff']:>8} {r['total_trades']:>8} {r.get('unique_subnets', 0):>8} "
              f"{r['avg_return']:>9.2%} {r['win_rate']:>9.1%} {r['sharpe']:>8.2f} "
              f"{r.get('avg_viability', 0):>9.1f}")

    # Find optimal cutoff
    print()
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    # Filter to results with enough trades
    valid_results = [r for r in results if r['total_trades'] >= 20]

    if valid_results:
        # Best by Sharpe
        best_sharpe = max(valid_results, key=lambda x: x['sharpe'])
        print(f"\nBest Sharpe Ratio: Cutoff {best_sharpe['cutoff']} (Sharpe: {best_sharpe['sharpe']:.2f})")

        # Best by Win Rate
        best_winrate = max(valid_results, key=lambda x: x['win_rate'])
        print(f"Best Win Rate: Cutoff {best_winrate['cutoff']} (Win Rate: {best_winrate['win_rate']:.1%})")

        # Best by Average Return
        best_return = max(valid_results, key=lambda x: x['avg_return'])
        print(f"Best Avg Return: Cutoff {best_return['cutoff']} (Return: {best_return['avg_return']:.2%})")

    # Trade-off analysis
    print()
    print("Trade-off Analysis (Return vs Universe Size):")
    print("-" * 50)

    base_trades = results[0]['total_trades'] if results[0]['total_trades'] > 0 else 1

    for r in results:
        trade_pct = r['total_trades'] / base_trades * 100 if base_trades > 0 else 0
        print(f"  Cutoff {r['cutoff']}: {trade_pct:.0f}% of trades, {r['avg_return']:.2%} return")

    # Quintile breakdown for best cutoff
    if valid_results:
        best = best_sharpe
        print()
        print("=" * 70)
        print(f"DETAILED ANALYSIS: CUTOFF {best['cutoff']}")
        print("=" * 70)

        if best['total_trades'] > 0:
            trades = best['trades']

            print("\nBy FAI Quintile:")
            print("-" * 50)

            for q in range(1, 6):
                q_trades = [t for t in trades if t['fai_quintile'] == q]
                if len(q_trades) > 0:
                    q_returns = [t['weighted_return'] for t in q_trades]
                    q_avg = statistics.mean(q_returns)
                    q_winrate = sum(1 for r in q_returns if r > 0) / len(q_returns)
                    print(f"  Q{q}: {len(q_trades)} trades, "
                          f"Avg Return: {q_avg:.2%}, "
                          f"Win Rate: {q_winrate:.1%}")

            print("\nViability Score Distribution of Trades:")
            print("-" * 50)
            viab_bins = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 100)]
            for low, high in viab_bins:
                bin_trades = [t for t in trades if low <= t['viability_score'] < high]
                if len(bin_trades) > 0:
                    bin_returns = [t['weighted_return'] for t in bin_trades]
                    bin_avg = statistics.mean(bin_returns)
                    print(f"  {low}-{high}: {len(bin_trades)} trades, "
                          f"Avg Return: {bin_avg:.2%}")

    # Recommendation
    print()
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)

    if valid_results:
        # Find the cutoff with best risk-adjusted return
        recommended = max(valid_results, key=lambda x: x['sharpe'])
        print(f"\nRecommended Viability Cutoff: {recommended['cutoff']}")
        print(f"  - Sharpe Ratio: {recommended['sharpe']:.2f}")
        print(f"  - Win Rate: {recommended['win_rate']:.1%}")
        print(f"  - Average Return: {recommended['avg_return']:.2%}")
        print(f"  - Trade Universe: {recommended['total_trades']} opportunities")
        print()
        print("Subnets with viability score >= this cutoff should be considered 'viable'.")
        print("Below this threshold = 'not viable' (excluded from trading).")
    else:
        print("\nInsufficient data for confident recommendation.")
        print("Consider relaxing cutoff thresholds or gathering more historical data.")


if __name__ == "__main__":
    asyncio.run(main())
