#!/usr/bin/env python3
"""
Deep Dive: Flow Momentum Analysis

This analysis explores:
1. Multiple momentum definitions (1D, 3D, 7D flow changes, cross-timeframe ratios)
2. Extended return horizons (1D through 30D)
3. Event study: Track cumulative returns after momentum signals
4. Peak timing: When does price typically peak after positive momentum?
5. Decay analysis: At what point does mean reversion kick in?
"""

import asyncio
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict

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
class MomentumSignal:
    """Represents a momentum signal event for event study analysis."""
    netuid: int
    signal_date: datetime
    signal_type: str  # e.g., "flow_7d_momentum_positive"
    signal_value: float

    # Forward returns from signal date
    returns: Dict[int, Optional[float]]  # day offset -> return


# =============================================================================
# DATA LOADING
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


# =============================================================================
# MOMENTUM CALCULATIONS
# =============================================================================

def compute_all_metrics(snapshots: List[DailyData]) -> List[Dict]:
    """Compute comprehensive metrics for each day."""
    if len(snapshots) < 60:
        return []

    by_date = {s.date.date(): s for s in snapshots}
    dates = sorted(by_date.keys())

    results = []

    for i, date in enumerate(dates):
        if i < 37:  # Need lookback for 30d flow + 7d momentum
            continue

        snap = by_date[date]

        # Helper to get flow over N days ending at index
        def get_flow(idx: int, days: int) -> float:
            if idx >= days:
                return by_date[dates[idx]].pool_reserve - by_date[dates[idx - days]].pool_reserve
            return 0.0

        # Raw flows
        flow_1d = get_flow(i, 1)
        flow_3d = get_flow(i, 3)
        flow_7d = get_flow(i, 7)
        flow_14d = get_flow(i, 14)
        flow_30d = get_flow(i, 30)

        # Flow momentum (change in flow over time)
        # e.g., flow_7d_momentum = flow_7d_today - flow_7d_7days_ago
        flow_1d_momentum_1d = flow_1d - get_flow(i-1, 1) if i > 1 else 0
        flow_1d_momentum_3d = flow_1d - get_flow(i-3, 1) if i > 3 else 0
        flow_1d_momentum_7d = flow_1d - get_flow(i-7, 1) if i > 7 else 0

        flow_3d_momentum_3d = flow_3d - get_flow(i-3, 3) if i > 6 else 0
        flow_3d_momentum_7d = flow_3d - get_flow(i-7, 3) if i > 10 else 0

        flow_7d_momentum_3d = flow_7d - get_flow(i-3, 7) if i > 10 else 0
        flow_7d_momentum_7d = flow_7d - get_flow(i-7, 7) if i > 14 else 0
        flow_7d_momentum_14d = flow_7d - get_flow(i-14, 7) if i > 21 else 0

        # Cross-timeframe ratios (short-term vs long-term flow)
        flow_1d_to_7d_ratio = flow_1d / (flow_7d / 7) if flow_7d != 0 else 0  # 1d flow vs avg daily 7d flow
        flow_3d_to_7d_ratio = (flow_3d / 3) / (flow_7d / 7) if flow_7d != 0 else 0
        flow_7d_to_30d_ratio = (flow_7d / 7) / (flow_30d / 30) if flow_30d != 0 else 0

        # Acceleration (second derivative)
        prev_momentum = get_flow(i-7, 7) - get_flow(i-14, 7) if i > 21 else 0
        flow_7d_acceleration = flow_7d_momentum_7d - prev_momentum

        # Forward returns at multiple horizons
        def get_return(days_forward: int) -> Optional[float]:
            if i + days_forward < len(dates):
                future_price = by_date[dates[i + days_forward]].price
                if snap.price > 0:
                    return (future_price - snap.price) / snap.price
            return None

        results.append({
            'netuid': snap.netuid,
            'date': date,
            'price': snap.price,
            'pool_reserve': snap.pool_reserve,

            # Raw flows
            'flow_1d': flow_1d,
            'flow_3d': flow_3d,
            'flow_7d': flow_7d,
            'flow_14d': flow_14d,
            'flow_30d': flow_30d,

            # Flow momentum (various lookbacks)
            'flow_1d_mom_1d': flow_1d_momentum_1d,
            'flow_1d_mom_3d': flow_1d_momentum_3d,
            'flow_1d_mom_7d': flow_1d_momentum_7d,
            'flow_3d_mom_3d': flow_3d_momentum_3d,
            'flow_3d_mom_7d': flow_3d_momentum_7d,
            'flow_7d_mom_3d': flow_7d_momentum_3d,
            'flow_7d_mom_7d': flow_7d_momentum_7d,
            'flow_7d_mom_14d': flow_7d_momentum_14d,

            # Cross-timeframe
            'flow_1d_to_7d': flow_1d_to_7d_ratio,
            'flow_3d_to_7d': flow_3d_to_7d_ratio,
            'flow_7d_to_30d': flow_7d_to_30d_ratio,

            # Acceleration
            'flow_7d_accel': flow_7d_acceleration,

            # Forward returns
            'ret_1d': get_return(1),
            'ret_3d': get_return(3),
            'ret_7d': get_return(7),
            'ret_14d': get_return(14),
            'ret_21d': get_return(21),
            'ret_30d': get_return(30),
        })

    return results


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def analyze_metric_vs_returns(data: List[Dict], metric_key: str) -> Dict:
    """Analyze a single metric against all return horizons."""
    horizons = [1, 3, 7, 14, 21, 30]

    valid = [d for d in data if d.get(f'ret_30d') is not None]
    if len(valid) < 100:
        return None

    metrics = np.array([d[metric_key] for d in valid])

    # Filter out extreme outliers and NaN
    mask = np.isfinite(metrics) & (np.abs(metrics) < np.percentile(np.abs(metrics[np.isfinite(metrics)]), 99))
    valid = [d for d, m in zip(valid, mask) if m]
    metrics = np.array([d[metric_key] for d in valid])

    if len(valid) < 100:
        return None

    results = {'metric': metric_key, 'n': len(valid)}

    for horizon in horizons:
        returns = np.array([d[f'ret_{horizon}d'] for d in valid])
        returns = returns[np.isfinite(returns)]
        metrics_clean = metrics[:len(returns)]

        if len(returns) < 50:
            continue

        # Correlation
        corr, pval = stats.pearsonr(metrics_clean, returns)

        # Quintile analysis
        try:
            quintiles = np.percentile(metrics_clean, [0, 20, 40, 60, 80, 100])
            q_returns = []
            for q in range(5):
                if q == 4:
                    mask = (metrics_clean >= quintiles[q]) & (metrics_clean <= quintiles[q+1])
                else:
                    mask = (metrics_clean >= quintiles[q]) & (metrics_clean < quintiles[q+1])
                q_returns.append(float(np.mean(returns[mask])) if mask.sum() > 0 else 0)

            spread = q_returns[4] - q_returns[0]
            mono, _ = stats.spearmanr(range(5), q_returns)
        except:
            q_returns = [0]*5
            spread = 0
            mono = 0

        results[f'{horizon}d'] = {
            'corr': float(corr),
            'pval': float(pval),
            'spread': float(spread),
            'mono': float(mono) if not np.isnan(mono) else 0,
            'q_returns': q_returns,
        }

    return results


