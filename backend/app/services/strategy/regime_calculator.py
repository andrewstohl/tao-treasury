"""Taoflow regime calculator.

Implements the state machine for flow regimes:
- Risk On: New buys allowed, sleeve can expand
- Neutral: Higher bar for new buys, prefer adds to winners
- Risk Off: No new buys, sleeve shrinks toward lower bound
- Quarantine (per subnet): No adds, trim 25-50%, monitor 48-72h
- Dead (per subnet): Mandatory accelerated exit
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet, SubnetSnapshot

settings = get_settings()
logger = structlog.get_logger()


class FlowRegime(str, Enum):
    """Flow regime states."""
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"
    QUARANTINE = "quarantine"
    DEAD = "dead"


class RegimeCalculator:
    """Calculates and updates flow regime for subnets.

    Uses multi-horizon flow signals (1d, 3d, 7d, 14d) with persistence
    requirements to avoid whipsaws.
    """

    def __init__(self):
        self.persistence_days = settings.flow_persistence_days
        self.risk_off_threshold = settings.risk_off_flow_threshold
        self.quarantine_threshold = settings.quarantine_flow_threshold

    async def compute_subnet_regime(
        self,
        subnet: Subnet,
        flow_history: Optional[List[Decimal]] = None
    ) -> Tuple[FlowRegime, str]:
        """Compute the flow regime for a single subnet.

        Args:
            subnet: Subnet with taoflow metrics
            flow_history: Optional list of daily flow values (most recent first)

        Returns:
            Tuple of (regime, reason)
        """
        reasons = []

        # Get flow metrics
        flow_1d = subnet.taoflow_1d or Decimal("0")
        flow_3d = subnet.taoflow_3d or Decimal("0")
        flow_7d = subnet.taoflow_7d or Decimal("0")
        flow_14d = subnet.taoflow_14d or Decimal("0")

        # Check for Dead state: Severe sustained outflow
        # 7d and 14d both deeply negative
        if flow_7d < self.quarantine_threshold and flow_14d < self.quarantine_threshold:
            reasons.append(f"Severe sustained outflow: 7d={float(flow_7d):.1%}, 14d={float(flow_14d):.1%}")
            return FlowRegime.DEAD, "; ".join(reasons)

        # Check for Quarantine: Strong negative flow with persistence
        # 7d negative AND (14d negative OR 3 of last 4 days negative)
        if flow_7d < self.risk_off_threshold and flow_14d < self.risk_off_threshold:
            reasons.append(f"Sustained negative flow: 7d={float(flow_7d):.1%}, 14d={float(flow_14d):.1%}")
            return FlowRegime.QUARANTINE, "; ".join(reasons)

        # Check daily flow pattern if history available
        if flow_history and len(flow_history) >= 4:
            negative_days = sum(1 for f in flow_history[:4] if f < 0)
            if negative_days >= 3 and flow_7d < 0:
                reasons.append(f"3+ of last 4 days negative with 7d={float(flow_7d):.1%}")
                return FlowRegime.QUARANTINE, "; ".join(reasons)

        # Check for Risk Off: Moderate negative flow
        if flow_7d < self.risk_off_threshold or (flow_3d < 0 and flow_7d < 0):
            reasons.append(f"Negative flow trend: 3d={float(flow_3d):.1%}, 7d={float(flow_7d):.1%}")
            return FlowRegime.RISK_OFF, "; ".join(reasons)

        # Check for Risk On: Strong positive flow with persistence
        if flow_7d > abs(self.risk_off_threshold) and flow_14d > 0:
            reasons.append(f"Positive flow momentum: 7d={float(flow_7d):.1%}, 14d={float(flow_14d):.1%}")
            return FlowRegime.RISK_ON, "; ".join(reasons)

        # Default: Neutral
        reasons.append(f"Mixed or flat flow: 1d={float(flow_1d):.1%}, 7d={float(flow_7d):.1%}")
        return FlowRegime.NEUTRAL, "; ".join(reasons)

    async def compute_portfolio_regime(self) -> Tuple[FlowRegime, str, Dict[str, int]]:
        """Compute overall portfolio regime based on position-weighted flows.

        Returns:
            Tuple of (regime, reason, regime_counts)
        """
        async with get_db_context() as db:
            # Get all subnets with positions
            from app.models.position import Position

            stmt = select(Position).where(
                Position.wallet_address == settings.wallet_address,
                Position.tao_value_mid > 0
            )
            result = await db.execute(stmt)
            positions = list(result.scalars().all())

            if not positions:
                return FlowRegime.NEUTRAL, "No active positions", {}

            # Count regimes weighted by position value
            regime_values: Dict[FlowRegime, Decimal] = {r: Decimal("0") for r in FlowRegime}
            regime_counts: Dict[str, int] = {r.value: 0 for r in FlowRegime}
            total_value = Decimal("0")

            for pos in positions:
                # Get subnet
                subnet_stmt = select(Subnet).where(Subnet.netuid == pos.netuid)
                subnet_result = await db.execute(subnet_stmt)
                subnet = subnet_result.scalar_one_or_none()

                if subnet:
                    regime = FlowRegime(subnet.flow_regime) if subnet.flow_regime else FlowRegime.NEUTRAL
                    regime_values[regime] += pos.tao_value_mid
                    regime_counts[regime.value] += 1
                    total_value += pos.tao_value_mid

            # Determine overall regime
            if total_value == 0:
                return FlowRegime.NEUTRAL, "No position value", regime_counts

            # If any position is Dead or Quarantine, that dominates
            if regime_counts.get("dead", 0) > 0:
                pct = regime_values[FlowRegime.DEAD] / total_value * 100
                return FlowRegime.RISK_OFF, f"{regime_counts['dead']} positions in Dead state ({pct:.1f}% of value)", regime_counts

            if regime_counts.get("quarantine", 0) > 0:
                pct = regime_values[FlowRegime.QUARANTINE] / total_value * 100
                return FlowRegime.RISK_OFF, f"{regime_counts['quarantine']} positions in Quarantine ({pct:.1f}% of value)", regime_counts

            # Calculate weighted regime
            risk_off_weight = regime_values[FlowRegime.RISK_OFF] / total_value
            risk_on_weight = regime_values[FlowRegime.RISK_ON] / total_value

            if risk_off_weight > Decimal("0.40"):
                return FlowRegime.RISK_OFF, f"Risk-off positions dominate ({float(risk_off_weight):.0%} of value)", regime_counts
            elif risk_on_weight > Decimal("0.50"):
                return FlowRegime.RISK_ON, f"Risk-on positions dominate ({float(risk_on_weight):.0%} of value)", regime_counts
            else:
                return FlowRegime.NEUTRAL, "Mixed regime across positions", regime_counts

    async def update_all_regimes(self) -> Dict[str, any]:
        """Update flow regimes for all subnets.

        Returns:
            Summary of regime updates
        """
        logger.info("Updating flow regimes for all subnets")

        results = {
            "subnets_updated": 0,
            "regime_changes": [],
            "regime_counts": {r.value: 0 for r in FlowRegime},
        }

        async with get_db_context() as db:
            # Get all subnets with pool liquidity
            stmt = select(Subnet).where(Subnet.pool_tao_reserve > 0)
            result = await db.execute(stmt)
            subnets = list(result.scalars().all())

            now = datetime.now(timezone.utc)

            for subnet in subnets:
                old_regime = subnet.flow_regime
                new_regime, reason = await self.compute_subnet_regime(subnet)

                # Update subnet
                subnet.flow_regime = new_regime.value

                # Track regime duration
                if old_regime != new_regime.value:
                    subnet.flow_regime_since = now
                    subnet.flow_regime_days = 0
                    results["regime_changes"].append({
                        "netuid": subnet.netuid,
                        "name": subnet.name,
                        "old": old_regime,
                        "new": new_regime.value,
                        "reason": reason,
                    })
                else:
                    if subnet.flow_regime_since:
                        subnet.flow_regime_days = (now - subnet.flow_regime_since).days

                results["regime_counts"][new_regime.value] += 1
                results["subnets_updated"] += 1

            await db.commit()

        # Compute portfolio regime
        portfolio_regime, portfolio_reason, _ = await self.compute_portfolio_regime()
        results["portfolio_regime"] = portfolio_regime.value
        results["portfolio_reason"] = portfolio_reason

        logger.info("Flow regimes updated",
                   subnets=results["subnets_updated"],
                   changes=len(results["regime_changes"]),
                   portfolio=portfolio_regime.value)

        return results

    def get_regime_policy(self, regime: FlowRegime) -> Dict[str, any]:
        """Get the trading policy for a given regime.

        Returns:
            Dict with policy constraints
        """
        policies = {
            FlowRegime.RISK_ON: {
                "new_buys_allowed": True,
                "adds_to_existing_allowed": True,
                "sleeve_can_expand": True,
                "target_sleeve_bound": "upper",
                "description": "New buys allowed if eligibility passes. Sleeve can expand to upper bound.",
            },
            FlowRegime.NEUTRAL: {
                "new_buys_allowed": True,  # But higher bar
                "adds_to_existing_allowed": True,
                "sleeve_can_expand": False,
                "target_sleeve_bound": "current",
                "description": "Higher bar for new buys. Prefer adds to existing winners.",
            },
            FlowRegime.RISK_OFF: {
                "new_buys_allowed": False,
                "adds_to_existing_allowed": False,
                "sleeve_can_expand": False,
                "target_sleeve_bound": "lower",
                "description": "No new buys. Sleeve shrinks toward lower bound. Prefer Root.",
            },
            FlowRegime.QUARANTINE: {
                "new_buys_allowed": False,
                "adds_to_existing_allowed": False,
                "trim_pct": Decimal("0.25"),  # Trim 25-50%
                "monitor_hours": 48,
                "description": "No adds. Trim 25-50% and monitor 48-72h.",
            },
            FlowRegime.DEAD: {
                "new_buys_allowed": False,
                "adds_to_existing_allowed": False,
                "mandatory_exit": True,
                "exit_accelerated": True,
                "description": "Mandatory exit ladder accelerated, even if it crystallizes larger loss.",
            },
        }
        return policies.get(regime, policies[FlowRegime.NEUTRAL])


# Singleton instance
regime_calculator = RegimeCalculator()
