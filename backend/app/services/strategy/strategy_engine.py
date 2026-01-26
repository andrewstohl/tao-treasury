"""Strategy Engine orchestrator.

Main entry point for the TAO Treasury strategy system.
Coordinates all strategy components:
- Regime calculation
- Eligibility filtering
- Position sizing
- Rebalance recommendations

Per spec: All outputs are advisory with full audit trail.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
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
from app.services.strategy.regime_calculator import regime_calculator, FlowRegime
from app.services.strategy.eligibility_gate import (
    eligibility_gate,
    EligibilityResult,
    ExitabilityLevel,
    ExitabilityResult,
)
from app.services.strategy.position_sizer import position_sizer, PositionLimit
from app.services.strategy.rebalancer import rebalancer, RebalanceResult, TriggerType

settings = get_settings()
logger = structlog.get_logger()


class PortfolioState(str, Enum):
    """Overall portfolio risk state."""
    HEALTHY = "healthy"
    CAUTION = "caution"
    RISK_OFF = "risk_off"
    EMERGENCY = "emergency"


@dataclass
class StrategyAnalysis:
    """Complete strategy analysis output."""
    # Timestamps
    analyzed_at: datetime
    data_as_of: Optional[datetime]

    # Portfolio state
    portfolio_state: PortfolioState
    state_reason: str

    # Regime summary
    regime_summary: Dict[str, int]  # regime -> count of positions
    portfolio_regime: str

    # Eligibility summary
    total_subnets: int
    eligible_subnets: int
    ineligible_reasons: Dict[str, int]  # reason -> count

    # Position analysis
    positions_analyzed: int
    overweight_positions: List[Dict[str, Any]]
    underweight_positions: List[Dict[str, Any]]
    positions_to_exit: List[Dict[str, Any]]

    # Constraints status
    concentration_ok: bool
    category_caps_ok: bool
    turnover_budget_remaining_pct: Decimal

    # Recommendations
    pending_recommendations: int
    urgent_recommendations: int

    # Full explanation
    explanation: str


@dataclass
class ConstraintCheck:
    """Result of a constraint check."""
    name: str
    passed: bool
    current_value: Any
    limit_value: Any
    explanation: str


class StrategyEngine:
    """Main strategy engine orchestrator."""

    def __init__(self):
        self.wallet_address = settings.wallet_address
        self._last_analysis: Optional[StrategyAnalysis] = None
        self._last_analysis_time: Optional[datetime] = None

    async def run_full_analysis(self) -> StrategyAnalysis:
        """Run complete strategy analysis.

        This is the main entry point for understanding portfolio state
        and generating recommendations.
        """
        logger.info("Running full strategy analysis")
        now = datetime.now(timezone.utc)

        async with get_db_context() as db:
            # Get portfolio snapshot
            snapshot = await self._get_latest_snapshot(db)
            data_as_of = snapshot.timestamp if snapshot else None

            # 1. Update regimes
            regime_summary = await regime_calculator.update_all_regimes()
            portfolio_regime_result = await regime_calculator.compute_portfolio_regime()
            portfolio_regime = portfolio_regime_result[0].value  # Extract regime string from tuple

            # 2. Update eligibility
            eligibility_summary = await eligibility_gate.update_subnet_eligibility()

            # 3. Analyze positions
            positions = await self._get_positions(db)
            position_analysis = await self._analyze_positions(db, positions, snapshot)

            # 4. Check all constraints
            constraint_checks = await self._check_all_constraints(db, positions, snapshot)

            # 5. Determine portfolio state
            portfolio_state, state_reason = self._determine_portfolio_state(
                snapshot, portfolio_regime, constraint_checks
            )

            # 6. Count recommendations
            pending_count, urgent_count = await self._count_recommendations(db)

            # Build ineligibility reasons summary
            ineligible_reasons: Dict[str, int] = {}
            stmt = select(Subnet).where(Subnet.is_eligible == False)
            result = await db.execute(stmt)
            ineligible_subnets = result.scalars().all()
            for s in ineligible_subnets:
                if s.ineligibility_reasons:
                    for reason in s.ineligibility_reasons.split("; "):
                        # Normalize reason to category
                        category = self._categorize_ineligibility(reason)
                        ineligible_reasons[category] = ineligible_reasons.get(category, 0) + 1

            # Build regime summary from positions
            regime_counts: Dict[str, int] = {}
            for pos in positions:
                subnet = await self._get_subnet(db, pos.netuid)
                if subnet:
                    regime = subnet.flow_regime or "neutral"
                    regime_counts[regime] = regime_counts.get(regime, 0) + 1

            # Build explanation
            explanation = self._build_analysis_explanation(
                portfolio_state, state_reason, regime_counts, position_analysis, constraint_checks
            )

            analysis = StrategyAnalysis(
                analyzed_at=now,
                data_as_of=data_as_of,
                portfolio_state=portfolio_state,
                state_reason=state_reason,
                regime_summary=regime_counts,
                portfolio_regime=portfolio_regime,
                total_subnets=eligibility_summary["total_checked"],
                eligible_subnets=eligibility_summary["eligible"],
                ineligible_reasons=ineligible_reasons,
                positions_analyzed=len(positions),
                overweight_positions=position_analysis["overweight"],
                underweight_positions=position_analysis["underweight"],
                positions_to_exit=position_analysis["to_exit"],
                concentration_ok=all(c.passed for c in constraint_checks if "concentration" in c.name.lower()),
                category_caps_ok=all(c.passed for c in constraint_checks if "category" in c.name.lower()),
                turnover_budget_remaining_pct=await self._get_turnover_budget_remaining(db, snapshot),
                pending_recommendations=pending_count,
                urgent_recommendations=urgent_count,
                explanation=explanation,
            )

            self._last_analysis = analysis
            self._last_analysis_time = now

            return analysis

    async def trigger_weekly_rebalance(self) -> RebalanceResult:
        """Trigger weekly rebalance recommendation generation."""
        logger.info("Triggering weekly rebalance")
        return await rebalancer.generate_weekly_rebalance()

    async def trigger_event_rebalance(
        self,
        event_type: str,
        affected_netuids: Optional[List[int]] = None,
    ) -> RebalanceResult:
        """Trigger event-driven rebalance.

        Args:
            event_type: Type of event (quarantine, dead, risk_reduction, etc.)
            affected_netuids: Specific subnets affected (if applicable)
        """
        logger.info("Triggering event-driven rebalance", event=event_type)

        trigger_map = {
            "quarantine": TriggerType.QUARANTINE_TRIM,
            "dead": TriggerType.DEAD_EXIT,
            "risk_reduction": TriggerType.RISK_REDUCTION,
            "concentration": TriggerType.CONCENTRATION_BREACH,
            "regime_shift": TriggerType.REGIME_SHIFT,
        }

        trigger = trigger_map.get(event_type, TriggerType.EVENT_DRIVEN_EXIT)
        return await rebalancer.generate_event_driven_rebalance(trigger, affected_netuids)

    async def get_position_limits(self) -> List[PositionLimit]:
        """Get position limits for all eligible subnets."""
        async with get_db_context() as db:
            snapshot = await self._get_latest_snapshot(db)
            if not snapshot:
                return []

            return await position_sizer.compute_all_limits(
                portfolio_nav_tao=snapshot.nav_mid,
                sleeve_nav_tao=snapshot.dtao_allocation_tao,
            )

    async def get_eligible_universe(self) -> List[EligibilityResult]:
        """Get current eligible investment universe."""
        return await eligibility_gate.get_eligible_universe()

    async def check_exitability(self, db: AsyncSession) -> Dict[str, Any]:
        """Check exitability for all current positions.

        Args:
            db: Database session (passed from DI)

        Returns structured assessment of position slippage risk,
        including any that need WARNING attention or FORCE_TRIM action.

        This is used to:
        1. Surface exitability issues in the UI
        2. Generate trim recommendations when enable_exitability_gate=True
        """
        result = await eligibility_gate.check_all_positions_exitability(db)

        # If feature enabled and we have force_trims, generate recommendations
        if result["feature_enabled"] and result["force_trims"]:
            await self._generate_exitability_trim_recommendations(db, result["force_trims"])

        return result

    async def _generate_exitability_trim_recommendations(
        self,
        db: AsyncSession,
        force_trim_positions: List[Dict[str, Any]],
    ) -> None:
        """Generate trim recommendations for positions failing exitability.

        Args:
            db: Database session (passed from DI)
            force_trim_positions: Positions requiring FORCE_TRIM
        """
        logger.info("Generating exitability trim recommendations",
                   count=len(force_trim_positions))

        for pos_data in force_trim_positions:
            netuid = pos_data["netuid"]
            trim_amount = pos_data.get("trim_amount_tao", 0)
            trim_pct = pos_data.get("trim_pct", 0)

            if trim_amount <= 0:
                continue

            # Check for existing pending recommendation
            existing_stmt = select(TradeRecommendation).where(
                TradeRecommendation.wallet_address == self.wallet_address,
                TradeRecommendation.netuid == netuid,
                TradeRecommendation.status == "pending",
                TradeRecommendation.trigger_type == "exitability_trim",
            )
            existing = await db.execute(existing_stmt)
            if existing.scalar_one_or_none():
                continue  # Already have a pending recommendation

            # Create trim recommendation
            rec = TradeRecommendation(
                wallet_address=self.wallet_address,
                netuid=netuid,
                direction="sell",
                size_tao=Decimal(str(trim_amount)),
                trigger_type="exitability_trim",
                reason=f"Exit slippage {pos_data['slippage_100pct']:.1%} exceeds 10% threshold. "
                       f"Trim {trim_pct:.0f}% to restore safe exitability.",
                priority=2,  # High priority but not emergency
                is_urgent=True,
                status="pending",
                estimated_slippage_pct=Decimal(str(pos_data["slippage_100pct"])),
                total_estimated_cost_tao=Decimal(str(trim_amount)) * Decimal(str(pos_data["slippage_100pct"])),
            )
            db.add(rec)

            # Create alert
            alert = Alert(
                wallet_address=self.wallet_address,
                category="exitability",
                severity="warning",
                title=f"Exitability Warning: {pos_data['subnet_name']}",
                message=f"Position exit slippage is {pos_data['slippage_100pct']:.1%}, "
                        f"exceeding the 10% threshold. Recommended trim: {trim_amount:.2f} TAO ({trim_pct:.0f}%).",
                netuid=netuid,
                threshold_value=Decimal("0.10"),
                actual_value=Decimal(str(pos_data["slippage_100pct"])),
                is_active=True,
            )
            db.add(alert)

        await db.commit()

        logger.info("Exitability trim recommendations created",
                   count=len(force_trim_positions))

    async def check_constraints(self) -> List[ConstraintCheck]:
        """Check all portfolio constraints and return status."""
        async with get_db_context() as db:
            snapshot = await self._get_latest_snapshot(db)
            positions = await self._get_positions(db)
            return await self._check_all_constraints(db, positions, snapshot)

    async def get_recommendation_summary(self) -> Dict[str, Any]:
        """Get summary of pending recommendations."""
        async with get_db_context() as db:
            # Get pending recommendations
            stmt = select(TradeRecommendation).where(
                TradeRecommendation.wallet_address == self.wallet_address,
                TradeRecommendation.status == "pending",
            ).order_by(TradeRecommendation.priority, TradeRecommendation.created_at)

            result = await db.execute(stmt)
            recs = list(result.scalars().all())

            buys = [r for r in recs if r.direction == "buy"]
            sells = [r for r in recs if r.direction == "sell"]
            urgent = [r for r in recs if r.is_urgent]

            total_buy_tao = sum(r.size_tao for r in buys)
            total_sell_tao = sum(r.size_tao for r in sells)
            total_cost_tao = sum(r.total_estimated_cost_tao for r in recs)

            return {
                "total_pending": len(recs),
                "buys": len(buys),
                "sells": len(sells),
                "urgent": len(urgent),
                "total_buy_tao": float(total_buy_tao),
                "total_sell_tao": float(total_sell_tao),
                "estimated_costs_tao": float(total_cost_tao),
                "recommendations": [
                    {
                        "id": r.id,
                        "netuid": r.netuid,
                        "direction": r.direction,
                        "size_tao": float(r.size_tao),
                        "trigger": r.trigger_type,
                        "reason": r.reason,
                        "priority": r.priority,
                        "is_urgent": r.is_urgent,
                        "slippage_pct": float(r.estimated_slippage_pct * 100),
                    }
                    for r in recs[:20]  # Limit to top 20
                ],
            }

    async def create_alert(
        self,
        category: str,
        severity: str,
        title: str,
        message: str,
        netuid: Optional[int] = None,
        threshold_value: Optional[Decimal] = None,
        actual_value: Optional[Decimal] = None,
    ) -> Alert:
        """Create a new alert.

        Args:
            category: Alert category (drawdown, liquidity, taoflow, regime_change, etc.)
            severity: Alert severity (critical, warning, info)
            title: Short alert title
            message: Detailed alert message
            netuid: Related subnet (if applicable)
            threshold_value: Threshold that was breached
            actual_value: Actual value that triggered the alert
        """
        async with get_db_context() as db:
            alert = Alert(
                wallet_address=self.wallet_address,
                category=category,
                severity=severity,
                title=title,
                message=message,
                netuid=netuid,
                threshold_value=threshold_value,
                actual_value=actual_value,
                is_active=True,
            )
            db.add(alert)
            await db.commit()
            return alert

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

    async def _get_subnet(self, db: AsyncSession, netuid: int) -> Optional[Subnet]:
        """Get subnet by netuid."""
        stmt = select(Subnet).where(Subnet.netuid == netuid)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _analyze_positions(
        self,
        db: AsyncSession,
        positions: List[Position],
        snapshot: Optional[PortfolioSnapshot],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Analyze positions for weight and eligibility."""
        result = {
            "overweight": [],
            "underweight": [],
            "to_exit": [],
        }

        if not snapshot or snapshot.nav_mid <= 0:
            return result

        portfolio_nav = snapshot.nav_mid
        target_pct = settings.default_position_concentration

        for pos in positions:
            current_pct = pos.tao_value_mid / portfolio_nav
            subnet = await self._get_subnet(db, pos.netuid)

            pos_info = {
                "netuid": pos.netuid,
                "name": subnet.name if subnet else f"Subnet {pos.netuid}",
                "current_tao": float(pos.tao_value_mid),
                "current_pct": float(current_pct * 100),
                "regime": subnet.flow_regime if subnet else "unknown",
            }

            # Check eligibility
            if subnet and not subnet.is_eligible:
                pos_info["reason"] = subnet.ineligibility_reasons
                result["to_exit"].append(pos_info)
            elif current_pct > settings.max_position_concentration:
                pos_info["excess_pct"] = float((current_pct - settings.max_position_concentration) * 100)
                result["overweight"].append(pos_info)
            elif current_pct < target_pct * Decimal("0.5"):
                pos_info["target_pct"] = float(target_pct * 100)
                result["underweight"].append(pos_info)

        return result

    async def _check_all_constraints(
        self,
        db: AsyncSession,
        positions: List[Position],
        snapshot: Optional[PortfolioSnapshot],
    ) -> List[ConstraintCheck]:
        """Check all portfolio constraints."""
        checks = []

        if not snapshot:
            return checks

        portfolio_nav = snapshot.nav_mid

        # 1. Position concentration checks
        for pos in positions:
            current_pct = pos.tao_value_mid / portfolio_nav if portfolio_nav else Decimal("0")
            subnet = await self._get_subnet(db, pos.netuid)
            name = subnet.name if subnet else f"SN{pos.netuid}"

            checks.append(ConstraintCheck(
                name=f"Concentration: {name}",
                passed=current_pct <= settings.max_position_concentration,
                current_value=f"{float(current_pct * 100):.1f}%",
                limit_value=f"{float(settings.max_position_concentration * 100):.0f}%",
                explanation=f"{name} is {float(current_pct * 100):.1f}% of portfolio (max {float(settings.max_position_concentration * 100):.0f}%)",
            ))

        # 2. Category concentration check (skip "uncategorized" - limit only applies to explicit categories)
        category_totals: Dict[str, Decimal] = {}
        for pos in positions:
            subnet = await self._get_subnet(db, pos.netuid)
            category = (subnet.category if subnet else None) or "uncategorized"
            category_totals[category] = category_totals.get(category, Decimal("0")) + pos.tao_value_mid

        sleeve_nav = snapshot.dtao_allocation_tao or Decimal("1")
        for category, total in category_totals.items():
            # Skip "uncategorized" - the 30% limit only applies to explicit categories
            if category == "uncategorized":
                continue
            category_pct = total / sleeve_nav if sleeve_nav else Decimal("0")
            checks.append(ConstraintCheck(
                name=f"Category: {category}",
                passed=category_pct <= settings.max_category_concentration_sleeve,
                current_value=f"{float(category_pct * 100):.1f}%",
                limit_value=f"{float(settings.max_category_concentration_sleeve * 100):.0f}%",
                explanation=f"{category} category is {float(category_pct * 100):.1f}% of sleeve (max {float(settings.max_category_concentration_sleeve * 100):.0f}%)",
            ))

        # 3. Drawdown check
        drawdown = snapshot.drawdown_from_ath if snapshot.drawdown_from_ath else Decimal("0")
        checks.append(ConstraintCheck(
            name="Drawdown: Soft limit",
            passed=drawdown <= settings.soft_drawdown_limit,
            current_value=f"{float(drawdown * 100):.1f}%",
            limit_value=f"{float(settings.soft_drawdown_limit * 100):.0f}%",
            explanation=f"Drawdown is {float(drawdown * 100):.1f}% (soft limit {float(settings.soft_drawdown_limit * 100):.0f}%)",
        ))

        checks.append(ConstraintCheck(
            name="Drawdown: Hard limit",
            passed=drawdown <= settings.hard_drawdown_limit,
            current_value=f"{float(drawdown * 100):.1f}%",
            limit_value=f"{float(settings.hard_drawdown_limit * 100):.0f}%",
            explanation=f"Drawdown is {float(drawdown * 100):.1f}% (hard limit {float(settings.hard_drawdown_limit * 100):.0f}%)",
        ))

        # 4. Position count check
        pos_count = len(positions)
        checks.append(ConstraintCheck(
            name="Position count",
            passed=settings.min_positions <= pos_count <= settings.max_positions,
            current_value=str(pos_count),
            limit_value=f"{settings.min_positions}-{settings.max_positions}",
            explanation=f"Portfolio has {pos_count} positions (target {settings.min_positions}-{settings.max_positions})",
        ))

        return checks

    async def _count_recommendations(self, db: AsyncSession) -> tuple[int, int]:
        """Count pending and urgent recommendations."""
        stmt = select(func.count()).select_from(TradeRecommendation).where(
            TradeRecommendation.wallet_address == self.wallet_address,
            TradeRecommendation.status == "pending",
        )
        result = await db.execute(stmt)
        pending = result.scalar() or 0

        urgent_stmt = select(func.count()).select_from(TradeRecommendation).where(
            TradeRecommendation.wallet_address == self.wallet_address,
            TradeRecommendation.status == "pending",
            TradeRecommendation.is_urgent == True,
        )
        urgent_result = await db.execute(urgent_stmt)
        urgent = urgent_result.scalar() or 0

        return pending, urgent

    async def _get_turnover_budget_remaining(
        self,
        db: AsyncSession,
        snapshot: Optional[PortfolioSnapshot],
    ) -> Decimal:
        """Calculate remaining weekly turnover budget."""
        if not snapshot:
            return Decimal("100")

        # Sum turnover from last 7 days of executed recommendations
        from datetime import timedelta
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        stmt = select(func.sum(TradeRecommendation.size_tao)).where(
            TradeRecommendation.wallet_address == self.wallet_address,
            TradeRecommendation.status == "executed",
            TradeRecommendation.marked_executed_at >= week_ago,
        )
        result = await db.execute(stmt)
        executed_tao = result.scalar() or Decimal("0")

        used_pct = executed_tao / snapshot.nav_mid if snapshot.nav_mid else Decimal("0")
        remaining = settings.max_weekly_turnover - used_pct

        return max(Decimal("0"), remaining * 100)

    def _determine_portfolio_state(
        self,
        snapshot: Optional[PortfolioSnapshot],
        portfolio_regime: str,
        constraint_checks: List[ConstraintCheck],
    ) -> tuple[PortfolioState, str]:
        """Determine overall portfolio state."""
        if not snapshot:
            return PortfolioState.CAUTION, "No portfolio data available"

        # Check for emergency conditions
        drawdown = snapshot.drawdown_from_ath or Decimal("0")
        if drawdown > settings.hard_drawdown_limit:
            return PortfolioState.EMERGENCY, f"Drawdown {float(drawdown * 100):.1f}% exceeds hard limit"

        # Check for risk-off conditions
        if portfolio_regime in [FlowRegime.RISK_OFF.value, FlowRegime.QUARANTINE.value]:
            return PortfolioState.RISK_OFF, f"Portfolio in {portfolio_regime} regime"

        if drawdown > settings.soft_drawdown_limit:
            return PortfolioState.RISK_OFF, f"Drawdown {float(drawdown * 100):.1f}% exceeds soft limit"

        # Check for caution conditions
        failed_checks = [c for c in constraint_checks if not c.passed]
        if failed_checks:
            return PortfolioState.CAUTION, f"{len(failed_checks)} constraint(s) breached"

        if portfolio_regime == FlowRegime.NEUTRAL.value:
            return PortfolioState.CAUTION, "Portfolio in neutral regime - monitor for direction"

        # Healthy state
        return PortfolioState.HEALTHY, "All constraints satisfied, positive flow regime"

    def _categorize_ineligibility(self, reason: str) -> str:
        """Categorize ineligibility reason for summary."""
        reason_lower = reason.lower()
        if "emission" in reason_lower:
            return "Low emissions"
        if "liquidity" in reason_lower:
            return "Low liquidity"
        if "holder" in reason_lower:
            return "Low holder count"
        if "age" in reason_lower or "new" in reason_lower:
            return "Too new"
        if "owner" in reason_lower or "take" in reason_lower:
            return "High owner take"
        if "flow" in reason_lower or "regime" in reason_lower:
            return "Negative flow"
        if "blocked" in reason_lower or "slippage" in reason_lower:
            return "High slippage"
        if "validator" in reason_lower:
            return "Validator quality"
        return "Other"

    def _build_analysis_explanation(
        self,
        state: PortfolioState,
        state_reason: str,
        regime_counts: Dict[str, int],
        position_analysis: Dict[str, List[Dict[str, Any]]],
        constraint_checks: List[ConstraintCheck],
    ) -> str:
        """Build detailed analysis explanation."""
        lines = [
            f"Portfolio State: {state.value.upper()}",
            f"Reason: {state_reason}",
            "",
            "Regime Distribution:",
        ]

        for regime, count in sorted(regime_counts.items()):
            lines.append(f"  {regime}: {count} positions")

        lines.append("")
        lines.append("Position Analysis:")
        lines.append(f"  Overweight: {len(position_analysis['overweight'])}")
        lines.append(f"  Underweight: {len(position_analysis['underweight'])}")
        lines.append(f"  To exit: {len(position_analysis['to_exit'])}")

        failed_checks = [c for c in constraint_checks if not c.passed]
        if failed_checks:
            lines.append("")
            lines.append("Constraint Violations:")
            for check in failed_checks:
                lines.append(f"  ❌ {check.explanation}")

        return "\n".join(lines)


# Singleton instance
strategy_engine = StrategyEngine()