def event_study_momentum_crossover(data: List[Dict], momentum_key: str) -> Dict:
    """
    Event study: When momentum crosses from negative to positive,
    track cumulative returns over following 30 days.
    """
    # Sort by netuid and date
    by_subnet = defaultdict(list)
    for d in data:
        by_subnet[d['netuid']].append(d)

    for netuid in by_subnet:
        by_subnet[netuid].sort(key=lambda x: x['date'])

    # Find crossover events (momentum goes from negative to positive)
    events = []

    for netuid, subnet_data in by_subnet.items():
        for i in range(1, len(subnet_data)):
            prev = subnet_data[i-1]
            curr = subnet_data[i]

            prev_mom = prev.get(momentum_key, 0)
            curr_mom = curr.get(momentum_key, 0)

            # Crossover: previous was negative, current is positive
            if prev_mom < 0 and curr_mom > 0:
                # Collect forward returns
                forward_returns = {}
                for horizon in [1, 3, 7, 14, 21, 30]:
                    ret_key = f'ret_{horizon}d'
                    if curr.get(ret_key) is not None:
                        forward_returns[horizon] = curr[ret_key]

                if forward_returns:
                    events.append({
                        'netuid': netuid,
                        'date': curr['date'],
                        'momentum_value': curr_mom,
                        'returns': forward_returns,
                    })

    if len(events) < 20:
        return {'error': 'Insufficient crossover events', 'n': len(events)}

    # Aggregate returns by horizon
    horizon_returns = defaultdict(list)
    for event in events:
        for horizon, ret in event['returns'].items():
            if ret is not None:
                horizon_returns[horizon].append(ret)

    # Calculate average cumulative return at each horizon
    avg_returns = {}
    for horizon in [1, 3, 7, 14, 21, 30]:
        if horizon in horizon_returns and len(horizon_returns[horizon]) > 10:
            returns = horizon_returns[horizon]
            avg_returns[horizon] = {
                'mean': float(np.mean(returns)),
                'median': float(np.median(returns)),
                'std': float(np.std(returns)),
                'positive_pct': float(np.mean(np.array(returns) > 0)),
                'n': len(returns),
            }

    return {
        'momentum_key': momentum_key,
        'total_events': len(events),
        'returns_by_horizon': avg_returns,
    }


