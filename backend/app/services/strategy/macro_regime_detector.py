"""TAO Macro Regime Detector.

Phase 2A: Portfolio-level market regime classification.

Classifies overall TAO market conditions into regimes that inform
portfolio-wide strategy adjustments (e.g., dynamic sleeve sizing).

Macro Regimes:
- BULL: Strong positive flows, low drawdown, expanding market
- ACCUMULATION: Bottoming/recovery zone, good DCA opportunity
- NEUTRAL: Mixed signals, maintain current allocations
- DISTRIBUTION: Topping formation, slowing inflows, elevated caution
- BEAR: Negative flows, contracting market, defensive posture
- CAPITULATION: Severe drawdown + panic outflows, max defensive

Uses signals:
- Aggregate taoflow across all subnets
- Portfolio drawdown from ATH
- Distribution of subnet flow regimes
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Optional, Tuple
from enum import Enum

import structlog
from sqlalchemy import select, func

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet, SubnetSnapshot
from app.models.portfolio import PortfolioSnapshot, NAVHistory

logger = structlog.get_logger()


class MacroRegime(str, Enum):
    """TAO macro market regime states.

    Ordered by risk appetite from most aggressive to most defensive.
    """
    BULL = "bull"                    # Strong positive flows, expand sleeve
    ACCUMULATION = "accumulation"    # Bottoming zone, lean into DCA
    NEUTRAL = "neutral"              # Mixed signals, maintain current
    DISTRIBUTION = "distribution"    # Topping signs, elevated caution
    BEAR = "bear"                    # Defensive posture, shrink sleeve
    CAPITULATION = "capitulation"    # Max defensive, preserve capital


@dataclass
class MacroRegimeResult:
    """Result of macro regime detection."""
    regime: MacroRegime
    confidence: str  # "high", "medium", "low"
    reason: str
    signals: Dict[str, any]
    timestamp: datetime


@dataclass
class MacroSignals:
    """Aggregate signals for macro regime detection."""
    aggregate_flow_7d: Decimal           # Sum of 7d taoflow across subnets
    aggregate_flow_14d: Decimal          # Sum of 14d taoflow across subnets
    drawdown_from_ath: Decimal           # Current portfolio drawdown
    regime_distribution: Dict[str, int]  # Count of subnets per flow regime
    risk_off_pct: Decimal                # % of subnets in risk_off or worse
    total_subnets: int
    total_liquidity_tao: Decimal         # Sum of pool TAO across subnets


class MacroRegimeDetector:
    """Detects TAO macro market regime from aggregate signals.

    Uses a simple rule-based classifier with the following priority:
    1. CAPITULATION: Severe drawdown + severe outflow (max defensive)
    2. BULL: Strong inflows + low drawdown (max aggressive)
    3. BEAR: Moderate outflows OR high risk-off concentration
    4. ACCUMULATION: Bottoming zone with stabilizing flows
    5. DISTRIBUTION: Near ATH but slowing/negative flows
    6. NEUTRAL: Default when signals are mixed
    """

    def __init__(self):
        # Defer settings initialization to avoid import-time side effects
        settings = get_settings()
        self._settings = settings

        self.enabled = settings.enable_macro_regime_detection

        # Flow thresholds
        self.bull_flow_threshold = settings.macro_bull_flow_threshold
        self.bear_flow_threshold = settings.macro_bear_flow_threshold
        self.capitulation_flow_threshold = settings.macro_capitulation_flow_threshold

        # Drawdown thresholds
        self.accumulation_drawdown_min = settings.macro_accumulation_drawdown_min
        self.accumulation_drawdown_max = settings.macro_accumulation_drawdown_max
        self.capitulation_drawdown = settings.macro_capitulation_drawdown

        # Lookback period
        self.lookback_days = settings.macro_regime_lookback_days

    async def get_aggregate_signals(self, db) -> MacroSignals:
        """Compute aggregate signals from all subnets.

        Args:
            db: Database session

        Returns:
            MacroSignals with computed aggregate metrics
        """
        # Get all active subnets (with pool liquidity)
        stmt = select(Subnet).where(Subnet.pool_tao_reserve > 0)
        result = await db.execute(stmt)
        subnets = list(result.scalars().all())

        if not subnets:
            return MacroSignals(
                aggregate_flow_7d=Decimal("0"),
                aggregate_flow_14d=Decimal("0"),
                drawdown_from_ath=Decimal("0"),
                regime_distribution={},
                risk_off_pct=Decimal("0"),
                total_subnets=0,
                total_liquidity_tao=Decimal("0"),
            )

        # Aggregate flow signals
        total_flow_7d = sum((s.taoflow_7d or Decimal("0")) for s in subnets)
        total_flow_14d = sum((s.taoflow_14d or Decimal("0")) for s in subnets)
        total_liquidity = sum((s.pool_tao_reserve or Decimal("0")) for s in subnets)

        # Normalize flows by liquidity for percentage
        if total_liquidity > 0:
            aggregate_flow_7d = total_flow_7d / total_liquidity
            aggregate_flow_14d = total_flow_14d / total_liquidity
        else:
            aggregate_flow_7d = Decimal("0")
            aggregate_flow_14d = Decimal("0")

        # Regime distribution
        regime_counts: Dict[str, int] = {}
        for subnet in subnets:
            regime = subnet.flow_regime or "neutral"
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

        # Calculate risk-off percentage (risk_off, quarantine, dead)
        risk_off_count = (
            regime_counts.get("risk_off", 0) +
            regime_counts.get("quarantine", 0) +
            regime_counts.get("dead", 0)
        )
        risk_off_pct = Decimal(str(risk_off_count / len(subnets))) if subnets else Decimal("0")

        # Get portfolio drawdown from most recent snapshot
        drawdown = await self._get_portfolio_drawdown(db)

        return MacroSignals(
            aggregate_flow_7d=aggregate_flow_7d,
            aggregate_flow_14d=aggregate_flow_14d,
            drawdown_from_ath=drawdown,
            regime_distribution=regime_counts,
            risk_off_pct=risk_off_pct,
            total_subnets=len(subnets),
            total_liquidity_tao=total_liquidity,
        )

    async def _get_portfolio_drawdown(self, db) -> Decimal:
        """Get current portfolio drawdown from ATH.

        Args:
            db: Database session

        Returns:
            Drawdown as decimal (0.15 = 15% drawdown)
        """
        # Try NAVHistory first for accurate ATH
        stmt = (
            select(NAVHistory)
            .where(NAVHistory.wallet_address == self._settings.wallet_address)
            .order_by(NAVHistory.date.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        nav_history = result.scalar_one_or_none()

        if nav_history and nav_history.nav_exec_ath and nav_history.nav_exec_ath > 0:
            current_nav = nav_history.nav_exec_close or Decimal("0")
            ath = nav_history.nav_exec_ath
            if current_nav > 0:
                drawdown = (ath - current_nav) / ath
                return max(Decimal("0"), drawdown)

        # Fallback to PortfolioSnapshot
        stmt = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.wallet_address == self._settings.wallet_address)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot:
            return snapshot.drawdown_from_ath or Decimal("0")

        return Decimal("0")

    def classify_regime(self, signals: MacroSignals) -> MacroRegimeResult:
        """Classify macro regime from aggregate signals.

        Priority order (checked first wins):
        1. CAPITULATION: Severe drawdown AND severe outflow
        2. BULL: Strong inflows AND low drawdown
        3. BEAR: Moderate outflows OR high risk-off concentration
        4. ACCUMULATION: In drawdown zone with stabilizing/positive flows
        5. DISTRIBUTION: Low drawdown but negative/flat flows
        6. NEUTRAL: Default

        Args:
            signals: Aggregate market signals

        Returns:
            MacroRegimeResult with regime classification
        """
        now = datetime.now(timezone.utc)
        flow_7d = signals.aggregate_flow_7d
        flow_14d = signals.aggregate_flow_14d
        drawdown = signals.drawdown_from_ath
        risk_off_pct = signals.risk_off_pct

        # Build signal dict for debugging/logging
        signal_dict = {
            "aggregate_flow_7d": float(flow_7d),
            "aggregate_flow_14d": float(flow_14d),
            "drawdown_from_ath": float(drawdown),
            "risk_off_pct": float(risk_off_pct),
            "total_subnets": signals.total_subnets,
            "regime_distribution": signals.regime_distribution,
        }

        # 1. CAPITULATION: Severe drawdown + severe outflow
        if (drawdown >= self.capitulation_drawdown and
            flow_7d <= self.capitulation_flow_threshold):
            return MacroRegimeResult(
                regime=MacroRegime.CAPITULATION,
                confidence="high",
                reason=f"Severe drawdown ({float(drawdown):.1%}) with panic outflows ({float(flow_7d):.1%} 7d flow)",
                signals=signal_dict,
                timestamp=now,
            )

        # 2. BULL: Strong inflows + low drawdown
        if (flow_7d >= self.bull_flow_threshold and
            flow_14d >= 0 and
            drawdown < self.accumulation_drawdown_min):
            confidence = "high" if flow_14d >= self.bull_flow_threshold else "medium"
            return MacroRegimeResult(
                regime=MacroRegime.BULL,
                confidence=confidence,
                reason=f"Strong inflows ({float(flow_7d):.1%} 7d) with low drawdown ({float(drawdown):.1%})",
                signals=signal_dict,
                timestamp=now,
            )

        # 3. BEAR: Moderate outflows OR high risk-off concentration
        if flow_7d <= self.bear_flow_threshold:
            confidence = "high" if flow_14d <= self.bear_flow_threshold else "medium"
            return MacroRegimeResult(
                regime=MacroRegime.BEAR,
                confidence=confidence,
                reason=f"Negative flows ({float(flow_7d):.1%} 7d, {float(flow_14d):.1%} 14d)",
                signals=signal_dict,
                timestamp=now,
            )

        if risk_off_pct >= Decimal("0.40"):  # 40%+ subnets in risk-off or worse
            return MacroRegimeResult(
                regime=MacroRegime.BEAR,
                confidence="medium",
                reason=f"High risk-off concentration ({float(risk_off_pct):.0%} of subnets)",
                signals=signal_dict,
                timestamp=now,
            )

        # 4. ACCUMULATION: In drawdown zone with stabilizing flows
        if (self.accumulation_drawdown_min <= drawdown <= self.accumulation_drawdown_max and
            flow_7d >= self.bear_flow_threshold):  # Not in severe outflow
            confidence = "high" if flow_7d >= 0 else "medium"
            return MacroRegimeResult(
                regime=MacroRegime.ACCUMULATION,
                confidence=confidence,
                reason=f"Drawdown zone ({float(drawdown):.1%}) with stabilizing flows ({float(flow_7d):.1%})",
                signals=signal_dict,
                timestamp=now,
            )

        # 5. DISTRIBUTION: Low drawdown but negative/flat flows
        # Decelerating = recent (7d) weaker than longer average (14d)
        if (drawdown < self.accumulation_drawdown_min and
            self.bear_flow_threshold < flow_7d < self.bull_flow_threshold and
            flow_7d < flow_14d):  # Decelerating flows (7d weaker than 14d)
            return MacroRegimeResult(
                regime=MacroRegime.DISTRIBUTION,
                confidence="medium",
                reason=f"Near highs ({float(drawdown):.1%} drawdown) but decelerating flows (7d: {float(flow_7d):.1%}, 14d: {float(flow_14d):.1%})",
                signals=signal_dict,
                timestamp=now,
            )

        # 6. NEUTRAL: Default for mixed signals
        return MacroRegimeResult(
            regime=MacroRegime.NEUTRAL,
            confidence="low",
            reason=f"Mixed signals (flow: {float(flow_7d):.1%}, drawdown: {float(drawdown):.1%})",
            signals=signal_dict,
            timestamp=now,
        )

    async def detect_regime(self) -> MacroRegimeResult:
        """Detect current TAO macro regime.

        Main entry point for regime detection.

        Returns:
            MacroRegimeResult with current regime classification
        """
        if not self.enabled:
            return MacroRegimeResult(
                regime=MacroRegime.NEUTRAL,
                confidence="low",
                reason="Macro regime detection disabled",
                signals={},
                timestamp=datetime.now(timezone.utc),
            )

        async with get_db_context() as db:
            signals = await self.get_aggregate_signals(db)
            result = self.classify_regime(signals)

            logger.info(
                "Macro regime detected",
                regime=result.regime.value,
                confidence=result.confidence,
                reason=result.reason,
                flow_7d=float(signals.aggregate_flow_7d),
                drawdown=float(signals.drawdown_from_ath),
            )

            return result

    def get_regime_policy(self, regime: MacroRegime) -> Dict[str, any]:
        """Get portfolio policy adjustments for a given macro regime.

        Returns target sleeve bounds and strategy adjustments.

        Args:
            regime: The macro regime

        Returns:
            Dict with policy parameters
        """
        policies = {
            MacroRegime.BULL: {
                "sleeve_target": "upper",
                "sleeve_modifier": Decimal("1.0"),  # Full sleeve
                "new_positions_allowed": True,
                "aggressive_rebalancing": True,
                "root_bias": Decimal("0"),  # No extra root preference
                "description": "Expand sleeve to upper bound. Aggressive accumulation allowed.",
            },
            MacroRegime.ACCUMULATION: {
                "sleeve_target": "mid_upper",
                "sleeve_modifier": Decimal("0.85"),  # 85% of max
                "new_positions_allowed": True,
                "aggressive_rebalancing": False,
                "root_bias": Decimal("0.05"),  # Slight root preference
                "description": "Good DCA zone. Measured accumulation in high-conviction subnets.",
            },
            MacroRegime.NEUTRAL: {
                "sleeve_target": "mid",
                "sleeve_modifier": Decimal("0.70"),  # 70% of max
                "new_positions_allowed": True,
                "aggressive_rebalancing": False,
                "root_bias": Decimal("0.10"),  # Moderate root preference
                "description": "Maintain current allocations. Wait for clearer signals.",
            },
            MacroRegime.DISTRIBUTION: {
                "sleeve_target": "mid_lower",
                "sleeve_modifier": Decimal("0.55"),  # 55% of max
                "new_positions_allowed": False,
                "aggressive_rebalancing": False,
                "root_bias": Decimal("0.15"),  # Elevated root preference
                "description": "Reduce exposure. No new positions. Favor exits to root.",
            },
            MacroRegime.BEAR: {
                "sleeve_target": "lower",
                "sleeve_modifier": Decimal("0.40"),  # 40% of max
                "new_positions_allowed": False,
                "aggressive_rebalancing": False,
                "root_bias": Decimal("0.20"),  # Strong root preference
                "description": "Defensive posture. Shrink sleeve toward minimum.",
            },
            MacroRegime.CAPITULATION: {
                "sleeve_target": "minimum",
                "sleeve_modifier": Decimal("0.25"),  # 25% of max
                "new_positions_allowed": False,
                "aggressive_rebalancing": False,
                "root_bias": Decimal("0.25"),  # Maximum root preference
                "description": "Max defensive. Preserve capital. Only hold highest conviction.",
            },
        }
        return policies.get(regime, policies[MacroRegime.NEUTRAL])


    def compute_target_sleeve_allocation(
        self,
        regime: MacroRegime,
        portfolio_nav_tao: Decimal,
    ) -> Tuple[Decimal, Decimal, str]:
        """Compute target sleeve allocation based on macro regime.

        Uses the sleeve_modifier to interpolate between min and max sleeve bounds.
        Formula: target = min + modifier * (max - min)

        Args:
            regime: Current macro regime
            portfolio_nav_tao: Total portfolio NAV in TAO

        Returns:
            Tuple of (target_sleeve_pct, target_sleeve_tao, explanation)
        """
        policy = self.get_regime_policy(regime)
        modifier = policy["sleeve_modifier"]

        # Get allocation bounds from config
        sleeve_min = self._settings.dtao_allocation_min
        sleeve_max = self._settings.dtao_allocation_max

        # Interpolate target based on modifier
        target_pct = sleeve_min + modifier * (sleeve_max - sleeve_min)
        target_tao = portfolio_nav_tao * target_pct

        explanation = (
            f"Macro regime {regime.value} (modifier {float(modifier):.0%}): "
            f"Target sleeve {float(target_pct):.1%} of NAV = {float(target_tao):,.1f} TAO "
            f"(range: {float(sleeve_min):.0%} - {float(sleeve_max):.0%})"
        )

        return target_pct, target_tao, explanation

    async def get_sleeve_sizing_context(self) -> Dict[str, any]:
        """Get full sleeve sizing context for dashboard/rebalancer.

        Returns:
            Dict with regime, target allocation, and policy details
        """
        result = await self.detect_regime()
        policy = self.get_regime_policy(result.regime)

        # Get allocation bounds
        sleeve_min = self._settings.dtao_allocation_min
        sleeve_max = self._settings.dtao_allocation_max
        modifier = policy["sleeve_modifier"]
        target_pct = sleeve_min + modifier * (sleeve_max - sleeve_min)

        return {
            "regime": result.regime.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "sleeve_modifier": float(modifier),
            "target_sleeve_pct": float(target_pct),
            "sleeve_min_pct": float(sleeve_min),
            "sleeve_max_pct": float(sleeve_max),
            "new_positions_allowed": policy["new_positions_allowed"],
            "aggressive_rebalancing": policy["aggressive_rebalancing"],
            "root_bias": float(policy["root_bias"]),
            "description": policy["description"],
            "feature_enabled": self.enabled,
            "signals": result.signals,
        }


# Lazy singleton instance
_macro_regime_detector: Optional[MacroRegimeDetector] = None


def get_macro_regime_detector() -> MacroRegimeDetector:
    """Get or create the MacroRegimeDetector singleton."""
    global _macro_regime_detector
    if _macro_regime_detector is None:
        _macro_regime_detector = MacroRegimeDetector()
    return _macro_regime_detector


class _LazyMacroRegimeDetector:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_macro_regime_detector(), name)


macro_regime_detector = _LazyMacroRegimeDetector()
