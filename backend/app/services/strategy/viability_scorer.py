"""Viability scoring system for subnet filtering.

Implements a two-stage filter:
1. Hard failures (7 binary pass/fail checks)
2. Percentile-rank scoring (6 weighted metrics) with tier assignment

Only subnets passing all hard failures receive a composite score.
"""

import json
from bisect import bisect_left
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context

logger = structlog.get_logger()


class ViabilityTier(str, Enum):
    TIER_1 = "tier_1"  # 75-100: Prime candidates
    TIER_2 = "tier_2"  # 55-74: Eligible
    TIER_3 = "tier_3"  # 40-54: Watchlist only
    TIER_4 = "tier_4"  # 0-39: Excluded


@dataclass
class HardFailureResult:
    passed: bool
    failures: List[str]


@dataclass
class ViabilityFactors:
    """Per-metric breakdown for transparency."""
    tao_reserve_raw: float
    tao_reserve_percentile: float
    tao_reserve_weighted: float

    net_flow_7d_raw: float
    net_flow_7d_percentile: float
    net_flow_7d_weighted: float

    emission_share_raw: float
    emission_share_percentile: float
    emission_share_weighted: float

    price_trend_7d_raw: float
    price_trend_7d_percentile: float
    price_trend_7d_weighted: float

    subnet_age_raw: int
    subnet_age_percentile: float
    subnet_age_weighted: float

    max_drawdown_30d_raw: float
    max_drawdown_30d_percentile: float
    max_drawdown_30d_weighted: float


@dataclass
class ViabilityResult:
    netuid: int
    name: str
    hard_failure: HardFailureResult
    score: Optional[float]  # 0-100, None if hard failure
    tier: ViabilityTier
    factors: Optional[ViabilityFactors]


