"""Backtesting engine for viability scoring.

Replays viability scoring at historical points using SubnetSnapshot data,
then measures forward price performance per tier to validate scoring quality.
"""

import json
from bisect import bisect_left
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context

logger = structlog.get_logger()


@dataclass
class SubnetAtTime:
    """Reconstructed subnet state at a historical point in time."""
    netuid: int
    name: str
    pool_tao_reserve: float
    emission_share: float
    holder_count: int
    age_days: int
    alpha_price_tao: float
    taoflow_7d: float
    price_trend_7d: float
    max_drawdown: float
    startup_mode: bool


@dataclass
class BacktestSubnetResult:
    """Scoring and forward return for one subnet on one date."""
    netuid: int
    name: str
    tier: str
    score: Optional[float]
    hard_failure: bool
    failure_reasons: List[str]
    return_1d: Optional[float]
    return_3d: Optional[float]
    return_7d: Optional[float]


@dataclass
class BacktestDayResult:
    """Results for all subnets scored on one date."""
    date: str
    tier_counts: Dict[str, int]
    subnets: List[BacktestSubnetResult]


@dataclass
class TierSummary:
    """Aggregate metrics for one tier across all backtest dates."""
    count: int
    avg_return_1d: Optional[float]
    avg_return_3d: Optional[float]
    avg_return_7d: Optional[float]
    median_return_1d: Optional[float]
    median_return_3d: Optional[float]
    median_return_7d: Optional[float]
    win_rate_1d: Optional[float]
    win_rate_3d: Optional[float]
    win_rate_7d: Optional[float]


@dataclass
class BacktestResult:
    """Complete backtest output."""
    scoring_dates: List[str]
    data_range: Dict[str, str]
    summary: Dict[str, TierSummary]
    tier_separation: Dict[str, Optional[float]]
    daily_results: List[BacktestDayResult]


@dataclass
class PortfolioPeriod:
    """One rebalance period in the portfolio simulation."""
    date: str
    holdings: List[Dict[str, Any]]  # [{netuid, name, score, weight, entry_price, exit_price, return_pct}]
    period_return: float  # portfolio return for this period
    portfolio_value: float  # cumulative portfolio value at end of period
    in_root: bool  # True if no T1 subnets → held in root


@dataclass
class PortfolioSimResult:
    """Complete portfolio simulation output."""
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    total_return: float  # (final - initial) / initial
    num_periods: int
    periods_in_root: int
    equity_curve: List[Dict[str, Any]]  # [{date, value, return_pct, in_root, num_holdings}]
    periods: List[PortfolioPeriod]
    summary: Dict[str, Any]  # aggregate stats