def find_peak_timing(data: List[Dict], momentum_key: str) -> Dict:
    """
    When momentum is positive, when does price typically peak?
    Track cumulative returns and find the average peak day.
    """
    # Filter to positive momentum observations
    positive_mom = [d for d in data if d.get(momentum_key, 0) > 0 and d.get('ret_30d') is not None]

    if len(positive_mom) < 100:
        return {'error': 'Insufficient data', 'n': len(positive_mom)}

    # For each observation, find when peak return occurred
    peak_days = []
    peak_returns = []

    horizons = [1, 3, 7, 14, 21, 30]

    for d in positive_mom:
        returns_by_day = {}
        for h in horizons:
            ret = d.get(f'ret_{h}d')
            if ret is not None:
                returns_by_day[h] = ret

        if len(returns_by_day) >= 4:  # Need enough data points
            peak_day = max(returns_by_day.keys(), key=lambda k: returns_by_day[k])
            peak_ret = returns_by_day[peak_day]
            peak_days.append(peak_day)
            peak_returns.append(peak_ret)

    if not peak_days:
        return {'error': 'Could not compute peaks'}

    # Distribution of peak days
    day_counts = {h: peak_days.count(h) for h in horizons}

    return {
        'momentum_key': momentum_key,
        'n_observations': len(positive_mom),
        'avg_peak_day': float(np.mean(peak_days)),
        'median_peak_day': float(np.median(peak_days)),
        'peak_day_distribution': day_counts,
        'avg_peak_return': float(np.mean(peak_returns)),
        'median_peak_return': float(np.median(peak_returns)),
    }


def analyze_return_decay(data: List[Dict], momentum_key: str, quintile: int = 4) -> Dict:
    """
    For the top quintile of momentum, track how returns evolve over time.
    This shows the decay pattern - when does alpha opportunity fade?
    """
    valid = [d for d in data if d.get('ret_30d') is not None]
    if len(valid) < 100:
        return {'error': 'Insufficient data'}

    metrics = np.array([d[momentum_key] for d in valid])
    mask = np.isfinite(metrics)
    valid = [d for d, m in zip(valid, mask) if m]
    metrics = np.array([d[momentum_key] for d in valid])

    # Get top quintile threshold
    q80 = np.percentile(metrics, 80)
    top_quintile = [d for d, m in zip(valid, metrics >= q80) if m]

    if len(top_quintile) < 50:
        return {'error': 'Insufficient top quintile data', 'n': len(top_quintile)}

    # Track average return at each horizon
    decay_curve = {}
    horizons = [1, 3, 7, 14, 21, 30]

    for h in horizons:
        returns = [d[f'ret_{h}d'] for d in top_quintile if d.get(f'ret_{h}d') is not None]
        if returns:
            decay_curve[h] = {
                'mean': float(np.mean(returns)),
                'median': float(np.median(returns)),
                'std': float(np.std(returns)),
                'sharpe': float(np.mean(returns) / np.std(returns)) if np.std(returns) > 0 else 0,
                'positive_pct': float(np.mean(np.array(returns) > 0)),
                'n': len(returns),
            }

    # Find optimal exit point (where Sharpe is maximized)
    sharpes = {h: decay_curve[h]['sharpe'] for h in decay_curve if 'sharpe' in decay_curve[h]}
    optimal_horizon = max(sharpes.keys(), key=lambda k: sharpes[k]) if sharpes else None

    return {
        'momentum_key': momentum_key,
        'quintile': 'top',
        'n_observations': len(top_quintile),
        'decay_curve': decay_curve,
        'optimal_exit_day': optimal_horizon,
        'optimal_sharpe': sharpes.get(optimal_horizon, 0) if optimal_horizon else 0,
    }


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

