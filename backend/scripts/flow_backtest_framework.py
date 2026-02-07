#!/usr/bin/env python3
"""
Comprehensive Flow Metrics Backtest Framework

This framework tests multiple flow-based metrics against future price returns
across multiple time horizons, using:
1. Correlation analysis
2. Quintile bucket analysis
3. Momentum/rate-of-change analysis

Data: ~357 days of dTAO history (Feb 13, 2025 - present)
"""

import asyncio
import sys
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from scipy import stats
from sqlalchemy import select, func, text

from app.core.database import get_db_context
from app.models.subnet import SubnetSnapshot


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DailySnapshot:
    """Single day's data for a subnet."""
    netuid: int
    date: datetime
    price: float
    pool_reserve: float


@dataclass
class MetricPoint:
    """Computed metrics and forward returns for analysis."""
    netuid: int
    date: datetime
    price: float

    # Raw flow metrics
    flow_1d: float
    flow_3d: float
    flow_7d: float
    flow_14d: float
    flow_30d: float

    # FTI variants
    fti: float  # (flow_1d * 0.5) + (flow_7d/7 * 0.3) + (flow_30d/30 * 0.2)
    fti_normalized: float  # FTI / pool_reserve

    # Momentum metrics
    fti_momentum_3d: float  # FTI change over 3 days
    fti_momentum_7d: float  # FTI change over 7 days
    flow_7d_momentum: float  # 7d flow change over 7 days
    flow_7d_acceleration: float  # rate of change of 7d flow

    # Forward returns (to be filled)
    return_1d: Optional[float] = None
    return_3d: Optional[float] = None
    return_7d: Optional[float] = None
    return_14d: Optional[float] = None


@dataclass
class AnalysisResult:
    """Results for a single metric-horizon combination."""
    metric_name: str
    horizon: str
    n_observations: int

    # Correlation analysis
    correlation: float
    r_squared: float
    p_value: float
    is_significant: bool

    # Quintile analysis
    quintile_returns: List[float]  # Average return per quintile
    quintile_counts: List[int]
    monotonic_score: float  # How monotonic the relationship is (-1 to 1)

    # Top/Bottom analysis
    top_quintile_return: float
    bottom_quintile_return: float
    spread: float  # top - bottom


# =============================================================================
# DATA LOADING
# =============================================================================

