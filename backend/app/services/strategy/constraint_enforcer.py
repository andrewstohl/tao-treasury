"""Constraint enforcer for portfolio risk management.

Monitors and enforces all portfolio constraints with
detailed explanation strings for transparency.

Constraints enforced:
- Position concentration (max 15% per position)
- Category concentration (max 30% of sleeve)
- Drawdown limits (soft 15%, hard 20%)
- Turnover caps (daily 10%, weekly 40%)
- Slippage caps (5% for 50% exit, 10% for full)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet
from app.models.position import Position
from app.models.portfolio import PortfolioSnapshot
from app.models.trade import TradeRecommendation
from app.models.alert import Alert

settings = get_settings()
logger = structlog.get_logger()


class ConstraintSeverity(str, Enum):
    """Severity level of constraint violation."""
    INFO = "info"           # Within limits but approaching
    WARNING = "warning"     # Near limit (>80% of limit)
    BREACH = "critical"     # Limit exceeded


@dataclass
class ConstraintViolation:
    """Details of a constraint violation."""
    constraint_name: str
    severity: ConstraintSeverity
    current_value: Decimal
    limit_value: Decimal
    utilization_pct: Decimal  # How much of the limit is used
    explanation: str
    action_required: str
    netuid: Optional[int] = None
    category: Optional[str] = None


@dataclass
class ConstraintStatus:
    """Overall constraint status for the portfolio."""
    checked_at: datetime
    all_constraints_ok: bool
    total_checked: int
    violations: List[ConstraintViolation]
    warnings: List[ConstraintViolation]
    summary: str


class ConstraintEnforcer:
    """Monitors and enforces portfolio constraints."""

    def __init__(self):
        self.wallet_address = settings.wallet_address

        # Load thresholds
        self.max_position_pct = settings.max_position_concentration
        self.max_category_pct = settings.max_category_concentration_sleeve
        self.soft_drawdown = settings.soft_drawdown_limit
        self.hard_drawdown = settings.hard_drawdown_limit
        self.max_daily_turnover = settings.max_daily_turnover
        self.max_weekly_turnover = settings.max_weekly_turnover
        self.max_slip_50pct = settings.max_exit_slippage_50pct
        self.max_slip_100pct = settings.max_exit_slippage_100pct

        # Warning threshold (80% of limit)
        self.warning_threshold = Decimal("0.80")

    async def check_all_constraints(self) -> ConstraintStatus:
        """Check all portfolio constraints and return status.

        Returns comprehensive status with violations and warnings.
        """
        logger.info("Checking all portfolio constraints")
        now = datetime.now(timezone.utc)

        violations: List[ConstraintViolation] = []
        warnings: List[ConstraintViolation] = []
        total_checked = 0

        async with get_db_context() as db:
            snapshot = await self._get_latest_snapshot(db)
            if not snapshot:
                return ConstraintStatus(
                    checked_at=now,
                    all_constraints_ok=False,
                    total_checked=0,
                    violations=[],
                    warnings=[],
                    summary="No portfolio snapshot available",
                )

            positions = await self._get_positions(db)

            # 1. Check position concentration
            pos_violations = await self._check_position_concentration(
                db, positions, snapshot
            )
            total_checked += len(positions)
            for v in pos_violations:
                if v.severity == ConstraintSeverity.BREACH:
                    violations.append(v)
                else:
                    warnings.append(v)

            # 2. Check category concentration
            cat_violations = await self._check_category_concentration(
                db, positions, snapshot
            )
            total_checked += len(cat_violations) or 1
            for v in cat_violations:
                if v.severity == ConstraintSeverity.BREACH:
                    violations.append(v)
                else:
                    warnings.append(v)

            # 3. Check drawdown limits
            dd_violation = self._check_drawdown(snapshot)
            total_checked += 1
            if dd_violation:
                if dd_violation.severity == ConstraintSeverity.BREACH:
                    violations.append(dd_violation)
                else:
                    warnings.append(dd_violation)

            # 4. Check turnover limits
            turnover_violation = await self._check_turnover(db, snapshot)
            total_checked += 1
            if turnover_violation:
                if turnover_violation.severity == ConstraintSeverity.BREACH:
                    violations.append(turnover_violation)
                else:
                    warnings.append(turnover_violation)

            # 5. Check slippage exposure
            slip_violations = await self._check_slippage_exposure(db, positions)
            total_checked += len(positions)
            for v in slip_violations:
                if v.severity == ConstraintSeverity.BREACH:
                    violations.append(v)
                else:
                    warnings.append(v)

        # Build summary
        summary = self._build_summary(violations, warnings, total_checked)

        return ConstraintStatus(
            checked_at=now,
            all_constraints_ok=len(violations) == 0,
            total_checked=total_checked,
            violations=violations,
            warnings=warnings,
            summary=summary,
        )

    async def check_trade_allowed(
        self,
        netuid: int,
        direction: str,
        size_tao: Decimal,
    ) -> Tuple[bool, str]:
        """Check if a proposed trade is allowed by constraints.

        Args:
            netuid: Target subnet
            direction: 'buy' or 'sell'
            size_tao: Trade size in TAO

        Returns:
            Tuple of (allowed, explanation)
        """
        async with get_db_context() as db:
            snapshot = await self._get_latest_snapshot(db)
            if not snapshot:
                return False, "No portfolio snapshot available"

            # Check turnover budget
            remaining_turnover = await self._get_remaining_turnover(db, snapshot)
            trade_turnover = size_tao / snapshot.nav_mid if snapshot.nav_mid else Decimal("0")

            if trade_turnover > remaining_turnover:
                return False, (
                    f"Trade would exceed turnover limit. "
                    f"Trade: {float(trade_turnover * 100):.1f}% of NAV, "
                    f"Remaining budget: {float(remaining_turnover * 100):.1f}%"
                )

            if direction == "buy":
                # Check concentration after trade
                pos = await self._get_position(db, netuid)
                current_value = pos.tao_value_mid if pos else Decimal("0")
                new_value = current_value + size_tao
                new_pct = new_value / snapshot.nav_mid if snapshot.nav_mid else Decimal("0")

                if new_pct > self.max_position_pct:
                    return False, (
                        f"Trade would exceed concentration limit. "
                        f"Result: {float(new_pct * 100):.1f}%, "
                        f"Limit: {float(self.max_position_pct * 100):.0f}%"
                    )

                # Check category limit
                subnet = await self._get_subnet(db, netuid)
                if subnet:
                    category = subnet.category or "uncategorized"
                    cat_alloc = await self._get_category_allocation(db, category)
                    new_cat_pct = (cat_alloc + size_tao) / snapshot.dtao_allocation_tao if snapshot.dtao_allocation_tao else Decimal("0")

                    if new_cat_pct > self.max_category_pct:
                        return False, (
                            f"Trade would exceed category limit for {category}. "
                            f"Result: {float(new_cat_pct * 100):.1f}%, "
                            f"Limit: {float(self.max_category_pct * 100):.0f}%"
                        )

            return True, "Trade allowed within all constraints"

    async def get_available_capacity(
        self,
        netuid: int,
    ) -> Dict[str, Decimal]:
        """Get available capacity for a position within all constraints.

        Returns:
            Dict with capacity under each constraint type
        """
        async with get_db_context() as db:
            snapshot = await self._get_latest_snapshot(db)
            if not snapshot:
                return {"error": Decimal("-1")}

            pos = await self._get_position(db, netuid)
            current_value = pos.tao_value_mid if pos else Decimal("0")

            # Concentration capacity
            max_by_concentration = snapshot.nav_mid * self.max_position_pct
            concentration_capacity = max(Decimal("0"), max_by_concentration - current_value)

            # Category capacity
            subnet = await self._get_subnet(db, netuid)
            category = (subnet.category if subnet else None) or "uncategorized"
            cat_alloc = await self._get_category_allocation(db, category)
            max_by_category = snapshot.dtao_allocation_tao * self.max_category_pct
            # Add back current position (it's already counted in category)
            category_capacity = max(Decimal("0"), max_by_category - cat_alloc + current_value)

            # Turnover capacity
            remaining_turnover = await self._get_remaining_turnover(db, snapshot)
            turnover_capacity = snapshot.nav_mid * remaining_turnover

            return {
                "concentration_capacity_tao": concentration_capacity,
                "category_capacity_tao": category_capacity,
                "turnover_capacity_tao": turnover_capacity,
                "binding_capacity_tao": min(concentration_capacity, category_capacity, turnover_capacity),
            }

    async def create_violation_alerts(
        self,
        violations: List[ConstraintViolation],
    ) -> List[Alert]:
        """Create alerts for constraint violations.

        Returns list of created alerts.
        """
        alerts = []

        async with get_db_context() as db:
            for v in violations:
                # Check if similar alert already exists and is active
                existing = await self._get_existing_alert(db, v)
                if existing:
                    continue

                alert = Alert(
                    wallet_address=self.wallet_address,
                    category=v.constraint_name.lower().replace(" ", "_"),
                    severity=v.severity.value,
                    title=f"Constraint Violation: {v.constraint_name}",
                    message=f"{v.explanation}\n\nAction Required: {v.action_required}",
                    netuid=v.netuid,
                    threshold_value=v.limit_value,
                    actual_value=v.current_value,
                    is_active=True,
                )
                db.add(alert)
                alerts.append(alert)

            await db.commit()

        logger.info("Created violation alerts", count=len(alerts))
        return alerts

    # Private helper methods

    async def _get_latest_snapshot(self, db: AsyncSession) -> Optional[PortfolioSnapshot]:
        """Get latest portfolio snapshot."""
        stmt = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.wallet_address == self.wallet_address)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_positions(self, db: AsyncSession) -> List[Position]:
        """Get all current positions."""
        stmt = select(Position).where(
            Position.wallet_address == self.wallet_address,
            Position.tao_value_mid > Decimal("0.01"),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _get_position(self, db: AsyncSession, netuid: int) -> Optional[Position]:
        """Get position for a specific subnet."""
        stmt = select(Position).where(
            Position.wallet_address == self.wallet_address,
            Position.netuid == netuid,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_subnet(self, db: AsyncSession, netuid: int) -> Optional[Subnet]:
        """Get subnet by netuid."""
        stmt = select(Subnet).where(Subnet.netuid == netuid)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_category_allocation(self, db: AsyncSession, category: str) -> Decimal:
        """Get total allocation to a category."""
        # This is a simplified version - in production would join with subnets
        stmt = select(Position).where(Position.wallet_address == self.wallet_address)
        result = await db.execute(stmt)
        positions = result.scalars().all()

        total = Decimal("0")
        for pos in positions:
            subnet = await self._get_subnet(db, pos.netuid)
            pos_category = (subnet.category if subnet else None) or "uncategorized"
            if pos_category == category:
                total += pos.tao_value_mid

        return total

    async def _check_position_concentration(
        self,
        db: AsyncSession,
        positions: List[Position],
        snapshot: PortfolioSnapshot,
    ) -> List[ConstraintViolation]:
        """Check position concentration constraints."""
        violations = []
        portfolio_nav = snapshot.nav_mid

        for pos in positions:
            position_pct = pos.tao_value_mid / portfolio_nav if portfolio_nav else Decimal("0")
            utilization = position_pct / self.max_position_pct if self.max_position_pct else Decimal("0")

            subnet = await self._get_subnet(db, pos.netuid)
            name = subnet.name if subnet else f"Subnet {pos.netuid}"

            if position_pct > self.max_position_pct:
                violations.append(ConstraintViolation(
                    constraint_name="Position Concentration",
                    severity=ConstraintSeverity.BREACH,
                    current_value=position_pct,
                    limit_value=self.max_position_pct,
                    utilization_pct=utilization * 100,
                    explanation=(
                        f"{name} (SN{pos.netuid}) is {float(position_pct * 100):.1f}% of portfolio, "
                        f"exceeding the {float(self.max_position_pct * 100):.0f}% limit."
                    ),
                    action_required=(
                        f"Reduce position by {float((position_pct - self.max_position_pct) * portfolio_nav):,.0f} TAO "
                        f"to bring within limit."
                    ),
                    netuid=pos.netuid,
                ))
            elif utilization > self.warning_threshold:
                violations.append(ConstraintViolation(
                    constraint_name="Position Concentration",
                    severity=ConstraintSeverity.WARNING,
                    current_value=position_pct,
                    limit_value=self.max_position_pct,
                    utilization_pct=utilization * 100,
                    explanation=(
                        f"{name} (SN{pos.netuid}) is {float(position_pct * 100):.1f}% of portfolio, "
                        f"approaching the {float(self.max_position_pct * 100):.0f}% limit."
                    ),
                    action_required="Monitor position size and avoid adding to position.",
                    netuid=pos.netuid,
                ))

        return violations

    async def _check_category_concentration(
        self,
        db: AsyncSession,
        positions: List[Position],
        snapshot: PortfolioSnapshot,
    ) -> List[ConstraintViolation]:
        """Check category concentration constraints.

        Note: The "uncategorized" category is skipped from the 30% limit check
        since it represents positions in subnets without assigned categories.
        Category limits only apply to explicitly categorized positions.
        """
        violations = []
        sleeve_nav = snapshot.dtao_allocation_tao or Decimal("1")

        # Group positions by category
        category_totals: Dict[str, Decimal] = {}
        for pos in positions:
            subnet = await self._get_subnet(db, pos.netuid)
            category = (subnet.category if subnet else None) or "uncategorized"
            category_totals[category] = category_totals.get(category, Decimal("0")) + pos.tao_value_mid

        for category, total in category_totals.items():
            # Skip "uncategorized" - the 30% limit only applies to explicit categories
            if category == "uncategorized":
                continue

            category_pct = total / sleeve_nav
            utilization = category_pct / self.max_category_pct if self.max_category_pct else Decimal("0")

            if category_pct > self.max_category_pct:
                violations.append(ConstraintViolation(
                    constraint_name="Category Concentration",
                    severity=ConstraintSeverity.BREACH,
                    current_value=category_pct,
                    limit_value=self.max_category_pct,
                    utilization_pct=utilization * 100,
                    explanation=(
                        f"'{category}' category is {float(category_pct * 100):.1f}% of sleeve, "
                        f"exceeding the {float(self.max_category_pct * 100):.0f}% limit."
                    ),
                    action_required=(
                        f"Reduce allocation to '{category}' by "
                        f"{float((category_pct - self.max_category_pct) * sleeve_nav):,.0f} TAO."
                    ),
                    category=category,
                ))
            elif utilization > self.warning_threshold:
                violations.append(ConstraintViolation(
                    constraint_name="Category Concentration",
                    severity=ConstraintSeverity.WARNING,
                    current_value=category_pct,
                    limit_value=self.max_category_pct,
                    utilization_pct=utilization * 100,
                    explanation=(
                        f"'{category}' category is {float(category_pct * 100):.1f}% of sleeve, "
                        f"approaching the {float(self.max_category_pct * 100):.0f}% limit."
                    ),
                    action_required=f"Avoid adding to '{category}' category positions.",
                    category=category,
                ))

        return violations

    def _check_drawdown(self, snapshot: PortfolioSnapshot) -> Optional[ConstraintViolation]:
        """Check drawdown constraints."""
        drawdown = snapshot.drawdown_from_ath or Decimal("0")

        if drawdown > self.hard_drawdown:
            return ConstraintViolation(
                constraint_name="Drawdown Hard Limit",
                severity=ConstraintSeverity.BREACH,
                current_value=drawdown,
                limit_value=self.hard_drawdown,
                utilization_pct=(drawdown / self.hard_drawdown * 100) if self.hard_drawdown else Decimal("0"),
                explanation=(
                    f"Portfolio drawdown is {float(drawdown * 100):.1f}%, "
                    f"exceeding the hard limit of {float(self.hard_drawdown * 100):.0f}%."
                ),
                action_required=(
                    "IMMEDIATE ACTION REQUIRED: Reduce risk exposure across portfolio. "
                    "Consider exiting highest-risk positions."
                ),
            )
        elif drawdown > self.soft_drawdown:
            return ConstraintViolation(
                constraint_name="Drawdown Soft Limit",
                severity=ConstraintSeverity.WARNING,
                current_value=drawdown,
                limit_value=self.soft_drawdown,
                utilization_pct=(drawdown / self.soft_drawdown * 100) if self.soft_drawdown else Decimal("0"),
                explanation=(
                    f"Portfolio drawdown is {float(drawdown * 100):.1f}%, "
                    f"exceeding the soft limit of {float(self.soft_drawdown * 100):.0f}%."
                ),
                action_required=(
                    "Caution: Consider reducing position sizes and avoiding new entries "
                    "until drawdown recovers."
                ),
            )

        return None

    async def _check_turnover(
        self,
        db: AsyncSession,
        snapshot: PortfolioSnapshot,
    ) -> Optional[ConstraintViolation]:
        """Check turnover constraints."""
        # Get weekly turnover from executed trades
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = select(func.sum(TradeRecommendation.size_tao)).where(
            TradeRecommendation.wallet_address == self.wallet_address,
            TradeRecommendation.status == "executed",
            TradeRecommendation.marked_executed_at >= week_ago,
        )
        result = await db.execute(stmt)
        weekly_turnover_tao = result.scalar() or Decimal("0")

        portfolio_nav = snapshot.nav_mid or Decimal("1")
        turnover_pct = weekly_turnover_tao / portfolio_nav
        utilization = turnover_pct / self.max_weekly_turnover if self.max_weekly_turnover else Decimal("0")

        if turnover_pct > self.max_weekly_turnover:
            return ConstraintViolation(
                constraint_name="Weekly Turnover",
                severity=ConstraintSeverity.BREACH,
                current_value=turnover_pct,
                limit_value=self.max_weekly_turnover,
                utilization_pct=utilization * 100,
                explanation=(
                    f"Weekly turnover is {float(turnover_pct * 100):.1f}% of NAV, "
                    f"exceeding the {float(self.max_weekly_turnover * 100):.0f}% limit."
                ),
                action_required=(
                    "No new trades allowed until turnover budget resets. "
                    f"Budget resets in {7 - (datetime.now(timezone.utc) - week_ago).days} days."
                ),
            )
        elif utilization > self.warning_threshold:
            remaining = (self.max_weekly_turnover - turnover_pct) * portfolio_nav
            return ConstraintViolation(
                constraint_name="Weekly Turnover",
                severity=ConstraintSeverity.WARNING,
                current_value=turnover_pct,
                limit_value=self.max_weekly_turnover,
                utilization_pct=utilization * 100,
                explanation=(
                    f"Weekly turnover is {float(turnover_pct * 100):.1f}% of NAV, "
                    f"approaching the {float(self.max_weekly_turnover * 100):.0f}% limit."
                ),
                action_required=f"Only {float(remaining):,.0f} TAO of turnover budget remaining this week.",
            )

        return None

    async def _check_slippage_exposure(
        self,
        db: AsyncSession,
        positions: List[Position],
    ) -> List[ConstraintViolation]:
        """Check slippage exposure for positions."""
        violations = []

        for pos in positions:
            # Check if exit slippage exceeds caps
            if pos.exit_slippage_100pct > self.max_slip_100pct:
                subnet = await self._get_subnet(db, pos.netuid)
                name = subnet.name if subnet else f"Subnet {pos.netuid}"

                violations.append(ConstraintViolation(
                    constraint_name="Exit Slippage",
                    severity=ConstraintSeverity.BREACH,
                    current_value=pos.exit_slippage_100pct,
                    limit_value=self.max_slip_100pct,
                    utilization_pct=(pos.exit_slippage_100pct / self.max_slip_100pct * 100) if self.max_slip_100pct else Decimal("0"),
                    explanation=(
                        f"{name} (SN{pos.netuid}): Full exit slippage is "
                        f"{float(pos.exit_slippage_100pct * 100):.1f}%, "
                        f"exceeding the {float(self.max_slip_100pct * 100):.0f}% limit."
                    ),
                    action_required=(
                        "Consider reducing position size to lower exit slippage, "
                        "or waiting for liquidity to improve."
                    ),
                    netuid=pos.netuid,
                ))
            elif pos.exit_slippage_50pct > self.max_slip_50pct:
                subnet = await self._get_subnet(db, pos.netuid)
                name = subnet.name if subnet else f"Subnet {pos.netuid}"

                violations.append(ConstraintViolation(
                    constraint_name="Exit Slippage",
                    severity=ConstraintSeverity.WARNING,
                    current_value=pos.exit_slippage_50pct,
                    limit_value=self.max_slip_50pct,
                    utilization_pct=(pos.exit_slippage_50pct / self.max_slip_50pct * 100) if self.max_slip_50pct else Decimal("0"),
                    explanation=(
                        f"{name} (SN{pos.netuid}): 50% exit slippage is "
                        f"{float(pos.exit_slippage_50pct * 100):.1f}%, "
                        f"exceeding the {float(self.max_slip_50pct * 100):.0f}% limit."
                    ),
                    action_required="Monitor liquidity and consider gradual position reduction.",
                    netuid=pos.netuid,
                ))

        return violations

    async def _get_remaining_turnover(
        self,
        db: AsyncSession,
        snapshot: PortfolioSnapshot,
    ) -> Decimal:
        """Get remaining turnover budget for the week."""
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = select(func.sum(TradeRecommendation.size_tao)).where(
            TradeRecommendation.wallet_address == self.wallet_address,
            TradeRecommendation.status == "executed",
            TradeRecommendation.marked_executed_at >= week_ago,
        )
        result = await db.execute(stmt)
        used = result.scalar() or Decimal("0")

        portfolio_nav = snapshot.nav_mid or Decimal("1")
        used_pct = used / portfolio_nav
        return max(Decimal("0"), self.max_weekly_turnover - used_pct)

    async def _get_existing_alert(
        self,
        db: AsyncSession,
        violation: ConstraintViolation,
    ) -> Optional[Alert]:
        """Check if a similar alert already exists."""
        category = violation.constraint_name.lower().replace(" ", "_")
        stmt = select(Alert).where(
            Alert.wallet_address == self.wallet_address,
            Alert.category == category,
            Alert.is_active == True,
            Alert.netuid == violation.netuid,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _build_summary(
        self,
        violations: List[ConstraintViolation],
        warnings: List[ConstraintViolation],
        total_checked: int,
    ) -> str:
        """Build human-readable summary."""
        if not violations and not warnings:
            return f"All {total_checked} constraints satisfied. Portfolio is within all limits."

        lines = [f"Checked {total_checked} constraints:"]

        if violations:
            lines.append(f"\n❌ {len(violations)} VIOLATIONS:")
            for v in violations:
                lines.append(f"  • {v.constraint_name}: {v.explanation}")

        if warnings:
            lines.append(f"\n⚠️ {len(warnings)} WARNINGS:")
            for w in warnings:
                lines.append(f"  • {w.constraint_name}: {w.explanation}")

        return "\n".join(lines)


# Singleton instance
constraint_enforcer = ConstraintEnforcer()