async def run_deep_dive():
    """Run comprehensive momentum analysis."""

    print("=" * 80)
    print("DEEP DIVE: FLOW MOMENTUM ANALYSIS")
    print("=" * 80)
    print()

    # Load data
    print("Loading data...")
    raw_data = await load_data()
    print(f"Loaded {len(raw_data)} subnets")

    # Compute metrics
    print("Computing metrics...")
    all_data = []
    for netuid, snapshots in raw_data.items():
        metrics = compute_all_metrics(snapshots)
        all_data.extend(metrics)

    print(f"Total data points: {len(all_data)}")
    print()

    # ==========================================================================
    # SECTION 1: All Momentum Metrics vs All Horizons
    # ==========================================================================

    print("=" * 80)
    print("SECTION 1: MOMENTUM METRICS COMPARISON")
    print("=" * 80)
    print()

    momentum_metrics = [
        'flow_1d_mom_1d', 'flow_1d_mom_3d', 'flow_1d_mom_7d',
        'flow_3d_mom_3d', 'flow_3d_mom_7d',
        'flow_7d_mom_3d', 'flow_7d_mom_7d', 'flow_7d_mom_14d',
        'flow_1d_to_7d', 'flow_3d_to_7d', 'flow_7d_to_30d',
        'flow_7d_accel',
    ]

    all_results = []
    for metric in momentum_metrics:
        result = analyze_metric_vs_returns(all_data, metric)
        if result:
            all_results.append(result)

    # Print results table
    print("SPREAD (Q5 - Q1 return) by Metric and Horizon:")
    print("-" * 100)
    print(f"{'Metric':<20} {'1D':>10} {'3D':>10} {'7D':>10} {'14D':>10} {'21D':>10} {'30D':>10}")
    print("-" * 100)

    for r in all_results:
        row = f"{r['metric']:<20}"
        for h in [1, 3, 7, 14, 21, 30]:
            if f'{h}d' in r:
                spread = r[f'{h}d']['spread'] * 100
                row += f"{spread:>+10.1f}%"
            else:
                row += f"{'--':>10}"
        print(row)

    print()

    # ==========================================================================
    # SECTION 2: Event Study - Momentum Crossovers
    # ==========================================================================

    print("=" * 80)
    print("SECTION 2: EVENT STUDY - MOMENTUM CROSSOVER (Neg → Pos)")
    print("=" * 80)
    print()
    print("When momentum crosses from negative to positive, what are average returns?")
    print()

    key_metrics = ['flow_7d_mom_7d', 'flow_7d_mom_3d', 'flow_3d_mom_3d', 'flow_1d_mom_3d']

    for metric in key_metrics:
        result = event_study_momentum_crossover(all_data, metric)
        if 'error' not in result:
            print(f"{metric}:")
            print(f"  Total crossover events: {result['total_events']}")
            print(f"  Average returns after crossover:")

            for h in [1, 3, 7, 14, 21, 30]:
                if h in result['returns_by_horizon']:
                    r = result['returns_by_horizon'][h]
                    print(f"    {h:2}D: {r['mean']*100:+6.2f}% avg, {r['median']*100:+6.2f}% median, {r['positive_pct']*100:.0f}% positive (n={r['n']})")
            print()

    # ==========================================================================
    # SECTION 3: Peak Timing Analysis
    # ==========================================================================

    print("=" * 80)
    print("SECTION 3: PEAK TIMING - When Does Price Peak After Positive Momentum?")
    print("=" * 80)
    print()

    for metric in key_metrics:
        result = find_peak_timing(all_data, metric)
        if 'error' not in result:
            print(f"{metric}:")
            print(f"  Observations with positive momentum: {result['n_observations']}")
            print(f"  Average peak day: {result['avg_peak_day']:.1f}")
            print(f"  Median peak day: {result['median_peak_day']:.1f}")
            print(f"  Peak day distribution: {result['peak_day_distribution']}")
            print(f"  Average peak return: {result['avg_peak_return']*100:+.2f}%")
            print()

    # ==========================================================================
    # SECTION 4: Return Decay Analysis
    # ==========================================================================

    print("=" * 80)
    print("SECTION 4: RETURN DECAY - Alpha Opportunity Window")
    print("=" * 80)
    print()
    print("For TOP QUINTILE momentum, how do returns evolve over time?")
    print("(Looking for optimal entry/exit timing)")
    print()

    for metric in key_metrics:
        result = analyze_return_decay(all_data, metric)
        if 'error' not in result:
            print(f"{metric}:")
            print(f"  Top quintile observations: {result['n_observations']}")
            print(f"  Return curve:")

            for h in [1, 3, 7, 14, 21, 30]:
                if h in result['decay_curve']:
                    d = result['decay_curve'][h]
                    sharpe_str = f"Sharpe={d['sharpe']:.2f}" if d['sharpe'] else ""
                    print(f"    {h:2}D: {d['mean']*100:+6.2f}% avg, {d['positive_pct']*100:.0f}% win rate, {sharpe_str}")

            print(f"  OPTIMAL EXIT: Day {result['optimal_exit_day']} (Sharpe={result['optimal_sharpe']:.2f})")
            print()

    # ==========================================================================
    # SECTION 5: Best Metric-Horizon Combinations
    # ==========================================================================

    print("=" * 80)
    print("SECTION 5: BEST METRIC-HORIZON COMBINATIONS")
    print("=" * 80)
    print()

    # Collect all spread values
    all_spreads = []
    for r in all_results:
        for h in [1, 3, 7, 14, 21, 30]:
            if f'{h}d' in r:
                all_spreads.append({
                    'metric': r['metric'],
                    'horizon': h,
                    'spread': r[f'{h}d']['spread'],
                    'mono': r[f'{h}d']['mono'],
                    'corr': r[f'{h}d']['corr'],
                    'pval': r[f'{h}d']['pval'],
                })

    # Sort by spread
    positive_spreads = [s for s in all_spreads if s['spread'] > 0]
    positive_spreads.sort(key=lambda x: x['spread'], reverse=True)

    print("TOP 15 POSITIVE SPREAD COMBINATIONS (Actionable Signals):")
    print("-" * 80)
    print(f"{'Rank':<5} {'Metric':<20} {'Horizon':>8} {'Spread':>12} {'Mono':>8} {'P-Value':>12}")
    print("-" * 80)

    for i, s in enumerate(positive_spreads[:15], 1):
        sig = "*" if s['pval'] < 0.05 else ""
        print(f"{i:<5} {s['metric']:<20} {s['horizon']:>5}D {s['spread']*100:>+10.2f}% {s['mono']:>+8.2f} {s['pval']:>11.4f}{sig}")

    print()
    print("* = statistically significant (p < 0.05)")
    print()

    # ==========================================================================
    # SECTION 6: Trading Strategy Implications
    # ==========================================================================

    print("=" * 80)
    print("SECTION 6: TRADING STRATEGY IMPLICATIONS")
    print("=" * 80)
    print()

    # Find the best momentum metric
    if positive_spreads:
        best = positive_spreads[0]
        print(f"BEST SIGNAL: {best['metric']} predicting {best['horizon']}D returns")
        print(f"  - Spread: {best['spread']*100:+.2f}% (Q5 - Q1)")
        print(f"  - Monotonicity: {best['mono']:+.2f}")
        print()

        # Get decay analysis for best metric
        decay = analyze_return_decay(all_data, best['metric'])
        if 'error' not in decay:
            print("ALPHA WINDOW ANALYSIS:")
            print("-" * 40)

            peak_day = None
            peak_return = 0

            for h in [1, 3, 7, 14, 21, 30]:
                if h in decay['decay_curve']:
                    d = decay['decay_curve'][h]
                    if d['mean'] > peak_return:
                        peak_return = d['mean']
                        peak_day = h

                    status = "PEAK" if h == peak_day else ""
                    print(f"  Day {h:2}: {d['mean']*100:+6.2f}% avg return, {d['positive_pct']*100:.0f}% win rate {status}")

            print()
            if peak_day:
                print(f"RECOMMENDATION:")
                print(f"  - ENTRY: When {best['metric']} is in top quintile (strongly positive)")
                print(f"  - TARGET HOLD: {peak_day} days (peak average return)")
                print(f"  - EXIT BY: Day {decay['optimal_exit_day']} (optimal risk-adjusted)")

                # Check for mean reversion
                if 30 in decay['decay_curve'] and peak_day and peak_day < 30:
                    final_return = decay['decay_curve'][30]['mean']
                    peak_return = decay['decay_curve'][peak_day]['mean']
                    if final_return < peak_return:
                        print(f"  - WARNING: Mean reversion observed after day {peak_day}")
                        print(f"             Return decays from {peak_return*100:+.2f}% to {final_return*100:+.2f}% by day 30")


if __name__ == "__main__":
    asyncio.run(run_deep_dive())