async def load_all_snapshots() -> Dict[int, List[DailySnapshot]]:
    """Load all historical snapshots, organized by subnet."""
    async with get_db_context() as db:
        stmt = (
            select(SubnetSnapshot)
            .where(SubnetSnapshot.alpha_price_tao > 0)
            .where(SubnetSnapshot.pool_tao_reserve > 0)
            .order_by(SubnetSnapshot.netuid, SubnetSnapshot.timestamp)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        by_subnet: Dict[int, List[DailySnapshot]] = defaultdict(list)
        for row in rows:
            snap = DailySnapshot(
                netuid=row.netuid,
                date=row.timestamp.replace(tzinfo=None),
                price=float(row.alpha_price_tao),
                pool_reserve=float(row.pool_tao_reserve),
            )
            by_subnet[row.netuid].append(snap)

        return dict(by_subnet)


# =============================================================================
# METRIC COMPUTATION
# =============================================================================

def compute_metrics(snapshots: List[DailySnapshot]) -> List[MetricPoint]:
    """Compute all metrics for a subnet's time series."""
    if len(snapshots) < 45:  # Need history for lookback + forward
        return []

    # Index by date for easier lookup
    by_date = {s.date.date(): s for s in snapshots}
    dates = sorted(by_date.keys())

    points = []

    for i, date in enumerate(dates):
        snap = by_date[date]

        # Need at least 30 days lookback
        if i < 30:
            continue

        # Calculate flows from reserve changes
        def get_flow(days_back: int) -> float:
            if i >= days_back:
                past_date = dates[i - days_back]
                return snap.pool_reserve - by_date[past_date].pool_reserve
            return 0.0

        flow_1d = get_flow(1)
        flow_3d = get_flow(3)
        flow_7d = get_flow(7)
        flow_14d = get_flow(14)
        flow_30d = get_flow(30)

        # FTI calculation
        fti = (flow_1d * 0.5) + (flow_7d / 7 * 0.3) + (flow_30d / 30 * 0.2)
        fti_normalized = fti / snap.pool_reserve if snap.pool_reserve > 0 else 0

        # FTI momentum (need historical FTI)
        def get_past_fti(days_back: int) -> float:
            if i >= days_back + 30:
                past_date = dates[i - days_back]
                past_snap = by_date[past_date]

                past_flow_1d = get_flow_at(i - days_back, 1)
                past_flow_7d = get_flow_at(i - days_back, 7)
                past_flow_30d = get_flow_at(i - days_back, 30)

                return (past_flow_1d * 0.5) + (past_flow_7d / 7 * 0.3) + (past_flow_30d / 30 * 0.2)
            return fti

        def get_flow_at(idx: int, days_back: int) -> float:
            if idx >= days_back:
                return by_date[dates[idx]].pool_reserve - by_date[dates[idx - days_back]].pool_reserve
            return 0.0

        past_fti_3d = get_past_fti(3)
        past_fti_7d = get_past_fti(7)

        fti_momentum_3d = fti - past_fti_3d
        fti_momentum_7d = fti - past_fti_7d

        # Flow 7d momentum
        past_flow_7d = get_flow_at(i - 7, 7) if i >= 14 else flow_7d
        flow_7d_momentum = flow_7d - past_flow_7d
        flow_7d_acceleration = flow_7d_momentum / abs(past_flow_7d) if past_flow_7d != 0 else 0

        # Forward returns
        def get_return(days_forward: int) -> Optional[float]:
            if i + days_forward < len(dates):
                future_date = dates[i + days_forward]
                future_price = by_date[future_date].price
                if snap.price > 0:
                    return (future_price - snap.price) / snap.price
            return None

        point = MetricPoint(
            netuid=snap.netuid,
            date=snap.date,
            price=snap.price,
            flow_1d=flow_1d,
            flow_3d=flow_3d,
            flow_7d=flow_7d,
            flow_14d=flow_14d,
            flow_30d=flow_30d,
            fti=fti,
            fti_normalized=fti_normalized,
            fti_momentum_3d=fti_momentum_3d,
            fti_momentum_7d=fti_momentum_7d,
            flow_7d_momentum=flow_7d_momentum,
            flow_7d_acceleration=flow_7d_acceleration,
            return_1d=get_return(1),
            return_3d=get_return(3),
            return_7d=get_return(7),
            return_14d=get_return(14),
        )
        points.append(point)

    return points


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def analyze_metric_horizon(
    points: List[MetricPoint],
    metric_name: str,
    horizon: str,
) -> Optional[AnalysisResult]:
    """Analyze a single metric against a single return horizon."""

    # Extract metric values and returns
    metric_getter = {
        'flow_1d': lambda p: p.flow_1d,
        'flow_3d': lambda p: p.flow_3d,
        'flow_7d': lambda p: p.flow_7d,
        'flow_14d': lambda p: p.flow_14d,
        'flow_30d': lambda p: p.flow_30d,
        'fti': lambda p: p.fti,
        'fti_normalized': lambda p: p.fti_normalized,
        'fti_momentum_3d': lambda p: p.fti_momentum_3d,
        'fti_momentum_7d': lambda p: p.fti_momentum_7d,
        'flow_7d_momentum': lambda p: p.flow_7d_momentum,
        'flow_7d_acceleration': lambda p: p.flow_7d_acceleration,
    }

    return_getter = {
        '1d': lambda p: p.return_1d,
        '3d': lambda p: p.return_3d,
        '7d': lambda p: p.return_7d,
        '14d': lambda p: p.return_14d,
    }

    if metric_name not in metric_getter or horizon not in return_getter:
        return None

    get_metric = metric_getter[metric_name]
    get_return = return_getter[horizon]

    # Filter to valid points
    valid_points = [
        (get_metric(p), get_return(p))
        for p in points
        if get_return(p) is not None
    ]

    if len(valid_points) < 50:
        return None

    metrics = np.array([v[0] for v in valid_points])
    returns = np.array([v[1] for v in valid_points])

    # Remove NaN/Inf
    mask = np.isfinite(metrics) & np.isfinite(returns)
    metrics = metrics[mask]
    returns = returns[mask]

    if len(metrics) < 50:
        return None

    # Correlation analysis
    try:
        corr, p_value = stats.pearsonr(metrics, returns)
        r_squared = corr ** 2
    except:
        return None

    # Quintile analysis
    try:
        quintile_edges = np.percentile(metrics, [0, 20, 40, 60, 80, 100])
        quintile_returns = []
        quintile_counts = []

        for q in range(5):
            low = quintile_edges[q]
            high = quintile_edges[q + 1]

            if q == 4:  # Last quintile includes upper bound
                mask = (metrics >= low) & (metrics <= high)
            else:
                mask = (metrics >= low) & (metrics < high)

            q_returns = returns[mask]
            quintile_returns.append(float(np.mean(q_returns)) if len(q_returns) > 0 else 0.0)
            quintile_counts.append(int(np.sum(mask)))

        # Monotonic score: Spearman correlation of quintile rank vs quintile return
        monotonic_corr, _ = stats.spearmanr(range(5), quintile_returns)
        monotonic_score = float(monotonic_corr) if not np.isnan(monotonic_corr) else 0.0

    except Exception as e:
        quintile_returns = [0.0] * 5
        quintile_counts = [0] * 5
        monotonic_score = 0.0

    return AnalysisResult(
        metric_name=metric_name,
        horizon=horizon,
        n_observations=len(metrics),
        correlation=float(corr),
        r_squared=float(r_squared),
        p_value=float(p_value),
        is_significant=p_value < 0.05,
        quintile_returns=quintile_returns,
        quintile_counts=quintile_counts,
        monotonic_score=monotonic_score,
        top_quintile_return=quintile_returns[4],
        bottom_quintile_return=quintile_returns[0],
        spread=quintile_returns[4] - quintile_returns[0],
    )


# =============================================================================
# MAIN BACKTEST
# =============================================================================

async def run_comprehensive_backtest():
    """Run the full backtest across all metrics and horizons."""

    print("=" * 80)
    print("COMPREHENSIVE FLOW METRICS BACKTEST")
    print("=" * 80)
    print()

    # Load data
    print("Loading historical snapshots...")
    snapshots_by_subnet = await load_all_snapshots()
    print(f"Loaded data for {len(snapshots_by_subnet)} subnets")

    # Compute metrics for all subnets
    print("Computing flow metrics...")
    all_points: List[MetricPoint] = []

    for netuid, snapshots in snapshots_by_subnet.items():
        points = compute_metrics(snapshots)
        all_points.extend(points)
        if len(points) > 0:
            print(f"  Subnet {netuid}: {len(points)} data points")

    print(f"\nTotal analysis points: {len(all_points)}")
    print()

    # Define test matrix
    metrics = [
        'flow_1d', 'flow_3d', 'flow_7d', 'flow_14d', 'flow_30d',
        'fti', 'fti_normalized',
        'fti_momentum_3d', 'fti_momentum_7d',
        'flow_7d_momentum', 'flow_7d_acceleration',
    ]

    horizons = ['1d', '3d', '7d', '14d']

    # Run analysis
    results: List[AnalysisResult] = []

    for metric in metrics:
        for horizon in horizons:
            result = analyze_metric_horizon(all_points, metric, horizon)
            if result:
                results.append(result)

    # ==========================================================================
    # REPORT: CORRELATION ANALYSIS
    # ==========================================================================

    print("=" * 80)
    print("SECTION 1: CORRELATION ANALYSIS")
    print("=" * 80)
    print()
    print(f"{'Metric':<22} {'Horizon':<8} {'Corr':>10} {'R²':>10} {'P-Value':>12} {'Sig?':>6}")
    print("-" * 80)

    # Group by horizon for easier comparison
    for horizon in horizons:
        horizon_results = [r for r in results if r.horizon == horizon]
        horizon_results.sort(key=lambda x: abs(x.correlation), reverse=True)

        for r in horizon_results:
            sig = "YES" if r.is_significant else "no"
            print(f"{r.metric_name:<22} {r.horizon:<8} {r.correlation:>+10.4f} {r.r_squared:>10.4f} {r.p_value:>12.6f} {sig:>6}")
        print()

    # ==========================================================================
    # REPORT: QUINTILE ANALYSIS
    # ==========================================================================

    print("=" * 80)
    print("SECTION 2: QUINTILE ANALYSIS (Average Return by Metric Quintile)")
    print("=" * 80)
    print()
    print("Quintile buckets: Q1 = lowest metric values, Q5 = highest metric values")
    print("Positive spread (Q5-Q1 > 0) means higher metric predicts better returns")
    print()

    print(f"{'Metric':<22} {'Horizon':<6} {'Q1':>8} {'Q2':>8} {'Q3':>8} {'Q4':>8} {'Q5':>8} {'Spread':>10} {'Mono':>8}")
    print("-" * 100)

    for horizon in horizons:
        horizon_results = [r for r in results if r.horizon == horizon]
        horizon_results.sort(key=lambda x: x.spread, reverse=True)

        for r in horizon_results:
            q1, q2, q3, q4, q5 = [f"{x*100:+.2f}%" for x in r.quintile_returns]
            spread = f"{r.spread*100:+.2f}%"
            mono = f"{r.monotonic_score:+.2f}"
            print(f"{r.metric_name:<22} {r.horizon:<6} {q1:>8} {q2:>8} {q3:>8} {q4:>8} {q5:>8} {spread:>10} {mono:>8}")
        print()

    # ==========================================================================
    # REPORT: BEST PERFORMERS
    # ==========================================================================

    print("=" * 80)
    print("SECTION 3: TOP PERFORMERS BY CRITERION")
    print("=" * 80)
    print()

    # Best by spread (quintile analysis)
    print("TOP 10 BY QUINTILE SPREAD (most predictive of direction):")
    print("-" * 60)
    sorted_by_spread = sorted(results, key=lambda x: x.spread, reverse=True)[:10]
    for i, r in enumerate(sorted_by_spread, 1):
        print(f"{i:2}. {r.metric_name:<20} ({r.horizon:<3}): Spread = {r.spread*100:+.2f}%, Q5 = {r.top_quintile_return*100:+.2f}%")
    print()

    # Best by monotonicity
    print("TOP 10 BY MONOTONICITY (most consistent relationship):")
    print("-" * 60)
    sorted_by_mono = sorted(results, key=lambda x: x.monotonic_score, reverse=True)[:10]
    for i, r in enumerate(sorted_by_mono, 1):
        print(f"{i:2}. {r.metric_name:<20} ({r.horizon:<3}): Mono = {r.monotonic_score:+.2f}, Spread = {r.spread*100:+.2f}%")
    print()

    # Best by statistical significance with positive spread
    print("TOP 10 STATISTICALLY SIGNIFICANT WITH POSITIVE SPREAD:")
    print("-" * 60)
    sig_positive = [r for r in results if r.is_significant and r.spread > 0]
    sig_positive.sort(key=lambda x: x.spread, reverse=True)
    for i, r in enumerate(sig_positive[:10], 1):
        print(f"{i:2}. {r.metric_name:<20} ({r.horizon:<3}): Spread = {r.spread*100:+.2f}%, p = {r.p_value:.4f}")
    print()

    # ==========================================================================
    # REPORT: FTI vs FLOW_7D HEAD-TO-HEAD
    # ==========================================================================

    print("=" * 80)
    print("SECTION 4: FTI vs FLOW_7D HEAD-TO-HEAD COMPARISON")
    print("=" * 80)
    print()

    for horizon in horizons:
        fti_result = next((r for r in results if r.metric_name == 'fti' and r.horizon == horizon), None)
        flow_7d_result = next((r for r in results if r.metric_name == 'flow_7d' and r.horizon == horizon), None)
        fti_mom_result = next((r for r in results if r.metric_name == 'fti_momentum_7d' and r.horizon == horizon), None)

        print(f"{horizon} Forward Return:")
        print("-" * 40)

        if fti_result:
            print(f"  FTI:             Spread={fti_result.spread*100:+.2f}%, Mono={fti_result.monotonic_score:+.2f}, R²={fti_result.r_squared:.4f}")
        if flow_7d_result:
            print(f"  Flow 7D:         Spread={flow_7d_result.spread*100:+.2f}%, Mono={flow_7d_result.monotonic_score:+.2f}, R²={flow_7d_result.r_squared:.4f}")
        if fti_mom_result:
            print(f"  FTI Momentum 7D: Spread={fti_mom_result.spread*100:+.2f}%, Mono={fti_mom_result.monotonic_score:+.2f}, R²={fti_mom_result.r_squared:.4f}")

        # Winner
        candidates = [r for r in [fti_result, flow_7d_result, fti_mom_result] if r]
        if candidates:
            winner = max(candidates, key=lambda x: x.spread)
            print(f"  WINNER: {winner.metric_name}")
        print()

    # ==========================================================================
    # REPORT: MOMENTUM ANALYSIS
    # ==========================================================================

    print("=" * 80)
    print("SECTION 5: MOMENTUM METRICS ANALYSIS")
    print("=" * 80)
    print()
    print("Does the CHANGE in flow/FTI predict better than absolute levels?")
    print()

    for horizon in horizons:
        print(f"{horizon} Forward Return:")
        print("-" * 50)

        level_metrics = ['flow_7d', 'fti', 'fti_normalized']
        momentum_metrics = ['fti_momentum_3d', 'fti_momentum_7d', 'flow_7d_momentum', 'flow_7d_acceleration']

        print("  LEVEL METRICS:")
        for metric in level_metrics:
            r = next((x for x in results if x.metric_name == metric and x.horizon == horizon), None)
            if r:
                print(f"    {metric:<20}: Spread={r.spread*100:+.2f}%, Mono={r.monotonic_score:+.2f}")

        print("  MOMENTUM METRICS:")
        for metric in momentum_metrics:
            r = next((x for x in results if x.metric_name == metric and x.horizon == horizon), None)
            if r:
                print(f"    {metric:<20}: Spread={r.spread*100:+.2f}%, Mono={r.monotonic_score:+.2f}")
        print()

    # ==========================================================================
    # FINAL CONCLUSIONS
    # ==========================================================================

    print("=" * 80)
    print("FINAL CONCLUSIONS")
    print("=" * 80)
    print()

    # Find overall best metric-horizon combo
    best_by_spread = max(results, key=lambda x: x.spread)
    best_by_mono = max(results, key=lambda x: x.monotonic_score)

    print(f"Best by Quintile Spread: {best_by_spread.metric_name} @ {best_by_spread.horizon}")
    print(f"  - Top quintile avg return: {best_by_spread.top_quintile_return*100:+.2f}%")
    print(f"  - Bottom quintile avg return: {best_by_spread.bottom_quintile_return*100:+.2f}%")
    print(f"  - Spread: {best_by_spread.spread*100:+.2f}%")
    print()

    print(f"Best by Monotonicity: {best_by_mono.metric_name} @ {best_by_mono.horizon}")
    print(f"  - Monotonic score: {best_by_mono.monotonic_score:+.2f}")
    print(f"  - Spread: {best_by_mono.spread*100:+.2f}%")
    print()

    # Save raw results to JSON for further analysis
    output_path = Path(__file__).parent / "backtest_results.json"
    output_data = {
        "run_timestamp": datetime.now().isoformat(),
        "total_observations": len(all_points),
        "subnets_analyzed": len(snapshots_by_subnet),
        "results": [
            {
                "metric": r.metric_name,
                "horizon": r.horizon,
                "n": r.n_observations,
                "correlation": r.correlation,
                "r_squared": r.r_squared,
                "p_value": r.p_value,
                "is_significant": r.is_significant,
                "quintile_returns": r.quintile_returns,
                "monotonic_score": r.monotonic_score,
                "spread": r.spread,
            }
            for r in results
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"Raw results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_backtest())