class ViabilityScorer:
    """Scores subnets on viability using hard failures and percentile-rank metrics."""

    def __init__(self):
        self._load_from_env()

    def _load_from_env(self):
        """Load config from environment-based defaults."""
        settings = get_settings()
        self.min_tao_reserve = settings.viability_min_tao_reserve
        self.min_emission_share = settings.viability_min_emission_share
        self.min_age_days = settings.viability_min_age_days
        self.min_holders = settings.viability_min_holders
        self.max_drawdown = settings.viability_max_drawdown_30d
        self.max_negative_flow_ratio = settings.viability_max_negative_flow_ratio

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

    def _load_from_db_row(self, row):
        """Load config from a ViabilityConfig database row."""
        self.min_tao_reserve = row.min_tao_reserve
        self.min_emission_share = row.min_emission_share
        self.min_age_days = row.min_age_days
        self.min_holders = row.min_holders
        self.max_drawdown = row.max_drawdown_30d
        self.max_negative_flow_ratio = row.max_negative_flow_ratio

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

    async def _reload_config(self, db: AsyncSession):
        """Reload config from database if an active config exists, else use env defaults."""
        from app.models.viability_config import ViabilityConfig

        stmt = (
            select(ViabilityConfig)
            .where(ViabilityConfig.is_active == True)  # noqa: E712
            .order_by(ViabilityConfig.updated_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is not None:
            self._load_from_db_row(row)
            logger.info("Viability config loaded from database", config_id=row.id, config_name=row.config_name)
        else:
            self._load_from_env()
            logger.info("Viability config loaded from env defaults")

    async def compute_max_drawdown_30d(self, db: AsyncSession, netuid: int) -> float:
        """Compute 30d rolling max drawdown from SubnetSnapshot prices."""
        from app.models.subnet import SubnetSnapshot

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = (
            select(SubnetSnapshot.alpha_price_tao)
            .where(SubnetSnapshot.netuid == netuid)
            .where(SubnetSnapshot.timestamp >= cutoff)
            .order_by(SubnetSnapshot.timestamp.asc())
        )
        result = await db.execute(stmt)
        prices = [float(row[0]) for row in result.all() if row[0] and float(row[0]) > 0]

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

    def check_hard_failures(
        self,
        subnet: Any,
        drawdown: float,
    ) -> HardFailureResult:
        """Run 7 binary pass/fail checks."""
        failures: List[str] = []

        tao_reserve = float(subnet.pool_tao_reserve or 0)
        emission_share = float(subnet.emission_share or 0)
        age_days = subnet.age_days or 0
        holder_count = subnet.holder_count or 0
        taoflow_7d = float(subnet.taoflow_7d or 0)
        startup = subnet.startup_mode

        # 1. TAO reserve
        if tao_reserve < float(self.min_tao_reserve):
            failures.append(f"TAO reserve {tao_reserve:.0f} < {self.min_tao_reserve}")

        # 2. Emission share
        if emission_share < float(self.min_emission_share):
            failures.append(f"Emission share {emission_share:.4%} < {self.min_emission_share:.1%}")

        # 3. Age
        if age_days < self.min_age_days:
            failures.append(f"Age {age_days}d < {self.min_age_days}d")

        # 4. Holders
        if holder_count < self.min_holders:
            failures.append(f"Holders {holder_count} < {self.min_holders}")

        # 5. Max drawdown
        if drawdown > float(self.max_drawdown):
            failures.append(f"30d drawdown {drawdown:.1%} > {self.max_drawdown:.0%}")

        # 6. Startup mode
        if startup is True:
            failures.append("Subnet in startup mode")

        # 7. Severe outflow (7d flow < -50% of reserve)
        if tao_reserve > 0:
            flow_ratio = taoflow_7d / tao_reserve
            if flow_ratio < -float(self.max_negative_flow_ratio):
                failures.append(
                    f"7d outflow {flow_ratio:.1%} of reserve (< -{self.max_negative_flow_ratio:.0%})"
                )

        return HardFailureResult(passed=len(failures) == 0, failures=failures)

    def _assign_tier(self, score: float) -> ViabilityTier:
        if score >= self.tier_1_min:
            return ViabilityTier.TIER_1
        elif score >= self.tier_2_min:
            return ViabilityTier.TIER_2
        elif score >= self.tier_3_min:
            return ViabilityTier.TIER_3
        else:
            return ViabilityTier.TIER_4

    @staticmethod
    def _percentile_rank(values: List[float], target: float) -> float:
        """Compute percentile rank (0-100) of target within sorted values."""
        if len(values) <= 1:
            return 50.0
        sorted_vals = sorted(values)
        rank = bisect_left(sorted_vals, target)
        return (rank / (len(sorted_vals) - 1)) * 100.0

    @staticmethod
    def _percentile_rank_inverted(values: List[float], target: float) -> float:
        """Inverted percentile: lower values get higher percentile."""
        if len(values) <= 1:
            return 50.0
        sorted_desc = sorted(values, reverse=True)
        rank = bisect_left(sorted_desc, target)
        # In descending sort, position 0 = highest value = lowest percentile
        # We want: lowest original value → highest percentile
        return (rank / (len(sorted_desc) - 1)) * 100.0

    async def score_all_subnets(self) -> List[ViabilityResult]:
        """Main scoring: hard failures → percentile rank → weighted composite → tiers."""
        from app.models.subnet import Subnet

        async with get_db_context() as db:
            # Reload config from DB (or env defaults) before each scoring run
            await self._reload_config(db)

            # Fetch all subnets (exclude SN0 root)
            stmt = select(Subnet).where(Subnet.netuid != 0)
            result = await db.execute(stmt)
            all_subnets = list(result.scalars().all())

            logger.info("Viability scoring started", total_subnets=len(all_subnets))

            # Phase 1: compute drawdown for all subnets and run hard failures
            passing: List[Tuple[Any, float]] = []  # (subnet, drawdown)
            failing: List[ViabilityResult] = []

            for subnet in all_subnets:
                drawdown = await self.compute_max_drawdown_30d(db, subnet.netuid)

                hard_result = self.check_hard_failures(subnet, drawdown)

                if hard_result.passed:
                    passing.append((subnet, drawdown))
                else:
                    failing.append(ViabilityResult(
                        netuid=subnet.netuid,
                        name=subnet.name,
                        hard_failure=hard_result,
                        score=None,
                        tier=ViabilityTier.TIER_4,
                        factors=None,
                    ))

            logger.info(
                "Hard failures complete",
                passing=len(passing),
                failing=len(failing),
            )

            if not passing:
                return failing

            # Phase 2: collect raw metrics for passing subnets
            raw_metrics: List[Dict[str, float]] = []
            for subnet, drawdown in passing:
                raw_metrics.append({
                    "tao_reserve": float(subnet.pool_tao_reserve or 0),
                    "net_flow_7d": float(subnet.taoflow_7d or 0),
                    "emission_share": float(subnet.emission_share or 0),
                    "price_trend_7d": float(subnet.price_trend_7d or 0),
                    "subnet_age": min(subnet.age_days or 0, self.age_cap),
                    "max_drawdown_30d": drawdown,
                })

            # Phase 3: compute percentile ranks
            normal_metrics = ["tao_reserve", "net_flow_7d", "emission_share", "price_trend_7d", "subnet_age"]
            for metric_name in normal_metrics:
                values = [m[metric_name] for m in raw_metrics]
                for m in raw_metrics:
                    m[f"{metric_name}_pctile"] = self._percentile_rank(values, m[metric_name])

            # Drawdown is inverted (lower = better)
            dd_values = [m["max_drawdown_30d"] for m in raw_metrics]
            for m in raw_metrics:
                m["max_drawdown_30d_pctile"] = self._percentile_rank_inverted(
                    dd_values, m["max_drawdown_30d"]
                )

            # Phase 4: weighted composite score
            results: List[ViabilityResult] = []
            for i, (subnet, drawdown) in enumerate(passing):
                m = raw_metrics[i]
                composite = sum(
                    m[f"{k}_pctile"] * w for k, w in self.weights.items()
                )

                tier = self._assign_tier(composite)

                factors = ViabilityFactors(
                    tao_reserve_raw=m["tao_reserve"],
                    tao_reserve_percentile=round(m["tao_reserve_pctile"], 1),
                    tao_reserve_weighted=round(m["tao_reserve_pctile"] * self.weights["tao_reserve"], 1),
                    net_flow_7d_raw=m["net_flow_7d"],
                    net_flow_7d_percentile=round(m["net_flow_7d_pctile"], 1),
                    net_flow_7d_weighted=round(m["net_flow_7d_pctile"] * self.weights["net_flow_7d"], 1),
                    emission_share_raw=m["emission_share"],
                    emission_share_percentile=round(m["emission_share_pctile"], 1),
                    emission_share_weighted=round(m["emission_share_pctile"] * self.weights["emission_share"], 1),
                    price_trend_7d_raw=m["price_trend_7d"],
                    price_trend_7d_percentile=round(m["price_trend_7d_pctile"], 1),
                    price_trend_7d_weighted=round(m["price_trend_7d_pctile"] * self.weights["price_trend_7d"], 1),
                    subnet_age_raw=int(m["subnet_age"]),
                    subnet_age_percentile=round(m["subnet_age_pctile"], 1),
                    subnet_age_weighted=round(m["subnet_age_pctile"] * self.weights["subnet_age"], 1),
                    max_drawdown_30d_raw=round(m["max_drawdown_30d"], 4),
                    max_drawdown_30d_percentile=round(m["max_drawdown_30d_pctile"], 1),
                    max_drawdown_30d_weighted=round(m["max_drawdown_30d_pctile"] * self.weights["max_drawdown_30d"], 1),
                )

                results.append(ViabilityResult(
                    netuid=subnet.netuid,
                    name=subnet.name,
                    hard_failure=HardFailureResult(passed=True, failures=[]),
                    score=round(composite, 1),
                    tier=tier,
                    factors=factors,
                ))

            logger.info(
                "Viability scoring complete",
                scored=len(results),
                tier_1=sum(1 for r in results if r.tier == ViabilityTier.TIER_1),
                tier_2=sum(1 for r in results if r.tier == ViabilityTier.TIER_2),
                tier_3=sum(1 for r in results if r.tier == ViabilityTier.TIER_3),
                tier_4_scored=sum(1 for r in results if r.tier == ViabilityTier.TIER_4),
                tier_4_failed=len(failing),
            )

            return failing + results

    async def _is_enabled(self) -> bool:
        """Check if viability scoring is enabled (DB config takes precedence)."""
        from app.models.viability_config import ViabilityConfig

        async with get_db_context() as db:
            stmt = (
                select(ViabilityConfig.enabled)
                .where(ViabilityConfig.is_active == True)  # noqa: E712
                .order_by(ViabilityConfig.updated_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            if row is not None:
                return row
        return get_settings().enable_viability_scoring

    async def update_all_viability(self) -> Dict[str, Any]:
        """Score all subnets and write results to database."""
        from app.models.subnet import Subnet

        if not await self._is_enabled():
            logger.info("Viability scoring disabled")
            return {"scored_count": 0, "tier_counts": {}}

        all_results = await self.score_all_subnets()

        # Build lookup
        result_lookup: Dict[int, ViabilityResult] = {r.netuid: r for r in all_results}

        async with get_db_context() as db:
            stmt = select(Subnet).where(Subnet.netuid != 0)
            result = await db.execute(stmt)
            subnets = list(result.scalars().all())

            for subnet in subnets:
                vr = result_lookup.get(subnet.netuid)
                if vr is None:
                    continue

                subnet.viability_score = Decimal(str(vr.score)) if vr.score is not None else None
                subnet.viability_tier = vr.tier.value
                subnet.max_drawdown_30d = (
                    Decimal(str(vr.factors.max_drawdown_30d_raw)) if vr.factors else None
                )

                if vr.factors:
                    subnet.viability_factors = json.dumps(asdict(vr.factors))
                else:
                    # Store hard failure reasons for failed subnets
                    subnet.viability_factors = json.dumps({
                        "hard_failures": vr.hard_failure.failures
                    })

            await db.commit()

        tier_counts = {}
        for tier in ViabilityTier:
            tier_counts[tier.value] = sum(1 for r in all_results if r.tier == tier)

        return {
            "scored_count": len(all_results),
            "tier_counts": tier_counts,
        }


# Lazy singleton
_viability_scorer: Optional[ViabilityScorer] = None


def get_viability_scorer() -> ViabilityScorer:
    global _viability_scorer
    if _viability_scorer is None:
        _viability_scorer = ViabilityScorer()
    return _viability_scorer


def reset_viability_scorer():
    """Reset the singleton so next access picks up fresh config."""
    global _viability_scorer
    _viability_scorer = None


class _LazyViabilityScorer:
    def __getattr__(self, name: str):
        return getattr(get_viability_scorer(), name)


viability_scorer = _LazyViabilityScorer()
