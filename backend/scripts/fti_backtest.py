#!/usr/bin/env python3
"""
Flow Trend Index (FTI) vs 7D Flow Backtest Analysis

This script compares the predictive power of:
1. Raw 7-day flow
2. Flow Trend Index (FTI) = (flow_1d * 0.5) + (flow_7d/7 * 0.3) + (flow_30d/30 * 0.2)

We measure correlation and R² with forward 7-day price returns to determine
which metric better predicts future subnet alpha price movements.
"""

import asyncio
import sys
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from scipy import stats
from sqlalchemy import select, func

from app.core.database import get_db_context
from app.models.subnet import SubnetSnapshot


@dataclass
class SnapshotData:
    """Data point for analysis."""
    netuid: int
    timestamp: datetime
    price: float
    pool_reserve: float


@dataclass
class AnalysisPoint:
    """Single point with flow metrics and forward return."""
    timestamp: datetime
    flow_1d: float
    flow_7d: float
    flow_30d: float
    fti: float
    fti_normalized: float
    price: float
    forward_return_7d: Optional[float]


async def get_snapshots(netuid: int, min_days: int = 60) -> List[SnapshotData]:
    """Fetch historical snapshots for a subnet."""
    async with get_db_context() as db:
        stmt = (
            select(SubnetSnapshot)
            .where(SubnetSnapshot.netuid == netuid)
            .order_by(SubnetSnapshot.timestamp)
        )
        result = await db.execute(stmt)
        snapshots = result.scalars().all()

        return [
            SnapshotData(
                netuid=s.netuid,
                timestamp=s.timestamp,
                price=float(s.alpha_price_tao) if s.alpha_price_tao else 0.0,
                pool_reserve=float(s.pool_tao_reserve) if s.pool_tao_reserve else 0.0,
            )
            for s in snapshots
            if s.alpha_price_tao and s.alpha_price_tao > 0
        ]


async def get_all_netuids() -> List[int]:
    """Get all netuids with sufficient historical data."""
    async with get_db_context() as db:
        stmt = (
            select(SubnetSnapshot.netuid, func.count(SubnetSnapshot.id).label('cnt'))
            .group_by(SubnetSnapshot.netuid)
            .having(func.count(SubnetSnapshot.id) >= 45)  # Need at least 45 days
        )
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]


def compute_flow_metrics(snapshots: List[SnapshotData]) -> List[AnalysisPoint]:
    """Compute flow metrics and forward returns from snapshots."""
    if len(snapshots) < 45:  # Need 30d lookback + 7d forward + buffer
        return []

    points = []

    # Index snapshots by date for easier lookup
    by_date = {s.timestamp.date(): s for s in snapshots}
    dates = sorted(by_date.keys())

    for i, date in enumerate(dates):
        snap = by_date[date]

        # Need at least 30 days lookback
        if i < 30:
            continue

        # Calculate flow from reserve changes
        # Flow 1d
        date_1d = dates[i - 1] if i >= 1 else None
        flow_1d = snap.pool_reserve - by_date[date_1d].pool_reserve if date_1d else 0

        # Flow 7d
        date_7d = dates[i - 7] if i >= 7 else None
        flow_7d = snap.pool_reserve - by_date[date_7d].pool_reserve if date_7d else 0

        # Flow 30d
        date_30d = dates[i - 30] if i >= 30 else None
        flow_30d = snap.pool_reserve - by_date[date_30d].pool_reserve if date_30d else 0

        # Calculate FTI
        # FTI = (flow_1d * 0.5) + (flow_7d/7 * 0.3) + (flow_30d/30 * 0.2)
        fti = (flow_1d * 0.5) + (flow_7d / 7 * 0.3) + (flow_30d / 30 * 0.2)

        # Normalized FTI (by pool size)
        fti_normalized = fti / snap.pool_reserve if snap.pool_reserve > 0 else 0

        # Forward 7-day return
        forward_return = None
        if i + 7 < len(dates):
            date_future = dates[i + 7]
            future_price = by_date[date_future].price
            if snap.price > 0:
                forward_return = (future_price - snap.price) / snap.price

        points.append(AnalysisPoint(
            timestamp=snap.timestamp,
            flow_1d=flow_1d,
            flow_7d=flow_7d,
            flow_30d=flow_30d,
            fti=fti,
            fti_normalized=fti_normalized,
            price=snap.price,
            forward_return_7d=forward_return,
        ))

    return points


