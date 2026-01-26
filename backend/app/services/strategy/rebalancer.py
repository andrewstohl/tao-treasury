"""Rebalancer for generating trade recommendations.

Implements two rebalance modes per spec:
1. Weekly scheduled rebalance - portfolio-wide optimization
2. Event-driven rebalance - triggered by regime changes, quarantine, etc.

All recommendations are advisory only (no auto-execution per spec).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet
from app.models.position import Position
from app.models.portfolio import PortfolioSnapshot
from app.models.trade import TradeRecommendation
from app.models.slippage import SlippageSurface
from app.services.strategy.regime_calculator import FlowRegime
from app.services.strategy.eligibility_gate import eligibility_gate
from app.services.strategy.position_sizer import position_sizer
from app.services.strategy.macro_regime_detector import macro_regime_detector, MacroRegime

settings = get_settings()
logger = structlog.get_logger()


class TriggerType(str, Enum):
    """Trade trigger types for audit trail."""
    SCHEDULED_REBALANCE = "scheduled_rebalance"
    EVENT_DRIVEN_EXIT = "event_driven_exit"
    OPPORTUNITY_ENTRY = "opportunity_entry"
    RISK_REDUCTION = "risk_reduction"
    QUARANTINE_TRIM = "quarantine_trim"
    DEAD_EXIT = "dead_exit"
    REGIME_SHIFT = "regime_shift"
    CONCENTRATION_BREACH = "concentration_breach"
    TURNOVER_LIMIT = "turnover_limit"


@dataclass
class RebalanceResult:
    """Result of rebalance computation."""
    recommendations: List[TradeRecommendation]
    total_buys_tao: Decimal
    total_sells_tao: Decimal
    turnover_pct: Decimal
    constrained_by_turnover: bool
    summary: str


class Rebalancer:
    """Generates trade recommendations for portfolio rebalancing."""

    def __init__(self):
        self.wallet_address = settings.wallet_address
        self.max_daily_turnover = settings.max_daily_turnover
        self.max_weekly_turnover = settings.max_weekly_turnover
        self.max_position_pct = settings.max_position_concentration

    async def generate_weekly_rebalance(self) -> RebalanceResult:
        """Generate weekly scheduled rebalance recommendations.

        This is the primary rebalance mode, running weekly to:
        1. Exit ineligible positions
        2. Trim overweight positions
        3. Apply macro regime sleeve sizing (shrink/grow sleeve)
        4. Add to underweight positions in eligible universe
        5. Enter new attractive positions (if macro regime allows)
        """
        logger.info("Generating weekly rebalance recommendations")

        recommendations = []
        total_buys = Decimal("0")
        total_sells = Decimal("0")

        # Get macro regime context for dynamic sleeve sizing
        macro_regime_result = await macro_regime_detector.detect_regime()
        macro_policy = macro_regime_detector.get_regime_policy(macro_regime_result.regime)
        new_positions_allowed = macro_policy["new_positions_allowed"]
        sleeve_modifier = macro_policy["sleeve_modifier"]
        root_bias = macro_policy["root_bias"]

        logger.info(
            "Macro regime context for rebalance",
            regime=macro_regime_result.regime.value,
            new_positions_allowed=new_positions_allowed,
            sleeve_modifier=float(sleeve_modifier),
            root_bias=float(root_bias),
        )

        async with get_db_context() as db:
            # Get current portfolio state
            snapshot = await self._get_latest_snapshot(db)
            if not snapshot:
                return self._empty_result("No portfolio snapshot available")

            portfolio_nav = snapshot.nav_mid
            current_sleeve_nav = snapshot.dtao_allocation_tao

            # Compute target sleeve based on macro regime
            target_sleeve_pct, target_sleeve_tao, sleeve_explanation = (
                macro_regime_detector.compute_target_sleeve_allocation(
                    macro_regime_result.regime, portfolio_nav
                )
            )
            sleeve_nav = target_sleeve_tao  # Use target for position sizing

            logger.info(
                "Dynamic sleeve sizing",
                current_sleeve_tao=float(current_sleeve_nav),
                target_sleeve_tao=float(target_sleeve_tao),
                explanation=sleeve_explanation,
            )

            # Get current positions
            positions = await self._get_positions(db)
            position_map = {p.netuid: p for p in positions}

            # Get eligible universe
            eligible = await eligibility_gate.get_eligible_universe()
            eligible_netuids = {e.netuid for e in eligible}

            # Get category allocations for position sizing
            category_allocs = await self._compute_category_allocations(db, positions)

            # Step 1: Generate EXIT recommendations for ineligible positions
            for pos in positions:
                if pos.netuid not in eligible_netuids:
                    rec = await self._create_exit_recommendation(
                        db, pos, TriggerType.EVENT_DRIVEN_EXIT,
                        f"Position no longer eligible for investment universe"
                    )
                    if rec:
                        recommendations.append(rec)
                        total_sells += rec.size_tao

            # Step 2: Check for regime-based exits
            for pos in positions:
                if pos.netuid in eligible_netuids:
                    subnet = await self._get_subnet(db, pos.netuid)
                    if subnet and subnet.flow_regime in [FlowRegime.QUARANTINE.value, FlowRegime.DEAD.value]:
                        trigger = (TriggerType.DEAD_EXIT if subnet.flow_regime == FlowRegime.DEAD.value
                                   else TriggerType.QUARANTINE_TRIM)
                        rec = await self._create_exit_recommendation(
                            db, pos, trigger,
                            f"Subnet in {subnet.flow_regime} regime - exiting per risk policy"
                        )
                        if rec:
                            recommendations.append(rec)
                            total_sells += rec.size_tao

            # Step 3: Trim overweight positions
            for pos in positions:
                if pos.netuid in eligible_netuids:
                    limit = await position_sizer.compute_position_limit(
                        netuid=pos.netuid,
                        portfolio_nav_tao=portfolio_nav,
                        sleeve_nav_tao=sleeve_nav,
                        category_allocations=category_allocs,
                        db=db,
                    )
                    if pos.tao_value_mid > limit.max_position_tao * Decimal("1.05"):
                        # More than 5% over limit - trim
                        trim_amount = pos.tao_value_mid - limit.max_position_tao
                        rec = await self._create_sell_recommendation(
                            db, pos, trim_amount, TriggerType.CONCENTRATION_BREACH,
                            f"Position {float(pos.tao_value_mid / portfolio_nav * 100):.1f}% exceeds "
                            f"{limit.binding_constraint} cap of {float(limit.max_position_tao / portfolio_nav * 100):.1f}%"
                        )
                        if rec:
                            recommendations.append(rec)
                            total_sells += rec.size_tao

            # Step 3.5: Apply macro regime sleeve reduction if needed
            # If current sleeve exceeds target by more than 5%, reduce proportionally
            if current_sleeve_nav > target_sleeve_tao * Decimal("1.05"):
                sleeve_excess = current_sleeve_nav - target_sleeve_tao
                excess_pct = sleeve_excess / current_sleeve_nav

                logger.info(
                    "Sleeve reduction triggered by macro regime",
                    regime=macro_regime_result.regime.value,
                    current_sleeve=float(current_sleeve_nav),
                    target_sleeve=float(target_sleeve_tao),
                    excess_tao=float(sleeve_excess),
                    excess_pct=float(excess_pct),
                )

                # Reduce all positions proportionally to shrink sleeve
                for pos in positions:
                    if pos.netuid in eligible_netuids:
                        # Don't double-count positions already being trimmed
                        already_selling = sum(
                            r.size_tao for r in recommendations
                            if r.netuid == pos.netuid and r.direction == "sell"
                        )
                        remaining_pos = pos.tao_value_mid - already_selling

                        if remaining_pos > Decimal("0"):
                            trim_for_sleeve = remaining_pos * excess_pct
                            if trim_for_sleeve > portfolio_nav * Decimal("0.005"):  # > 0.5% of portfolio
                                rec = await self._create_sell_recommendation(
                                    db, pos, trim_for_sleeve, TriggerType.REGIME_SHIFT,
                                    f"Macro regime {macro_regime_result.regime.value}: "
                                    f"reducing sleeve from {float(current_sleeve_nav / portfolio_nav * 100):.1f}% "
                                    f"to target {float(target_sleeve_tao / portfolio_nav * 100):.1f}%"
                                )
                                if rec:
                                    recommendations.append(rec)
                                    total_sells += rec.size_tao

            # Step 4: Identify entry opportunities
            # Available capital = current sells + any unstaked buffer above minimum
            available_capital = total_sells + max(
                Decimal("0"),
                snapshot.unstaked_buffer_tao - portfolio_nav * settings.unstaked_buffer_min
            )

            # Apply root_bias: Reserve portion of available capital for root stake
            # root_bias is 0.0 (BULL) to 0.25 (CAPITULATION)
            capital_for_sleeve = available_capital * (Decimal("1") - root_bias)
            capital_for_root = available_capital * root_bias

            if capital_for_root > Decimal("0"):
                logger.info(
                    "Root bias applied",
                    regime=macro_regime_result.regime.value,
                    root_bias=float(root_bias),
                    capital_for_root=float(capital_for_root),
                    capital_for_sleeve=float(capital_for_sleeve),
                )

            # Check if new positions are allowed by macro regime
            if not new_positions_allowed:
                logger.info(
                    "New positions blocked by macro regime",
                    regime=macro_regime_result.regime.value,
                    available_capital=float(capital_for_sleeve),
                )
                # Don't add any new positions - capital goes to root or existing adds only
                entry_candidates = []
            else:
                # Score eligible subnets for entry
                entry_candidates = []
                for e in eligible:
                    if e.netuid not in position_map or position_map[e.netuid].tao_value_mid < Decimal("1"):
                        # New entry or very small existing position
                        target, explanation = await position_sizer.get_target_position_size(
                            netuid=e.netuid,
                            portfolio_nav_tao=portfolio_nav,
                            sleeve_nav_tao=sleeve_nav,
                            category_allocations=category_allocs,
                        )
                        if target > Decimal("0"):
                            entry_candidates.append({
                                "netuid": e.netuid,
                                "name": e.name,
                                "score": e.score or 0,
                                "target_tao": target,
                            })

            # Sort by score and allocate capital (respecting macro regime)
            entry_candidates.sort(key=lambda x: x["score"], reverse=True)
            remaining_capital = capital_for_sleeve  # Only use sleeve portion

            for candidate in entry_candidates:
                if remaining_capital <= Decimal("0"):
                    break

                entry_size = min(candidate["target_tao"], remaining_capital)
                if entry_size >= portfolio_nav * Decimal("0.01"):  # At least 1% position
                    rec = await self._create_buy_recommendation(
                        db, candidate["netuid"], entry_size, TriggerType.OPPORTUNITY_ENTRY,
                        f"Attractive entry opportunity (score: {candidate['score']}) - "
                        f"target {float(entry_size):,.1f} TAO "
                        f"[macro: {macro_regime_result.regime.value}]"
                    )
                    if rec:
                        recommendations.append(rec)
                        total_buys += rec.size_tao
                        remaining_capital -= entry_size

            # Step 5: Check turnover constraints
            turnover = (total_buys + total_sells) / portfolio_nav if portfolio_nav else Decimal("0")
            constrained = False

            if turnover > self.max_weekly_turnover:
                # Need to scale down recommendations
                scale = float(self.max_weekly_turnover / turnover) * 0.95  # 5% buffer
                recommendations = self._scale_recommendations(recommendations, scale)
                constrained = True
                logger.warning("Recommendations scaled due to turnover limit",
                              original_turnover=float(turnover),
                              scaled_to=float(self.max_weekly_turnover))

            # Persist recommendations
            for rec in recommendations:
                db.add(rec)
            await db.commit()

        # Build summary
        summary = self._build_summary(recommendations, total_buys, total_sells, turnover, constrained)

        return RebalanceResult(
            recommendations=recommendations,
            total_buys_tao=total_buys,
            total_sells_tao=total_sells,
            turnover_pct=turnover * 100,
            constrained_by_turnover=constrained,
            summary=summary,
        )

    async def generate_event_driven_rebalance(
        self,
        trigger: TriggerType,
        affected_netuids: Optional[List[int]] = None,
    ) -> RebalanceResult:
        """Generate event-driven rebalance recommendations.

        Called when significant events occur:
        - Regime shift to Quarantine/Dead
        - Concentration breach
        - Risk-off trigger (drawdown)
        """
        logger.info("Generating event-driven rebalance", trigger=trigger.value)

        recommendations = []
        total_buys = Decimal("0")
        total_sells = Decimal("0")

        async with get_db_context() as db:
            snapshot = await self._get_latest_snapshot(db)
            if not snapshot:
                return self._empty_result("No portfolio snapshot available")

            portfolio_nav = snapshot.nav_mid

            if trigger == TriggerType.QUARANTINE_TRIM:
                # Find all quarantine positions and create trim recommendations
                positions = await self._get_positions(db)
                for pos in positions:
                    subnet = await self._get_subnet(db, pos.netuid)
                    if subnet and subnet.flow_regime == FlowRegime.QUARANTINE.value:
                        # Trim to 50% per spec for quarantine
                        trim_amount = pos.tao_value_mid * Decimal("0.5")
                        rec = await self._create_sell_recommendation(
                            db, pos, trim_amount, TriggerType.QUARANTINE_TRIM,
                            f"Quarantine regime - reducing position by 50%"
                        )
                        if rec:
                            recommendations.append(rec)
                            total_sells += rec.size_tao

            elif trigger == TriggerType.DEAD_EXIT:
                # Full exit from dead subnets
                positions = await self._get_positions(db)
                for pos in positions:
                    subnet = await self._get_subnet(db, pos.netuid)
                    if subnet and subnet.flow_regime == FlowRegime.DEAD.value:
                        rec = await self._create_exit_recommendation(
                            db, pos, TriggerType.DEAD_EXIT,
                            f"Dead regime - full exit required"
                        )
                        if rec:
                            recommendations.append(rec)
                            total_sells += rec.size_tao

            elif trigger == TriggerType.RISK_REDUCTION:
                # Portfolio-wide risk reduction (drawdown triggered)
                positions = await self._get_positions(db)
                # Reduce all positions by 25%
                for pos in positions:
                    trim_amount = pos.tao_value_mid * Decimal("0.25")
                    rec = await self._create_sell_recommendation(
                        db, pos, trim_amount, TriggerType.RISK_REDUCTION,
                        f"Drawdown triggered risk reduction - reducing by 25%"
                    )
                    if rec:
                        recommendations.append(rec)
                        total_sells += rec.size_tao

            elif trigger == TriggerType.CONCENTRATION_BREACH and affected_netuids:
                # Trim specific over-concentrated positions
                for netuid in affected_netuids:
                    pos = await self._get_position(db, netuid)
                    if pos:
                        rec = await self._create_exit_recommendation(
                            db, pos, TriggerType.CONCENTRATION_BREACH,
                            f"Concentration limit breach - trimming"
                        )
                        if rec:
                            recommendations.append(rec)
                            total_sells += rec.size_tao

            # Check daily turnover limit for event-driven
            turnover = total_sells / portfolio_nav if portfolio_nav else Decimal("0")
            constrained = False

            if turnover > self.max_daily_turnover:
                scale = float(self.max_daily_turnover / turnover) * 0.95
                recommendations = self._scale_recommendations(recommendations, scale)
                constrained = True

            # Persist recommendations
            for rec in recommendations:
                db.add(rec)
            await db.commit()

        summary = self._build_summary(recommendations, total_buys, total_sells, turnover, constrained)

        return RebalanceResult(
            recommendations=recommendations,
            total_buys_tao=total_buys,
            total_sells_tao=total_sells,
            turnover_pct=turnover * 100,
            constrained_by_turnover=constrained,
            summary=summary,
        )

    async def create_exit_ladder(
        self,
        netuid: int,
        total_exit_pct: Decimal,
        num_tranches: int = 3,
        reason: str = "Scheduled exit",
    ) -> List[TradeRecommendation]:
        """Create an exit ladder with multiple tranches.

        Per spec: Large exits should be broken into tranches to minimize slippage.
        """
        recommendations = []

        async with get_db_context() as db:
            pos = await self._get_position(db, netuid)
            if not pos:
                return []

            total_exit_tao = pos.tao_value_mid * total_exit_pct
            tranche_size_tao = total_exit_tao / num_tranches

            # Create parent recommendation for tracking
            parent_rec = await self._create_sell_recommendation(
                db, pos, total_exit_tao, TriggerType.SCHEDULED_REBALANCE,
                f"Exit ladder: {float(total_exit_pct * 100):.0f}% in {num_tranches} tranches"
            )

            if parent_rec:
                parent_rec.total_tranches = num_tranches
                parent_rec.tranche_number = 0  # Parent marker
                db.add(parent_rec)
                await db.flush()

                # Create individual tranche recommendations
                for i in range(1, num_tranches + 1):
                    tranche_rec = TradeRecommendation(
                        wallet_address=self.wallet_address,
                        netuid=netuid,
                        direction="sell",
                        size_alpha=tranche_size_tao / (pos.tao_value_mid / pos.alpha_balance) if pos.alpha_balance else Decimal("0"),
                        size_tao=tranche_size_tao,
                        size_pct_of_position=total_exit_pct / num_tranches,
                        trigger_type=TriggerType.SCHEDULED_REBALANCE.value,
                        reason=f"Tranche {i}/{num_tranches}: {reason}",
                        priority=5 + i,  # Later tranches lower priority
                        tranche_number=i,
                        total_tranches=num_tranches,
                        parent_recommendation_id=parent_rec.id,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    )
                    db.add(tranche_rec)
                    recommendations.append(tranche_rec)

                await db.commit()

        return recommendations

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
        stmt = (
            select(Position)
            .where(
                Position.wallet_address == self.wallet_address,
                Position.tao_value_mid > Decimal("0.01"),  # Filter dust
            )
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

    async def _compute_category_allocations(
        self,
        db: AsyncSession,
        positions: List[Position],
    ) -> Dict[str, Decimal]:
        """Compute current TAO allocation by category."""
        allocations: Dict[str, Decimal] = {}

        for pos in positions:
            subnet = await self._get_subnet(db, pos.netuid)
            category = (subnet.category if subnet else None) or "uncategorized"
            allocations[category] = allocations.get(category, Decimal("0")) + pos.tao_value_mid

        return allocations

    async def _create_exit_recommendation(
        self,
        db: AsyncSession,
        pos: Position,
        trigger: TriggerType,
        reason: str,
    ) -> Optional[TradeRecommendation]:
        """Create a full exit recommendation."""
        return await self._create_sell_recommendation(
            db, pos, pos.tao_value_mid, trigger, reason
        )

    async def _create_sell_recommendation(
        self,
        db: AsyncSession,
        pos: Position,
        size_tao: Decimal,
        trigger: TriggerType,
        reason: str,
    ) -> Optional[TradeRecommendation]:
        """Create a sell recommendation with slippage estimate."""
        if size_tao <= Decimal("0.01"):
            return None

        # Get slippage estimate
        slippage_pct = await self._estimate_slippage(db, pos.netuid, size_tao)
        slippage_tao = size_tao * slippage_pct

        # Calculate alpha amount
        if pos.tao_value_mid > 0:
            alpha_amount = pos.alpha_balance * (size_tao / pos.tao_value_mid)
        else:
            alpha_amount = Decimal("0")

        rec = TradeRecommendation(
            wallet_address=self.wallet_address,
            netuid=pos.netuid,
            direction="sell",
            size_alpha=alpha_amount,
            size_tao=size_tao,
            size_pct_of_position=size_tao / pos.tao_value_mid if pos.tao_value_mid else Decimal("1"),
            estimated_slippage_pct=slippage_pct,
            estimated_slippage_tao=slippage_tao,
            total_estimated_cost_tao=slippage_tao,
            expected_nav_impact_tao=size_tao - slippage_tao,
            trigger_type=trigger.value,
            reason=reason,
            priority=self._get_priority(trigger),
            is_urgent=trigger in [TriggerType.DEAD_EXIT, TriggerType.RISK_REDUCTION],
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        return rec

    async def _create_buy_recommendation(
        self,
        db: AsyncSession,
        netuid: int,
        size_tao: Decimal,
        trigger: TriggerType,
        reason: str,
    ) -> Optional[TradeRecommendation]:
        """Create a buy recommendation with slippage estimate."""
        if size_tao <= Decimal("0.01"):
            return None

        subnet = await self._get_subnet(db, netuid)
        if not subnet:
            return None

        # Get slippage estimate for stake action
        slippage_pct = await self._estimate_slippage(db, netuid, size_tao, action="stake")
        slippage_tao = size_tao * slippage_pct

        # Estimate alpha amount received (rough)
        if subnet.alpha_price_tao > 0:
            alpha_amount = size_tao / subnet.alpha_price_tao * (1 - slippage_pct)
        else:
            alpha_amount = Decimal("0")

        rec = TradeRecommendation(
            wallet_address=self.wallet_address,
            netuid=netuid,
            direction="buy",
            size_alpha=alpha_amount,
            size_tao=size_tao,
            size_pct_of_position=Decimal("1"),  # New position
            estimated_slippage_pct=slippage_pct,
            estimated_slippage_tao=slippage_tao,
            total_estimated_cost_tao=slippage_tao,
            expected_nav_impact_tao=size_tao - slippage_tao,
            trigger_type=trigger.value,
            reason=reason,
            priority=self._get_priority(trigger),
            is_urgent=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        return rec

    async def _estimate_slippage(
        self,
        db: AsyncSession,
        netuid: int,
        size_tao: Decimal,
        action: str = "unstake",
    ) -> Decimal:
        """Estimate slippage for a trade size."""
        stmt = select(SlippageSurface).where(
            SlippageSurface.netuid == netuid,
            SlippageSurface.action == action,
        ).order_by(SlippageSurface.size_tao)

        result = await db.execute(stmt)
        surfaces = list(result.scalars().all())

        if not surfaces:
            return Decimal("0.05")  # Default 5% if no data

        # Interpolate
        for i, s in enumerate(surfaces):
            if s.size_tao >= size_tao:
                if i == 0:
                    return s.slippage_pct
                prev = surfaces[i - 1]
                ratio = (size_tao - prev.size_tao) / (s.size_tao - prev.size_tao)
                return prev.slippage_pct + ratio * (s.slippage_pct - prev.slippage_pct)

        # Extrapolate for sizes beyond cached data
        return surfaces[-1].slippage_pct * Decimal("1.5")

    def _get_priority(self, trigger: TriggerType) -> int:
        """Get priority for a trigger type (1=highest)."""
        priorities = {
            TriggerType.DEAD_EXIT: 1,
            TriggerType.RISK_REDUCTION: 2,
            TriggerType.QUARANTINE_TRIM: 3,
            TriggerType.CONCENTRATION_BREACH: 4,
            TriggerType.EVENT_DRIVEN_EXIT: 5,
            TriggerType.REGIME_SHIFT: 6,
            TriggerType.SCHEDULED_REBALANCE: 7,
            TriggerType.OPPORTUNITY_ENTRY: 8,
        }
        return priorities.get(trigger, 5)

    def _scale_recommendations(
        self,
        recommendations: List[TradeRecommendation],
        scale: float,
    ) -> List[TradeRecommendation]:
        """Scale down recommendations to meet turnover constraints."""
        for rec in recommendations:
            rec.size_tao = rec.size_tao * Decimal(str(scale))
            rec.size_alpha = rec.size_alpha * Decimal(str(scale))
            rec.estimated_slippage_tao = rec.estimated_slippage_tao * Decimal(str(scale))
            rec.total_estimated_cost_tao = rec.total_estimated_cost_tao * Decimal(str(scale))
            rec.reason = f"[Scaled {scale*100:.0f}%] {rec.reason}"
        return recommendations

    def _empty_result(self, reason: str) -> RebalanceResult:
        """Create empty result with reason."""
        return RebalanceResult(
            recommendations=[],
            total_buys_tao=Decimal("0"),
            total_sells_tao=Decimal("0"),
            turnover_pct=Decimal("0"),
            constrained_by_turnover=False,
            summary=reason,
        )

    def _build_summary(
        self,
        recommendations: List[TradeRecommendation],
        total_buys: Decimal,
        total_sells: Decimal,
        turnover: Decimal,
        constrained: bool,
    ) -> str:
        """Build human-readable summary."""
        buys = [r for r in recommendations if r.direction == "buy"]
        sells = [r for r in recommendations if r.direction == "sell"]

        lines = [
            f"Rebalance Summary:",
            f"  {len(sells)} sell recommendations totaling {float(total_sells):,.1f} TAO",
            f"  {len(buys)} buy recommendations totaling {float(total_buys):,.1f} TAO",
            f"  Net turnover: {float(turnover * 100):.1f}%",
        ]

        if constrained:
            lines.append("  ⚠️ Recommendations scaled due to turnover limits")

        urgent = [r for r in recommendations if r.is_urgent]
        if urgent:
            lines.append(f"  🚨 {len(urgent)} urgent recommendations require immediate attention")

        return "\n".join(lines)


# Singleton instance
rebalancer = Rebalancer()
