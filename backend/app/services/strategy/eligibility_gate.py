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
from enum import Enum

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet
from app.models.position import Position
from app.models.validator import Validator
from app.models.slippage import SlippageSurface
from app.services.strategy.regime_calculator import FlowRegime

logger = structlog.get_logger()


class ExitabilityLevel(str, Enum):
    """Exitability severity levels for position slippage.

    PASS: Slippage acceptable, no action needed
    WARNING: 100% exit slippage > 7.5%, monitor closely
    BLOCK_BUY: 50% exit slippage > 5%, cannot enter new position
    FORCE_TRIM: 100% exit slippage > 10%, must reduce position size
    """
    PASS = "pass"
    WARNING = "warning"
    BLOCK_BUY = "block_buy"
    FORCE_TRIM = "force_trim"


@dataclass
class ExitabilityResult:
    """Result of exitability check for a position/subnet."""
    netuid: int
    level: ExitabilityLevel
    slippage_50pct: Decimal
    slippage_100pct: Decimal
    reason: str
    current_size_tao: Optional[Decimal] = None
    safe_size_tao: Optional[Decimal] = None  # Max size that keeps slippage under threshold
    trim_amount_tao: Optional[Decimal] = None  # Recommended trim if FORCE_TRIM
    trim_pct: Optional[Decimal] = None  # Trim as percentage of position


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
        settings = get_settings()
        self._wallet_address = settings.wallet_address

        # Universe filter thresholds from config
        self.min_liquidity_tao = settings.min_liquidity_tao
        self.min_holder_count = settings.min_holder_count
        self.min_subnet_age_days = settings.min_subnet_age_days
        self.max_owner_take = settings.max_owner_take
        self.min_emission_share = settings.min_emission_share

        # Slippage caps (exitability thresholds)
        self.max_exit_slippage_50pct = settings.max_exit_slippage_50pct  # 5% - blocks new buys
        self.max_exit_slippage_100pct = settings.max_exit_slippage_100pct  # 10% - forces trim
        self.exitability_warning_threshold = settings.exitability_warning_threshold  # 7.5% - warning tier
        self.enable_exitability_gate = settings.enable_exitability_gate  # Feature flag

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

        # 9. Exitability check for target position size
        # When feature flag enabled: BLOCK_BUY = hard gate for new buys
        # FORCE_TRIM is NOT checked here - that's for existing positions only
        if db and target_position_tao:
            if self.enable_exitability_gate:
                # Use new structured exitability check
                exitability = await self.check_exitability(db, subnet.netuid, target_position_tao)
                if exitability.level == ExitabilityLevel.BLOCK_BUY:
                    reasons.append(f"BLOCKED: {exitability.reason}")
                elif exitability.level == ExitabilityLevel.FORCE_TRIM:
                    # For new buys, FORCE_TRIM also blocks entry (can't buy what you'd immediately need to trim)
                    reasons.append(f"BLOCKED: {exitability.reason}")
                elif exitability.level == ExitabilityLevel.WARNING:
                    # Warning doesn't block, but note it
                    pass  # Could add to a warnings list if needed
            else:
                # Legacy soft check (feature flag disabled)
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

    async def check_exitability(
        self,
        db: AsyncSession,
        netuid: int,
        position_size_tao: Decimal,
    ) -> ExitabilityResult:
        """Check exitability level for a position.

        Returns structured result with severity level and recommended action.
        This is the core exitability check used by both eligibility (new buys)
        and position monitoring (existing holdings).

        Args:
            db: Database session
            netuid: Subnet network ID
            position_size_tao: Current or target position size in TAO

        Returns:
            ExitabilityResult with level, slippage values, and recommendations
        """
        # Get slippage surfaces for unstake action
        stmt = select(SlippageSurface).where(
            SlippageSurface.netuid == netuid,
            SlippageSurface.action == "unstake",
        ).order_by(SlippageSurface.size_tao)
        result = await db.execute(stmt)
        surfaces = list(result.scalars().all())

        if not surfaces:
            # No slippage data - conservative default
            return ExitabilityResult(
                netuid=netuid,
                level=ExitabilityLevel.WARNING,
                slippage_50pct=Decimal("0"),
                slippage_100pct=Decimal("0"),
                reason="No slippage data available - cannot assess exitability",
                current_size_tao=position_size_tao,
            )

        # Calculate slippage for 50% and 100% exit
        exit_50pct = position_size_tao * Decimal("0.5")
        exit_100pct = position_size_tao

        slip_50 = self._interpolate_slippage(surfaces, exit_50pct)
        slip_100 = self._interpolate_slippage(surfaces, exit_100pct)

        # Determine level based on thresholds
        # Priority: FORCE_TRIM > BLOCK_BUY > WARNING > PASS
        level = ExitabilityLevel.PASS
        reason = f"Slippage acceptable: 50%={float(slip_50):.1%}, 100%={float(slip_100):.1%}"

        # Check 100% exit against force trim threshold (10%)
        if slip_100 > self.max_exit_slippage_100pct:
            level = ExitabilityLevel.FORCE_TRIM
            reason = f"100% exit slippage {float(slip_100):.1%} > {float(self.max_exit_slippage_100pct):.1%} threshold - MUST TRIM"
        # Check 50% exit against block buy threshold (5%)
        elif slip_50 > self.max_exit_slippage_50pct:
            level = ExitabilityLevel.BLOCK_BUY
            reason = f"50% exit slippage {float(slip_50):.1%} > {float(self.max_exit_slippage_50pct):.1%} threshold - cannot enter"
        # Check 100% exit against warning threshold (7.5%)
        elif slip_100 > self.exitability_warning_threshold:
            level = ExitabilityLevel.WARNING
            reason = f"100% exit slippage {float(slip_100):.1%} > {float(self.exitability_warning_threshold):.1%} warning tier - monitor closely"

        result = ExitabilityResult(
            netuid=netuid,
            level=level,
            slippage_50pct=slip_50,
            slippage_100pct=slip_100,
            reason=reason,
            current_size_tao=position_size_tao,
        )

        # If FORCE_TRIM, calculate recommended trim
        if level == ExitabilityLevel.FORCE_TRIM:
            safe_size = await self.calculate_safe_position_size(
                db, netuid, position_size_tao, surfaces
            )
            if safe_size is None:
                # Safe size below minimum meaningful position - recommend full exit
                result.safe_size_tao = Decimal("0")
                result.trim_amount_tao = position_size_tao
                result.trim_pct = Decimal("100")
                result.reason += " (Full exit recommended - safe size below minimum)"
            elif safe_size < position_size_tao:
                result.safe_size_tao = safe_size
                result.trim_amount_tao = position_size_tao - safe_size
                result.trim_pct = result.trim_amount_tao / position_size_tao * Decimal("100")

        return result

    async def calculate_safe_position_size(
        self,
        db: AsyncSession,
        netuid: int,
        current_size_tao: Decimal,
        surfaces: Optional[List[SlippageSurface]] = None,
        target_slippage: Optional[Decimal] = None,
        portfolio_nav_tao: Optional[Decimal] = None,
    ) -> Optional[Decimal]:
        """Calculate the maximum position size that keeps exit slippage under threshold.

        Uses binary search to find the largest position where 100% exit slippage
        stays under the target threshold (default: 7.5% for safety buffer under 10%).

        SAFETY GUARD: If the calculated safe size would be below the minimum
        meaningful position size (min_position_pct of portfolio or min_position_tao),
        returns None to indicate full exit is recommended instead of micro position.

        Args:
            db: Database session
            netuid: Subnet network ID
            current_size_tao: Current position size
            surfaces: Optional pre-fetched slippage surfaces
            target_slippage: Target max slippage (default: warning threshold 7.5%)
            portfolio_nav_tao: Portfolio NAV for min position % calculation

        Returns:
            Maximum safe position size in TAO, or None if full exit recommended
        """
        # Use warning threshold as target for safety buffer
        if target_slippage is None:
            target_slippage = self.exitability_warning_threshold

        # Fetch surfaces if not provided
        if surfaces is None:
            stmt = select(SlippageSurface).where(
                SlippageSurface.netuid == netuid,
                SlippageSurface.action == "unstake",
            ).order_by(SlippageSurface.size_tao)
            result = await db.execute(stmt)
            surfaces = list(result.scalars().all())

        if not surfaces:
            return None

        # Binary search for max safe size
        # Search between 0 and current size
        low = Decimal("0")
        high = current_size_tao
        precision = Decimal("0.1")  # 0.1 TAO precision
        max_iterations = 20

        best_safe_size = Decimal("0")

        for _ in range(max_iterations):
            if high - low < precision:
                break

            mid = (low + high) / 2
            slip_100 = self._interpolate_slippage(surfaces, mid)

            if slip_100 <= target_slippage:
                # This size is safe, try larger
                best_safe_size = mid
                low = mid
            else:
                # This size has too much slippage, try smaller
                high = mid

        # SAFETY GUARD: Check if safe size is below minimum meaningful position
        settings = get_settings()
        min_position_tao = settings.min_position_tao

        # If we have portfolio NAV, also check percentage-based minimum
        if portfolio_nav_tao and portfolio_nav_tao > 0:
            min_position_pct_tao = portfolio_nav_tao * settings.min_position_pct
            min_position_tao = max(min_position_tao, min_position_pct_tao)

        if best_safe_size < min_position_tao:
            # Safe size is below minimum meaningful position
            # Recommend full exit instead of leaving a micro position
            logger.info(
                "Safe position size below minimum threshold, recommending full exit",
                netuid=netuid,
                safe_size=float(best_safe_size),
                min_position=float(min_position_tao),
            )
            return None  # None signals full exit recommended

        return best_safe_size

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

    async def check_all_positions_exitability(
        self,
        db: AsyncSession,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, any]:
        """Check exitability for all current positions.

        Scans all wallet positions and returns exitability assessment,
        flagging any that need action (WARNING or FORCE_TRIM).

        This is separate from eligibility (which is for new buys only).
        Existing positions may need trims even if they're "eligible" for new buys.

        Args:
            db: Database session (passed from DI)
            wallet_address: Wallet to check (default: config wallet)

        Returns:
            Dict with:
                - positions: List of ExitabilityResult for each position
                - warnings: Positions in WARNING state
                - force_trims: Positions requiring FORCE_TRIM
                - total_trim_tao: Total recommended trim amount
        """
        wallet = wallet_address or self._wallet_address
        logger.info("Checking exitability for all positions", wallet=wallet)

        results = {
            "positions": [],
            "warnings": [],
            "force_trims": [],
            "total_trim_tao": Decimal("0"),
            "feature_enabled": self.enable_exitability_gate,
        }

        # Get all positions with value
        stmt = select(Position).where(
            Position.wallet_address == wallet,
            Position.tao_value_mid > 0,
        )
        result = await db.execute(stmt)
        positions = list(result.scalars().all())

        for pos in positions:
            # Skip root network
            if pos.netuid == 0:
                continue

            exitability = await self.check_exitability(
                db, pos.netuid, pos.tao_value_mid
            )

            # Add subnet name for display
            subnet_stmt = select(Subnet).where(Subnet.netuid == pos.netuid)
            subnet_result = await db.execute(subnet_stmt)
            subnet = subnet_result.scalar_one_or_none()
            subnet_name = subnet.name if subnet else f"SN{pos.netuid}"

            position_result = {
                "netuid": pos.netuid,
                "subnet_name": subnet_name,
                "exitability": exitability,
                "level": exitability.level.value,
                "slippage_50pct": float(exitability.slippage_50pct),
                "slippage_100pct": float(exitability.slippage_100pct),
                "current_size_tao": float(pos.tao_value_mid),
                "reason": exitability.reason,
            }

            if exitability.safe_size_tao is not None:
                position_result["safe_size_tao"] = float(exitability.safe_size_tao)
            if exitability.trim_amount_tao is not None:
                position_result["trim_amount_tao"] = float(exitability.trim_amount_tao)
            if exitability.trim_pct is not None:
                position_result["trim_pct"] = float(exitability.trim_pct)

            results["positions"].append(position_result)

            # Categorize by level
            if exitability.level == ExitabilityLevel.WARNING:
                results["warnings"].append(position_result)
            elif exitability.level == ExitabilityLevel.FORCE_TRIM:
                results["force_trims"].append(position_result)
                if exitability.trim_amount_tao:
                    results["total_trim_tao"] += exitability.trim_amount_tao

        results["total_trim_tao"] = float(results["total_trim_tao"])

        logger.info("Exitability check complete",
                   total_positions=len(results["positions"]),
                   warnings=len(results["warnings"]),
                   force_trims=len(results["force_trims"]),
                   total_trim=results["total_trim_tao"])

        return results


# Lazy singleton instance
_eligibility_gate: Optional[EligibilityGate] = None


def get_eligibility_gate() -> EligibilityGate:
    """Get or create the EligibilityGate singleton."""
    global _eligibility_gate
    if _eligibility_gate is None:
        _eligibility_gate = EligibilityGate()
    return _eligibility_gate


class _LazyEligibilityGate:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_eligibility_gate(), name)


eligibility_gate = _LazyEligibilityGate()