def analyze_correlation(points: List[AnalysisPoint]) -> Dict[str, Any]:
    """Compute correlation and R² for flow metrics vs forward returns."""
    # Filter to points with valid forward returns
    valid_points = [p for p in points if p.forward_return_7d is not None]

    if len(valid_points) < 10:
        return {"error": "Insufficient data points", "n": len(valid_points)}

    returns = np.array([p.forward_return_7d for p in valid_points])
    flow_7d = np.array([p.flow_7d for p in valid_points])
    fti = np.array([p.fti for p in valid_points])
    fti_norm = np.array([p.fti_normalized for p in valid_points])
    flow_1d = np.array([p.flow_1d for p in valid_points])

    # Remove any NaN or Inf
    mask = np.isfinite(returns) & np.isfinite(flow_7d) & np.isfinite(fti) & np.isfinite(fti_norm)
    returns = returns[mask]
    flow_7d = flow_7d[mask]
    fti = fti[mask]
    fti_norm = fti_norm[mask]
    flow_1d = flow_1d[mask]

    if len(returns) < 10:
        return {"error": "Insufficient valid data points after filtering", "n": len(returns)}

    # Calculate correlations using Pearson
    corr_7d, pval_7d = stats.pearsonr(flow_7d, returns)
    corr_fti, pval_fti = stats.pearsonr(fti, returns)
    corr_fti_norm, pval_fti_norm = stats.pearsonr(fti_norm, returns)
    corr_1d, pval_1d = stats.pearsonr(flow_1d, returns)

    # R² values
    r2_7d = corr_7d ** 2
    r2_fti = corr_fti ** 2
    r2_fti_norm = corr_fti_norm ** 2
    r2_1d = corr_1d ** 2

    # Linear regression for more detail
    slope_7d, intercept_7d, r_7d, p_7d, stderr_7d = stats.linregress(flow_7d, returns)
    slope_fti, intercept_fti, r_fti, p_fti, stderr_fti = stats.linregress(fti, returns)

    return {
        "n": len(returns),
        "flow_7d": {
            "correlation": float(corr_7d),
            "r_squared": float(r2_7d),
            "p_value": float(pval_7d),
            "slope": float(slope_7d),
            "significant": pval_7d < 0.05,
        },
        "fti": {
            "correlation": float(corr_fti),
            "r_squared": float(r2_fti),
            "p_value": float(pval_fti),
            "slope": float(slope_fti),
            "significant": pval_fti < 0.05,
        },
        "fti_normalized": {
            "correlation": float(corr_fti_norm),
            "r_squared": float(r2_fti_norm),
            "p_value": float(pval_fti_norm),
            "significant": pval_fti_norm < 0.05,
        },
        "flow_1d": {
            "correlation": float(corr_1d),
            "r_squared": float(r2_1d),
            "p_value": float(pval_1d),
            "significant": pval_1d < 0.05,
        },
    }