class BacktestEngine:
    """Replays viability scoring against historical SubnetSnapshot data."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize with viability config (from DB, env, or custom override)."""
        if config:
            self.min_tao_reserve = float(config.get("min_tao_reserve", 500))
            self.min_emission_share = float(config.get("min_emission_share", 0.002))
            self.min_age_days = int(config.get("min_age_days", 60))
            self.min_holders = int(config.get("min_holders", 20))
            self.max_drawdown = float(config.get("max_drawdown_30d", 0.40))
            self.max_negative_flow_ratio = float(config.get("max_negative_flow_ratio", 0.30))
            self.weights = {
                "tao_reserve": float(config.get("weight_tao_reserve", 0.25)),
                "net_flow_7d": float(config.get("weight_net_flow_7d", 0.25)),
                "emission_share": float(config.get("weight_emission_share", 0.15)),
                "price_trend_7d": float(config.get("weight_price_trend_7d", 0.15)),
                "subnet_age": float(config.get("weight_subnet_age", 0.10)),
                "max_drawdown_30d": float(config.get("weight_max_drawdown_30d", 0.10)),
            }
            self.tier_1_min = int(config.get("tier_1_min", 75))
            self.tier_2_min = int(config.get("tier_2_min", 55))
            self.tier_3_min = int(config.get("tier_3_min", 40))
            self.age_cap = int(config.get("age_cap_days", 365))
        else:
            self._load_active_config()

    def _load_active_config(self):
        """Load from env defaults (synchronous init fallback)."""
        from app.core.config import get_settings
        settings = get_settings()
        self.min_tao_reserve = float(settings.viability_min_tao_reserve)
        self.min_emission_share = float(settings.viability_min_emission_share)
        self.min_age_days = settings.viability_min_age_days
        self.min_holders = settings.viability_min_holders
        self.max_drawdown = float(settings.viability_max_drawdown_30d)
        self.max_negative_flow_ratio = float(settings.viability_max_negative_flow_ratio)
        self.weights = {
            "tao_reserve": float(settings.viability_weight_tao_reserve),
            "net_flow_7d": float(settings.viability_weight_net_flow_7d),
            "emission_share": float(settings.viability_weight_emission_share),
            "price_trend_7d": float(settings.viability_weight_price_trend_7d),
            "subnet_age": float(settings.viability_weight_subnet_age),
            "max_drawdown_30d": float(settings.viability_weight_max_drawdown_30d),
        }
        self.tier_1_min = settings.viability_tier_1_min
        self.tier_2_min = settings.viability_tier_2_min
        self.tier_3_min = settings.viability_tier_3_min
        self.age_cap = settings.viability_age_cap_days

    async def load_active_config_from_db(self):
        """Load from DB if active config exists, else env defaults."""
        from app.models.viability_config import ViabilityConfig

        async with get_db_context() as db:
            stmt = (
                select(ViabilityConfig)
                .where(ViabilityConfig.is_active == True)  # noqa: E712
                .order_by(ViabilityConfig.updated_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()

        if row is not None:
            self.min_tao_reserve = float(row.min_tao_reserve)
            self.min_emission_share = float(row.min_emission_share)
            self.min_age_days = row.min_age_days
            self.min_holders = row.min_holders
            self.max_drawdown = float(row.max_drawdown_30d)
            self.max_negative_flow_ratio = float(row.max_negative_flow_ratio)
            self.weights = {
                "tao_reserve": float(row.weight_tao_reserve),
                "net_flow_7d": float(row.weight_net_flow_7d),
                "emission_share": float(row.weight_emission_share),
                "price_trend_7d": float(row.weight_price_trend_7d),
                "subnet_age": float(row.weight_subnet_age),
                "max_drawdown_30d": float(row.weight_max_drawdown_30d),
            }
            self.tier_1_min = row.tier_1_min
            self.tier_2_min = row.tier_2_min
            self.tier_3_min = row.tier_3_min
            self.age_cap = row.age_cap_days

    # ==================== Historical Data Reconstruction ====================

    async def _get_snapshots_at_time(
        self, db: AsyncSession, target_time: datetime
    ) -> Dict[int, Any]:
        """Get the most recent snapshot for each subnet at or before target_time."""
        from app.models.subnet import SubnetSnapshot

        # Subquery: max timestamp per netuid at or before target
        sub = (
            select(
                SubnetSnapshot.netuid,
                func.max(SubnetSnapshot.timestamp).label("max_ts"),
            )
            .where(SubnetSnapshot.timestamp <= target_time)
            .group_by(SubnetSnapshot.netuid)
            .subquery()
        )

        stmt = (
            select(SubnetSnapshot)
            .join(
                sub,
                (SubnetSnapshot.netuid == sub.c.netuid)
                & (SubnetSnapshot.timestamp == sub.c.max_ts),
            )
        )
        result = await db.execute(stmt)
        snapshots = result.scalars().all()
        return {s.netuid: s for s in snapshots}

    async def _get_price_at_time(
        self, db: AsyncSession, netuid: int, target_time: datetime
    ) -> Optional[float]:
        """Get alpha price closest to target_time."""
        from app.models.subnet import SubnetSnapshot

        stmt = (
            select(SubnetSnapshot.alpha_price_tao)
            .where(SubnetSnapshot.netuid == netuid)
            .where(SubnetSnapshot.timestamp <= target_time)
            .order_by(SubnetSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None and float(row) > 0:
            return float(row)
        return None

    async def _compute_price_trend(
        self, db: AsyncSession, netuid: int, target_time: datetime, days: int = 7
    ) -> float:
        """Compute price change over `days` ending at target_time."""
        current_price = await self._get_price_at_time(db, netuid, target_time)
        past_price = await self._get_price_at_time(
            db, netuid, target_time - timedelta(days=days)
        )
        if current_price and past_price and past_price > 0:
            return (current_price - past_price) / past_price
        return 0.0

    async def _compute_max_drawdown(
        self, db: AsyncSession, netuid: int, target_time: datetime, days: int = 30
    ) -> float:
        """Compute max drawdown over `days` ending at target_time."""
        from app.models.subnet import SubnetSnapshot

        start = target_time - timedelta(days=days)
        stmt = (
            select(SubnetSnapshot.alpha_price_tao)
            .where(SubnetSnapshot.netuid == netuid)
            .where(SubnetSnapshot.timestamp >= start)
            .where(SubnetSnapshot.timestamp <= target_time)
            .order_by(SubnetSnapshot.timestamp.asc())
        )
        result = await db.execute(stmt)
        prices = [float(r[0]) for r in result.all() if r[0] and float(r[0]) > 0]

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

    async def _compute_taoflow_7d(
        self, db: AsyncSession, netuid: int, target_time: datetime
    ) -> float:
        """Approximate 7d TAO flow from pool reserve changes."""
        from app.models.subnet import SubnetSnapshot

        # Current reserve
        stmt = (
            select(SubnetSnapshot.pool_tao_reserve)
            .where(SubnetSnapshot.netuid == netuid)
            .where(SubnetSnapshot.timestamp <= target_time)
            .order_by(SubnetSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        current_reserve = result.scalar_one_or_none()

        # Reserve 7 days ago
        past_time = target_time - timedelta(days=7)
        stmt = (
            select(SubnetSnapshot.pool_tao_reserve)
            .where(SubnetSnapshot.netuid == netuid)
            .where(SubnetSnapshot.timestamp <= past_time)
            .order_by(SubnetSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        past_reserve = result.scalar_one_or_none()

        if current_reserve is not None and past_reserve is not None:
            return float(current_reserve) - float(past_reserve)
        return 0.0

    async def _reconstruct_subnets_at_time(
        self, db: AsyncSession, target_time: datetime
    ) -> List[SubnetAtTime]:
        """Reconstruct all subnet states at a historical point in time."""
        from app.models.subnet import Subnet

        # Get registration dates for age calculation
        stmt = select(Subnet.netuid, Subnet.name, Subnet.registered_at)
        result = await db.execute(stmt)
        subnet_info = {r[0]: (r[1], r[2]) for r in result.all()}

        # Get latest snapshots at target time
        snapshots = await self._get_snapshots_at_time(db, target_time)

        subnets: List[SubnetAtTime] = []
        for netuid, snap in snapshots.items():
            if netuid == 0:
                continue  # skip root subnet

            info = subnet_info.get(netuid)
            if info is None:
                continue
            name, registered_at = info

            # Compute age
            age_days = 0
            if registered_at:
                age_days = max(0, (target_time - registered_at).days)

            # Compute derived metrics
            price_trend = await self._compute_price_trend(db, netuid, target_time)
            max_dd = await self._compute_max_drawdown(db, netuid, target_time)
            taoflow = await self._compute_taoflow_7d(db, netuid, target_time)

            subnets.append(SubnetAtTime(
                netuid=netuid,
                name=name,
                pool_tao_reserve=float(snap.pool_tao_reserve or 0),
                emission_share=float(snap.emission_share or 0),
                holder_count=snap.holder_count or 0,
                age_days=age_days,
                alpha_price_tao=float(snap.alpha_price_tao or 0),
                taoflow_7d=taoflow,
                price_trend_7d=price_trend,
                max_drawdown=max_dd,
                startup_mode=False,  # Not available in snapshots
            ))

        return subnets

    # ==================== Scoring ====================

    def _check_hard_failures(self, subnet: SubnetAtTime) -> Tuple[bool, List[str]]:
        """Run hard failure checks against reconstructed subnet.

        Metrics with sentinel value 0 (unavailable in historical backfill data)
        are skipped rather than treated as failures.
        """
        failures: List[str] = []

        if subnet.pool_tao_reserve < self.min_tao_reserve:
            failures.append(f"TAO reserve {subnet.pool_tao_reserve:.0f} < {self.min_tao_reserve}")
        if subnet.emission_share < self.min_emission_share:
            failures.append(f"Emission share {subnet.emission_share:.4%} < {self.min_emission_share:.1%}")
        if subnet.age_days < self.min_age_days:
            failures.append(f"Age {subnet.age_days}d < {self.min_age_days}d")
        # Skip holder check when data unavailable (backfill sets to 0)
        if subnet.holder_count > 0 and subnet.holder_count < self.min_holders:
            failures.append(f"Holders {subnet.holder_count} < {self.min_holders}")
        if subnet.max_drawdown > self.max_drawdown:
            failures.append(f"30d drawdown {subnet.max_drawdown:.1%} > {self.max_drawdown:.0%}")
        if subnet.startup_mode:
            failures.append("Startup mode")
        if subnet.pool_tao_reserve > 0:
            flow_ratio = subnet.taoflow_7d / subnet.pool_tao_reserve
            if flow_ratio < -self.max_negative_flow_ratio:
                failures.append(f"7d outflow {flow_ratio:.1%} of reserve")

        return (len(failures) == 0, failures)

    def _assign_tier(self, score: float) -> str:
        if score >= self.tier_1_min:
            return "tier_1"
        elif score >= self.tier_2_min:
            return "tier_2"
        elif score >= self.tier_3_min:
            return "tier_3"
        return "tier_4"

    @staticmethod
    def _percentile_rank(values: List[float], target: float) -> float:
        if len(values) <= 1:
            return 50.0
        sorted_vals = sorted(values)
        rank = bisect_left(sorted_vals, target)
        return (rank / (len(sorted_vals) - 1)) * 100.0

    @staticmethod
    def _percentile_rank_inverted(values: List[float], target: float) -> float:
        """Inverted percentile: lower values get higher percentile (e.g., drawdown)."""
        if len(values) <= 1:
            return 50.0
        return 100.0 - BacktestEngine._percentile_rank(values, target)

    def _score_subnets(
        self, subnets: List[SubnetAtTime]
    ) -> List[Tuple[SubnetAtTime, str, Optional[float], bool, List[str]]]:
        """Score a set of subnets. Returns list of (subnet, tier, score, hard_fail, reasons)."""
        passing: List[Tuple[SubnetAtTime, Dict[str, float]]] = []
        failing: List[Tuple[SubnetAtTime, List[str]]] = []

        for sn in subnets:
            passed, reasons = self._check_hard_failures(sn)
            if passed:
                passing.append((sn, {
                    "tao_reserve": sn.pool_tao_reserve,
                    "net_flow_7d": sn.taoflow_7d,
                    "emission_share": sn.emission_share,
                    "price_trend_7d": sn.price_trend_7d,
                    "subnet_age": min(sn.age_days, self.age_cap),
                    "max_drawdown_30d": sn.max_drawdown,
                }))
            else:
                failing.append((sn, reasons))

        results: List[Tuple[SubnetAtTime, str, Optional[float], bool, List[str]]] = []

        # Hard failures → tier_4
        for sn, reasons in failing:
            results.append((sn, "tier_4", None, True, reasons))

        if not passing:
            return results

        # Percentile ranks
        raw_metrics = [m for _, m in passing]
        normal_metrics = ["tao_reserve", "net_flow_7d", "emission_share", "price_trend_7d", "subnet_age"]
        for metric_name in normal_metrics:
            values = [m[metric_name] for m in raw_metrics]
            for m in raw_metrics:
                m[f"{metric_name}_pctile"] = self._percentile_rank(values, m[metric_name])

        dd_values = [m["max_drawdown_30d"] for m in raw_metrics]
        for m in raw_metrics:
            m["max_drawdown_30d_pctile"] = self._percentile_rank_inverted(
                dd_values, m["max_drawdown_30d"]
            )

        # Weighted composite + tier
        for (sn, m) in passing:
            composite = sum(
                m[f"{k}_pctile"] * w for k, w in self.weights.items()
            )
            tier = self._assign_tier(composite)
            results.append((sn, tier, round(composite, 1), False, []))

        return results

    # ==================== Forward Returns ====================

    async def _compute_forward_return(
        self, db: AsyncSession, netuid: int, base_price: float,
        target_time: datetime, days: int,
    ) -> Optional[float]:
        """Compute forward return over `days` from target_time."""
        future_price = await self._get_price_at_time(
            db, netuid, target_time + timedelta(days=days)
        )
        if future_price and base_price > 0:
            return (future_price - base_price) / base_price
        return None

    # ==================== Main Backtest ====================

    async def run(
        self,
        interval_days: int = 1,
        forward_horizons: Optional[List[int]] = None,
        include_subnet_detail: bool = False,
    ) -> BacktestResult:
        """Run backtesting over available historical data.

        Args:
            interval_days: Days between scoring dates.
            forward_horizons: Forward return horizons in days (default [1, 3, 7]).
        """
        if forward_horizons is None:
            forward_horizons = [1, 3, 7]

        # Load active config from DB before running
        await self.load_active_config_from_db()

        async with get_db_context() as db:
            from app.models.subnet import SubnetSnapshot

            # Determine data range
            result = await db.execute(
                select(
                    func.min(SubnetSnapshot.timestamp),
                    func.max(SubnetSnapshot.timestamp),
                )
            )
            row = result.one()
            data_start, data_end = row[0], row[1]

            if not data_start or not data_end:
                logger.warning("No snapshot data available for backtesting")
                return BacktestResult(
                    scoring_dates=[],
                    data_range={"start": "", "end": ""},
                    summary={},
                    tier_separation={},
                    daily_results=[],
                )

            logger.info(
                "Backtest starting",
                data_start=str(data_start),
                data_end=str(data_end),
                interval_days=interval_days,
            )

            # Generate scoring dates (skip the very first few days to allow lookback)
            # Start at data_start + 2 days (minimum for price trend)
            scoring_start = data_start + timedelta(days=2)
            scoring_dates: List[datetime] = []
            current = scoring_start
            while current <= data_end:
                scoring_dates.append(current)
                current += timedelta(days=interval_days)

            daily_results: List[BacktestDayResult] = []
            all_tier_returns: Dict[str, List[Dict[str, Optional[float]]]] = {
                "tier_1": [], "tier_2": [], "tier_3": [], "tier_4": []
            }

            for score_date in scoring_dates:
                # Reconstruct subnet state
                subnets = await self._reconstruct_subnets_at_time(db, score_date)

                if not subnets:
                    continue

                # Score
                scored = self._score_subnets(subnets)

                # Compute forward returns
                subnet_results: List[BacktestSubnetResult] = []
                for sn, tier, score, hard_fail, reasons in scored:
                    returns: Dict[str, Optional[float]] = {}
                    for h in forward_horizons:
                        ret = await self._compute_forward_return(
                            db, sn.netuid, sn.alpha_price_tao, score_date, h
                        )
                        returns[f"return_{h}d"] = ret

                    subnet_results.append(BacktestSubnetResult(
                        netuid=sn.netuid,
                        name=sn.name,
                        tier=tier,
                        score=score,
                        hard_failure=hard_fail,
                        failure_reasons=reasons,
                        return_1d=returns.get("return_1d"),
                        return_3d=returns.get("return_3d"),
                        return_7d=returns.get("return_7d"),
                    ))

                    all_tier_returns[tier].append(returns)

                # Tier counts
                tier_counts: Dict[str, int] = {}
                for t in ["tier_1", "tier_2", "tier_3", "tier_4"]:
                    tier_counts[t] = sum(1 for r in subnet_results if r.tier == t)

                daily_results.append(BacktestDayResult(
                    date=score_date.strftime("%Y-%m-%d"),
                    tier_counts=tier_counts,
                    subnets=subnet_results,
                ))

            # Build tier summaries
            summary: Dict[str, TierSummary] = {}
            for tier_name in ["tier_1", "tier_2", "tier_3", "tier_4"]:
                entries = all_tier_returns[tier_name]
                summary[tier_name] = self._build_tier_summary(entries)

            # Tier separation (median-based — robust to outliers)
            tier_separation: Dict[str, Optional[float]] = {}
            for h in forward_horizons:
                # Helper to get median for a tier at a horizon
                def _get_median(tier: str, horizon: int) -> Optional[float]:
                    s = summary[tier]
                    if horizon == 1:
                        return s.median_return_1d
                    elif horizon == 3:
                        return s.median_return_3d
                    return s.median_return_7d

                def _get_win(tier: str, horizon: int) -> Optional[float]:
                    s = summary[tier]
                    if horizon == 1:
                        return s.win_rate_1d
                    elif horizon == 3:
                        return s.win_rate_3d
                    return s.win_rate_7d

                t1_med = _get_median("tier_1", h)
                t4_med = _get_median("tier_4", h)
                t1_win = _get_win("tier_1", h)
                t4_win = _get_win("tier_4", h)

                # Median return separation
                if t1_med is not None and t4_med is not None:
                    tier_separation[f"tier1_vs_tier4_median_{h}d"] = round(t1_med - t4_med, 6)
                else:
                    tier_separation[f"tier1_vs_tier4_median_{h}d"] = None

                # Win rate separation
                if t1_win is not None and t4_win is not None:
                    tier_separation[f"tier1_vs_tier4_winrate_{h}d"] = round(t1_win - t4_win, 4)
                else:
                    tier_separation[f"tier1_vs_tier4_winrate_{h}d"] = None

            # Hard failure rate
            total_entries = sum(summary[t].count for t in ["tier_1", "tier_2", "tier_3", "tier_4"])
            hard_fail_count = sum(
                1 for dr in daily_results for sr in dr.subnets if sr.hard_failure
            ) if include_subnet_detail else summary["tier_4"].count
            if total_entries > 0:
                tier_separation["hard_failure_rate"] = round(hard_fail_count / total_entries, 4)
            else:
                tier_separation["hard_failure_rate"] = None

            final_daily = []
            for dr in daily_results:
                final_daily.append(BacktestDayResult(
                    date=dr.date,
                    tier_counts=dr.tier_counts,
                    subnets=dr.subnets if include_subnet_detail else [],
                ))

            return BacktestResult(
                scoring_dates=[d.strftime("%Y-%m-%d") for d in scoring_dates],
                data_range={
                    "start": data_start.strftime("%Y-%m-%d"),
                    "end": data_end.strftime("%Y-%m-%d"),
                },
                summary={k: asdict(v) for k, v in summary.items()},
                tier_separation=tier_separation,
                daily_results=final_daily,
            )

    def _build_tier_summary(
        self, entries: List[Dict[str, Optional[float]]]
    ) -> TierSummary:
        """Build aggregate metrics for one tier."""

        def avg_of(key: str) -> Optional[float]:
            vals = [e[key] for e in entries if e.get(key) is not None]
            return round(sum(vals) / len(vals), 6) if vals else None

        def median_of(key: str) -> Optional[float]:
            vals = sorted([e[key] for e in entries if e.get(key) is not None])
            if not vals:
                return None
            mid = len(vals) // 2
            if len(vals) % 2 == 0:
                return round((vals[mid - 1] + vals[mid]) / 2, 6)
            return round(vals[mid], 6)

        def win_rate(key: str) -> Optional[float]:
            vals = [e[key] for e in entries if e.get(key) is not None]
            if not vals:
                return None
            winners = sum(1 for v in vals if v > 0)
            return round(winners / len(vals), 4)

        return TierSummary(
            count=len(entries),
            avg_return_1d=avg_of("return_1d"),
            avg_return_3d=avg_of("return_3d"),
            avg_return_7d=avg_of("return_7d"),
            median_return_1d=median_of("return_1d"),
            median_return_3d=median_of("return_3d"),
            median_return_7d=median_of("return_7d"),
            win_rate_1d=win_rate("return_1d"),
            win_rate_3d=win_rate("return_3d"),
            win_rate_7d=win_rate("return_7d"),
        )

    # ==================== Portfolio Simulation ====================

    async def simulate_portfolio(
        self,
        interval_days: int = 3,
        initial_capital: float = 100.0,
        target_tier: str = "tier_1",
        start_date: Optional[str] = None,
        tier_weights: Optional[Dict[str, float]] = None,
    ) -> PortfolioSimResult:
        """Simulate a portfolio that holds qualifying subnets across one or more tiers.

        Supports two modes:
        - **Single-tier** (legacy): pass `target_tier` — equal-weight across all subnets in that tier.
        - **Multi-tier weighted**: pass `tier_weights` dict (e.g. {"tier_1": 0.4, "tier_2": 0.3, "tier_3": 0.3}).
          Each tier gets its weight share. Within each tier, subnets are equal-weighted.
          If a tier has no qualifying subnets, its allocation is parked in root (0% return).

        At each rebalance date:
        1. Score all subnets using current viability config.
        2. Select subnets in each target tier.
        3. Allocate portfolio: tier weight × (1/N per subnet in that tier).
        4. Hold until next rebalance date, compute returns from price changes.

        Args:
            interval_days: Days between rebalances (e.g. 3).
            initial_capital: Starting TAO (default 100).
            target_tier: Which single tier to hold (default "tier_1"). Ignored if tier_weights given.
            start_date: ISO date string to start sim (default: 6 months ago or data start).
            tier_weights: Dict mapping tier names to portfolio weight fractions (must sum to ~1.0).
        """
        await self.load_active_config_from_db()

        async with get_db_context() as db:
            from app.models.subnet import SubnetSnapshot

            # Data range
            result = await db.execute(
                select(
                    func.min(SubnetSnapshot.timestamp),
                    func.max(SubnetSnapshot.timestamp),
                )
            )
            row = result.one()
            data_start, data_end = row[0], row[1]

            if not data_start or not data_end:
                return PortfolioSimResult(
                    start_date="", end_date="", initial_capital=initial_capital,
                    final_value=initial_capital, total_return=0.0, num_periods=0,
                    periods_in_root=0, equity_curve=[], periods=[], summary={},
                )

            # Determine sim start
            if start_date:
                sim_start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            else:
                # Default: 6 months ago or data_start + 30 days (need lookback)
                six_months_ago = data_end - timedelta(days=180)
                sim_start = max(data_start + timedelta(days=30), six_months_ago)

            # Generate rebalance dates
            rebalance_dates: List[datetime] = []
            current = sim_start
            while current <= data_end - timedelta(days=interval_days):
                rebalance_dates.append(current)
                current += timedelta(days=interval_days)

            if not rebalance_dates:
                return PortfolioSimResult(
                    start_date=sim_start.strftime("%Y-%m-%d"),
                    end_date=data_end.strftime("%Y-%m-%d"),
                    initial_capital=initial_capital, final_value=initial_capital,
                    total_return=0.0, num_periods=0, periods_in_root=0,
                    equity_curve=[], periods=[], summary={},
                )

            portfolio_value = initial_capital
            periods: List[PortfolioPeriod] = []
            equity_curve: List[Dict[str, Any]] = []
            periods_in_root = 0
            winning_periods = 0
            all_period_returns: List[float] = []

            # Initial point
            equity_curve.append({
                "date": rebalance_dates[0].strftime("%Y-%m-%d"),
                "value": round(portfolio_value, 4),
                "return_pct": 0.0,
                "in_root": False,
                "num_holdings": 0,
            })

            for i, rebal_date in enumerate(rebalance_dates):
                next_date = (
                    rebalance_dates[i + 1]
                    if i + 1 < len(rebalance_dates)
                    else rebal_date + timedelta(days=interval_days)
                )

                # Score subnets at this date
                subnets = await self._reconstruct_subnets_at_time(db, rebal_date)
                if not subnets:
                    # No data → hold in root
                    periods_in_root += 1
                    period_return = 0.0
                    all_period_returns.append(period_return)
                    periods.append(PortfolioPeriod(
                        date=rebal_date.strftime("%Y-%m-%d"),
                        holdings=[], period_return=0.0,
                        portfolio_value=round(portfolio_value, 4),
                        in_root=True,
                    ))
                    equity_curve.append({
                        "date": next_date.strftime("%Y-%m-%d"),
                        "value": round(portfolio_value, 4),
                        "return_pct": 0.0,
                        "in_root": True,
                        "num_holdings": 0,
                    })
                    continue

                scored = self._score_subnets(subnets)

                # Build per-tier holdings map
                # effective_weights: the tier_weights dict, or single-tier mode
                if tier_weights:
                    effective_weights = tier_weights
                else:
                    effective_weights = {target_tier: 1.0}

                # Group scored subnets by their tier (only tiers we care about)
                tier_subnets: Dict[str, List[Tuple[SubnetAtTime, Optional[float]]]] = {}
                for sn, tier, score, _hf, _r in scored:
                    if tier in effective_weights:
                        tier_subnets.setdefault(tier, []).append((sn, score))

                # Compute total active weight (tiers that have qualifying subnets)
                # Tiers with no qualifying subnets → that portion earns 0% (root)
                total_holdings = sum(len(subs) for subs in tier_subnets.values())

                if total_holdings == 0:
                    # No qualifying subnets in any tier → park in root
                    periods_in_root += 1
                    period_return = 0.0
                    all_period_returns.append(period_return)
                    periods.append(PortfolioPeriod(
                        date=rebal_date.strftime("%Y-%m-%d"),
                        holdings=[], period_return=0.0,
                        portfolio_value=round(portfolio_value, 4),
                        in_root=True,
                    ))
                    equity_curve.append({
                        "date": next_date.strftime("%Y-%m-%d"),
                        "value": round(portfolio_value, 4),
                        "return_pct": 0.0,
                        "in_root": True,
                        "num_holdings": 0,
                    })
                    continue

                # Compute per-subnet weight:
                # Each tier gets its designated weight share.
                # Within the tier, equal-weight across qualifying subnets.
                # If a tier has 0 qualifying subnets, its weight goes to root (0% return).
                holdings_detail: List[Dict[str, Any]] = []
                weighted_return = 0.0
                root_weight = 0.0

                for tier_name, tier_w in effective_weights.items():
                    subs = tier_subnets.get(tier_name, [])
                    if not subs:
                        root_weight += tier_w
                        continue
                    per_subnet_weight = tier_w / len(subs)
                    for sn, score in subs:
                        entry_price = sn.alpha_price_tao
                        exit_price_val = await self._get_price_at_time(
                            db, sn.netuid, next_date
                        )

                        if exit_price_val and entry_price > 0:
                            ret = (exit_price_val - entry_price) / entry_price
                        else:
                            ret = 0.0

                        weighted_return += per_subnet_weight * ret
                        holdings_detail.append({
                            "netuid": sn.netuid,
                            "name": sn.name,
                            "tier": tier_name,
                            "score": round(score, 1) if score else None,
                            "weight": round(per_subnet_weight, 4),
                            "entry_price": round(entry_price, 9),
                            "exit_price": round(exit_price_val, 9) if exit_price_val else None,
                            "return_pct": round(ret, 6),
                        })

                # root_weight portion earns 0% — already excluded from weighted_return

                # Apply return to portfolio
                portfolio_value *= (1 + weighted_return)
                period_return = weighted_return
                all_period_returns.append(period_return)
                if period_return > 0:
                    winning_periods += 1

                periods.append(PortfolioPeriod(
                    date=rebal_date.strftime("%Y-%m-%d"),
                    holdings=holdings_detail,
                    period_return=round(period_return, 6),
                    portfolio_value=round(portfolio_value, 4),
                    in_root=False,
                ))

                equity_curve.append({
                    "date": next_date.strftime("%Y-%m-%d"),
                    "value": round(portfolio_value, 4),
                    "return_pct": round(period_return, 6),
                    "in_root": False,
                    "num_holdings": total_holdings,
                })

            # Summary stats
            total_return = (portfolio_value - initial_capital) / initial_capital
            avg_period_return = sum(all_period_returns) / len(all_period_returns) if all_period_returns else 0.0
            sorted_returns = sorted(all_period_returns)
            median_period_return = (
                sorted_returns[len(sorted_returns) // 2] if sorted_returns else 0.0
            )
            max_drawdown = self._compute_equity_drawdown(equity_curve)

            summary = {
                "total_return_pct": round(total_return, 6),
                "avg_period_return_pct": round(avg_period_return, 6),
                "median_period_return_pct": round(median_period_return, 6),
                "win_rate": round(winning_periods / max(len(all_period_returns), 1), 4),
                "max_drawdown_pct": round(max_drawdown, 6),
                "best_period": round(max(all_period_returns), 6) if all_period_returns else 0.0,
                "worst_period": round(min(all_period_returns), 6) if all_period_returns else 0.0,
                "avg_holdings_per_period": round(
                    sum(len(p.holdings) for p in periods) / max(len(periods), 1), 1
                ),
                "tier_weights": tier_weights if tier_weights else {target_tier: 1.0},
            }

            logger.info(
                "Portfolio simulation complete",
                total_return=f"{total_return:.2%}",
                periods=len(periods),
                in_root=periods_in_root,
                max_dd=f"{max_drawdown:.2%}",
            )

            return PortfolioSimResult(
                start_date=rebalance_dates[0].strftime("%Y-%m-%d"),
                end_date=(rebalance_dates[-1] + timedelta(days=interval_days)).strftime("%Y-%m-%d"),
                initial_capital=initial_capital,
                final_value=round(portfolio_value, 4),
                total_return=round(total_return, 6),
                num_periods=len(periods),
                periods_in_root=periods_in_root,
                equity_curve=equity_curve,
                periods=periods,
                summary=summary,
            )

    @staticmethod
    def _compute_equity_drawdown(equity_curve: List[Dict[str, Any]]) -> float:
        """Compute max drawdown from equity curve."""
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]["value"]
        max_dd = 0.0
        for point in equity_curve:
            val = point["value"]
            if val > peak:
                peak = val
            if peak > 0:
                dd = (peak - val) / peak
                if dd > max_dd:
                    max_dd = dd
        return max_dd
