"""Eligibility gate for subnet universe filtering.

Implements hard excludes per spec:
- Emission share zero or near zero
- Sustained negative taoflow
- Liquidity too low for target size
- Holder count below minimum
- Too new (below minimum age)
- Owner take above maximum
- Validator quality fails (vtrust floor, take cap)
- Exit slippage exceeds caps
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet
from app.models.validator import Validator
from app.models.slippage import SlippageSurface
from app.services.strategy.regime_calculator import FlowRegime

settings = get_settings()
logger = structlog.get_logger()


@dataclass
class EligibilityResult:
    """Result of eligibility check for a subnet."""
    netuid: int
    name: str
    is_eligible: bool
    reasons: List[str]
    score: Optional[int] = None  # 0-100 attractiveness score if eligible


class EligibilityGate:
    """Filters subnets into investable universe based on hard rules."""

    def __init__(self):
        # Universe filter thresholds from config
        self.min_liquidity_tao = settings.min_liquidity_tao
        self.min_holder_count = settings.min_holder_count
        self.min_subnet_age_days = settings.min_subnet_age_days
        self.max_owner_take = settings.max_owner_take
        self.min_emission_share = settings.min_emission_share

        # Slippage caps
        self.max_exit_slippage_50pct = settings.max_exit_slippage_50pct
        self.max_exit_slippage_100pct = settings.max_exit_slippage_100pct

        # Validator quality thresholds
        self.min_vtrust = Decimal("0.5")  # Minimum validator trust
        self.max_validator_take = Decimal("0.20")  # Max validator take rate

    async def check_subnet_eligibility(
        self,
        subnet: Subnet,
        target_position_tao: Optional[Decimal] = None,
        db: Optional[AsyncSession] = None
    ) -> EligibilityResult:
        """Check if a subnet is eligible for investment.

        Args:
            subnet: Subnet to check
            target_position_tao: Target position size for slippage check
            db: Optional database session

        Returns:
            EligibilityResult with eligibility status and reasons
        """
        reasons = []

        # 1. Emission share check
        if subnet.emission_share < self.min_emission_share:
            reasons.append(f"Emission share too low: {float(subnet.emission_share):.3%} < {float(self.min_emission_share):.3%}")

        # 2. Liquidity check
        if subnet.pool_tao_reserve < self.min_liquidity_tao:
            reasons.append(f"Liquidity too low: {float(subnet.pool_tao_reserve):.1f} TAO < {float(self.min_liquidity_tao)} TAO")

        # 3. Holder count check
        if subnet.holder_count < self.min_holder_count:
            reasons.append(f"Holder count too low: {subnet.holder_count} < {self.min_holder_count}")

        # 4. Age check
        if subnet.age_days < self.min_subnet_age_days:
            reasons.append(f"Subnet too new: {subnet.age_days} days < {self.min_subnet_age_days} days")

        # 5. Owner take check
        if subnet.owner_take > self.max_owner_take:
            reasons.append(f"Owner take too high: {float(subnet.owner_take):.1%} > {float(self.max_owner_take):.1%}")

        # 6. Flow regime check - exclude Quarantine and Dead
        if subnet.flow_regime in [FlowRegime.QUARANTINE.value, FlowRegime.DEAD.value]:
            reasons.append(f"Flow regime is {subnet.flow_regime}")

        # 7. Sustained negative taoflow check
        # Exclude if 7d AND 14d both negative
        if subnet.taoflow_7d < 0 and subnet.taoflow_14d < 0:
            reasons.append(f"Sustained negative flow: 7d={float(subnet.taoflow_7d):.1%}, 14d={float(subnet.taoflow_14d):.1%}")

        # 8. Validator quality check (if we have a top validator)
        if db and subnet.top_validator_hotkey:
            validator = await self._get_validator(db, subnet.top_validator_hotkey, subnet.netuid)
            if validator:
                if validator.vtrust < self.min_vtrust:
                    reasons.append(f"Validator vtrust too low: {float(validator.vtrust):.2f} < {float(self.min_vtrust)}")
                if validator.take_rate > self.max_validator_take:
                    reasons.append(f"Validator take too high: {float(validator.take_rate):.1%} > {float(self.max_validator_take):.1%}")

        # 9. Slippage check for target position size
        if db and target_position_tao:
            slippage_check = await self._check_slippage(db, subnet.netuid, target_position_tao)
            if slippage_check:
                reasons.append(slippage_check)

        # Calculate attractiveness score if eligible
        score = None
        if not reasons:
            score = await self._calculate_attractiveness_score(subnet)

        return EligibilityResult(
            netuid=subnet.netuid,
            name=subnet.name,
            is_eligible=len(reasons) == 0,
            reasons=reasons,
            score=score,
        )

    async def _get_validator(
        self,
        db: AsyncSession,
        hotkey: str,
        netuid: int
    ) -> Optional[Validator]:
        """Get validator by hotkey and netuid."""
        stmt = select(Validator).where(
            Validator.hotkey == hotkey,
            Validator.netuid == netuid,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _check_slippage(
        self,
        db: AsyncSession,
        netuid: int,
        target_size_tao: Decimal
    ) -> Optional[str]:
        """Check if slippage is acceptable for target position size.

        Returns:
            Error message if slippage exceeds caps, None otherwise
        """
        # Get slippage surfaces for unstake action
        stmt = select(SlippageSurface).where(
            SlippageSurface.netuid == netuid,
            SlippageSurface.action == "unstake",
        ).order_by(SlippageSurface.size_tao)
        result = await db.execute(stmt)
        surfaces = list(result.scalars().all())

        if not surfaces:
            return "No slippage data available"

        # Interpolate slippage for 50% and 100% exit
        exit_50pct = target_size_tao * Decimal("0.5")
        exit_100pct = target_size_tao

        slip_50 = self._interpolate_slippage(surfaces, exit_50pct)
        slip_100 = self._interpolate_slippage(surfaces, exit_100pct)

        if slip_50 > self.max_exit_slippage_50pct:
            return f"50% exit slippage too high: {float(slip_50):.1%} > {float(self.max_exit_slippage_50pct):.1%}"

        if slip_100 > self.max_exit_slippage_100pct:
            return f"100% exit slippage too high: {float(slip_100):.1%} > {float(self.max_exit_slippage_100pct):.1%}"

        return None

    def _interpolate_slippage(
        self,
        surfaces: List[SlippageSurface],
        size_tao: Decimal
    ) -> Decimal:
        """Interpolate slippage for a given size from cached surfaces."""
        if not surfaces:
            return Decimal("0.10")  # Default high if no data

        # Find bracketing surfaces
        lower = None
        upper = None

        for s in surfaces:
            if s.size_tao <= size_tao:
                lower = s
            if s.size_tao >= size_tao and upper is None:
                upper = s

        if lower is None:
            return surfaces[0].slippage_pct

        if upper is None:
            # Extrapolate using largest cached size
            return surfaces[-1].slippage_pct

        if lower.size_tao == upper.size_tao:
            return lower.slippage_pct

        # Linear interpolation
        ratio = (size_tao - lower.size_tao) / (upper.size_tao - lower.size_tao)
        slippage = lower.slippage_pct + ratio * (upper.slippage_pct - lower.slippage_pct)
        return slippage

    async def _calculate_attractiveness_score(self, subnet: Subnet) -> int:
        """Calculate attractiveness score for eligible subnet (0-100).

        Higher score = more attractive for investment.
        """
        score = 50  # Base score

        # Bonus for positive flow momentum
        if subnet.taoflow_7d > 0:
            score += min(20, int(float(subnet.taoflow_7d) * 100))
        if subnet.taoflow_14d > 0:
            score += min(10, int(float(subnet.taoflow_14d) * 50))

        # Bonus for strong emissions
        if subnet.emission_share > Decimal("0.01"):
            score += 10
        if subnet.emission_share > Decimal("0.02"):
            score += 5

        # Bonus for good liquidity
        if subnet.pool_tao_reserve > Decimal("10000"):
            score += 10
        if subnet.pool_tao_reserve > Decimal("50000"):
            score += 5

        # Bonus for holder base
        if subnet.holder_count > 500:
            score += 5
        if subnet.holder_count > 1000:
            score += 5

        # Penalty for high owner take
        if subnet.owner_take > Decimal("0.10"):
            score -= 10

        # Bonus for age/stability
        if subnet.age_days > 90:
            score += 5

        return max(0, min(100, score))

    async def get_eligible_universe(
        self,
        target_position_tao: Optional[Decimal] = None
    ) -> List[EligibilityResult]:
        """Get all eligible subnets sorted by attractiveness.

        Args:
            target_position_tao: Default target position size

        Returns:
            List of EligibilityResult for eligible subnets
        """
        logger.info("Computing eligible universe")

        results = []

        async with get_db_context() as db:
            # Get all subnets with pool liquidity
            stmt = select(Subnet).where(Subnet.pool_tao_reserve > 0)
            result = await db.execute(stmt)
            subnets = list(result.scalars().all())

            for subnet in subnets:
                # Skip root network
                if subnet.netuid == 0:
                    continue

                eligibility = await self.check_subnet_eligibility(
                    subnet,
                    target_position_tao,
                    db
                )
                results.append(eligibility)

        # Filter to eligible only and sort by score
        eligible = [r for r in results if r.is_eligible]
        eligible.sort(key=lambda x: x.score or 0, reverse=True)

        logger.info("Eligible universe computed",
                   total_checked=len(results),
                   eligible=len(eligible))

        return eligible

    async def update_subnet_eligibility(self) -> Dict[str, any]:
        """Update eligibility flags for all subnets.

        Returns:
            Summary of eligibility updates
        """
        logger.info("Updating subnet eligibility")

        summary = {
            "total_checked": 0,
            "eligible": 0,
            "ineligible": 0,
            "changes": [],
        }

        async with get_db_context() as db:
            # Get all subnets
            stmt = select(Subnet)
            result = await db.execute(stmt)
            subnets = list(result.scalars().all())

            for subnet in subnets:
                old_eligible = subnet.is_eligible

                # Skip root
                if subnet.netuid == 0:
                    subnet.is_eligible = False
                    subnet.ineligibility_reasons = "Root network not in dTAO sleeve"
                    continue

                eligibility = await self.check_subnet_eligibility(subnet, None, db)

                subnet.is_eligible = eligibility.is_eligible
                subnet.ineligibility_reasons = "; ".join(eligibility.reasons) if eligibility.reasons else None

                summary["total_checked"] += 1
                if eligibility.is_eligible:
                    summary["eligible"] += 1
                else:
                    summary["ineligible"] += 1

                if old_eligible != eligibility.is_eligible:
                    summary["changes"].append({
                        "netuid": subnet.netuid,
                        "name": subnet.name,
                        "now_eligible": eligibility.is_eligible,
                        "reasons": eligibility.reasons,
                    })

            await db.commit()

        logger.info("Eligibility updated",
                   total=summary["total_checked"],
                   eligible=summary["eligible"],
                   changes=len(summary["changes"]))

        return summary


# Singleton instance
eligibility_gate = EligibilityGate()