async def run_backtest():
    """Run the full backtest analysis across all subnets."""
    print("=" * 70)
    print("FTI vs 7D FLOW BACKTEST ANALYSIS")
    print("=" * 70)
    print()

    # Get all subnets with sufficient data
    netuids = await get_all_netuids()
    print(f"Found {len(netuids)} subnets with sufficient historical data")
    print()

    all_results = []
    aggregated_points = []

    for netuid in netuids:
        snapshots = await get_snapshots(netuid)
        if len(snapshots) < 45:
            continue

        points = compute_flow_metrics(snapshots)
        if len(points) < 10:
            continue

        result = analyze_correlation(points)
        if "error" not in result:
            result["netuid"] = netuid
            result["days"] = len(snapshots)
            all_results.append(result)
            aggregated_points.extend(points)

            print(f"Subnet {netuid}: n={result['n']}")
            print(f"  7D Flow:  r={result['flow_7d']['correlation']:+.4f}, R²={result['flow_7d']['r_squared']:.4f}, p={result['flow_7d']['p_value']:.4f}")
            print(f"  FTI:      r={result['fti']['correlation']:+.4f}, R²={result['fti']['r_squared']:.4f}, p={result['fti']['p_value']:.4f}")
            print(f"  FTI norm: r={result['fti_normalized']['correlation']:+.4f}, R²={result['fti_normalized']['r_squared']:.4f}, p={result['fti_normalized']['p_value']:.4f}")
            winner = "FTI" if result['fti']['r_squared'] > result['flow_7d']['r_squared'] else "7D Flow"
            print(f"  Winner: {winner}")
            print()

    # Aggregate analysis across all subnets
    print("=" * 70)
    print("AGGREGATE ANALYSIS (All Subnets Pooled)")
    print("=" * 70)

    agg_result = analyze_correlation(aggregated_points)
    if "error" not in agg_result:
        print(f"Total data points: {agg_result['n']}")
        print()
        print("Metric Comparison:")
        print("-" * 50)
        print(f"{'Metric':<15} {'Correlation':>12} {'R²':>10} {'P-Value':>12} {'Sig?':>6}")
        print("-" * 50)

        for metric_name, metric_key in [("1D Flow", "flow_1d"), ("7D Flow", "flow_7d"), ("FTI", "fti"), ("FTI Norm", "fti_normalized")]:
            m = agg_result[metric_key]
            sig = "Yes" if m['significant'] else "No"
            print(f"{metric_name:<15} {m['correlation']:>+12.4f} {m['r_squared']:>10.4f} {m['p_value']:>12.6f} {sig:>6}")

        print("-" * 50)
        print()

        # Determine winner
        fti_r2 = agg_result['fti']['r_squared']
        flow_7d_r2 = agg_result['flow_7d']['r_squared']
        fti_norm_r2 = agg_result['fti_normalized']['r_squared']

        best_metric = max([
            ("7D Flow", flow_7d_r2),
            ("FTI", fti_r2),
            ("FTI Normalized", fti_norm_r2),
        ], key=lambda x: x[1])

        print(f"WINNER: {best_metric[0]} (R² = {best_metric[1]:.4f})")
        print()

        # Improvement analysis
        if fti_r2 > flow_7d_r2:
            improvement = ((fti_r2 - flow_7d_r2) / flow_7d_r2) * 100 if flow_7d_r2 > 0 else float('inf')
            print(f"FTI improves predictive power over 7D Flow by {improvement:.1f}%")
        else:
            improvement = ((flow_7d_r2 - fti_r2) / fti_r2) * 100 if fti_r2 > 0 else float('inf')
            print(f"7D Flow is {improvement:.1f}% better than FTI")

        print()
        print("=" * 70)
        print("CONCLUSION")
        print("=" * 70)

        # Statistical significance check
        fti_sig = agg_result['fti']['significant']
        flow_7d_sig = agg_result['flow_7d']['significant']

        if not fti_sig and not flow_7d_sig:
            print("Neither metric shows statistically significant predictive power (p > 0.05)")
            print("Recommendation: Neither FTI nor 7D Flow reliably predicts 7-day returns")
        elif fti_r2 > flow_7d_r2 and fti_sig:
            print("FTI provides better predictive power with statistical significance")
            print("Recommendation: Use FTI as the primary flow indicator")
        elif flow_7d_r2 > fti_r2 and flow_7d_sig:
            print("7D Flow provides better predictive power with statistical significance")
            print("Recommendation: Stick with 7D Flow; FTI adds complexity without benefit")
        else:
            print("Results are mixed or inconclusive")
            print("Recommendation: Default to simpler 7D Flow metric")

    # Per-subnet summary
    print()
    print("=" * 70)
    print("PER-SUBNET SUMMARY")
    print("=" * 70)

    fti_wins = sum(1 for r in all_results if r['fti']['r_squared'] > r['flow_7d']['r_squared'])
    flow_wins = len(all_results) - fti_wins

    print(f"FTI wins: {fti_wins} subnets ({100*fti_wins/len(all_results) if all_results else 0:.1f}%)")
    print(f"7D Flow wins: {flow_wins} subnets ({100*flow_wins/len(all_results) if all_results else 0:.1f}%)")

    # Average R² improvement
    if all_results:
        avg_fti_r2 = np.mean([r['fti']['r_squared'] for r in all_results])
        avg_flow_r2 = np.mean([r['flow_7d']['r_squared'] for r in all_results])
        print(f"\nAverage R² - FTI: {avg_fti_r2:.4f}, 7D Flow: {avg_flow_r2:.4f}")


if __name__ == "__main__":
    asyncio.run(run_backtest())
