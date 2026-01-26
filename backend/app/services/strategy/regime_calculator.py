"""Taoflow regime calculator.

Implements the state machine for flow regimes:
- Risk On: New buys allowed, sleeve can expand
- Neutral: Higher bar for new buys, prefer adds to winners
- Risk Off: No new buys, sleeve shrinks toward lower bound
- Quarantine (per subnet): No adds, trim 25-50%, monitor 48-72h
- Dead (per subnet): Mandatory accelerated exit

Phase 1C adds persistence requirements to avoid whipsaws:
- Regime transitions require N consecutive days of the candidate regime
- Configurable per regime type (e.g., 2 days for RiskOn/Off, 3 for Quarantine)
- Feature flag: enable_regime_persistence (default off)

Phase 1B adds emissions collapse detection:
- Computes 7d emission_share delta from SubnetSnapshot history
- 30% drop -> Risk-Off, 50% drop -> Quarantine, near-zero -> Dead
- Can override flow-based regime when emissions collapse is severe
- Feature flag: enable_emissions_collapse_detection (default off)
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet, SubnetSnapshot

logger = structlog.get_logger()


class FlowRegime(str, Enum):
    """Flow regime states."""
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"
    QUARANTINE = "quarantine"
    DEAD = "dead"


@dataclass
class EmissionsCollapseResult:
    """Result of emissions collapse detection for a subnet."""
    netuid: int
    has_collapse: bool
    severity: Optional[str]  # "warning", "severe", "critical"
    suggested_regime: Optional[FlowRegime]
    current_emission_share: Decimal
    baseline_emission_share: Optional[Decimal]  # 7d ago
    delta_pct: Optional[Decimal]  # Percentage change
    reason: str


class RegimeCalculator:
    """Calculates and updates flow regime for subnets.

    Uses multi-horizon flow signals (1d, 3d, 7d, 14d) with persistence
    requirements to avoid whipsaws.
    """

    def __init__(self):
        settings = get_settings()
        self.persistence_days = settings.flow_persistence_days
        self.risk_off_threshold = settings.risk_off_flow_threshold
        self.quarantine_threshold = settings.quarantine_flow_threshold

        # Persistence settings (Phase 1C - anti-whipsaw)
        self.enable_persistence = settings.enable_regime_persistence
        self.persistence_requirements = {
            FlowRegime.RISK_ON: settings.regime_persistence_risk_on,
            FlowRegime.NEUTRAL: 1,  # No persistence required for Neutral
            FlowRegime.RISK_OFF: settings.regime_persistence_risk_off,
            FlowRegime.QUARANTINE: settings.regime_persistence_quarantine,
            FlowRegime.DEAD: settings.regime_persistence_dead,
        }

        # Emissions collapse detection (Phase 1B)
        self.enable_emissions_collapse = settings.enable_emissions_collapse_detection
        self.emissions_warning_threshold = settings.emissions_collapse_warning_threshold
        self.emissions_severe_threshold = settings.emissions_collapse_severe_threshold
        self.emissions_near_zero_threshold = settings.emissions_near_zero_threshold
        self.emissions_lookback_days = settings.emissions_lookback_days

        # Store wallet address for queries
        self._wallet_address = settings.wallet_address

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

    def apply_persistence(
        self,
        subnet: Subnet,
        candidate_regime: FlowRegime,
        candidate_reason: str,
    ) -> Tuple[FlowRegime, str, bool]:
        """Apply persistence requirement to regime transition.

        Checks if a regime transition should be allowed based on
        how many consecutive days the candidate regime has been computed.

        Args:
            subnet: Subnet with current regime and candidate tracking
            candidate_regime: The regime computed for today
            candidate_reason: Reason for the candidate regime

        Returns:
            Tuple of (final_regime, reason, did_transition)
        """
        if not self.enable_persistence:
            # Feature disabled - allow immediate transitions
            return candidate_regime, candidate_reason, True

        current_regime = FlowRegime(subnet.flow_regime) if subnet.flow_regime else FlowRegime.NEUTRAL
        current_candidate = FlowRegime(subnet.regime_candidate) if subnet.regime_candidate else None
        candidate_days = subnet.regime_candidate_days or 0

        # If candidate matches current regime, no transition needed
        if candidate_regime == current_regime:
            # Reset candidate tracking since we're stable
            return current_regime, candidate_reason, False

        # Check if this is the same candidate as before
        if current_candidate == candidate_regime:
            # Same candidate - increment days
            new_candidate_days = candidate_days + 1
        else:
            # Different candidate - reset to 1
            new_candidate_days = 1

        # Get persistence requirement for this transition
        required_days = self.persistence_requirements.get(candidate_regime, 2)

        # Check if we've met the persistence requirement
        if new_candidate_days >= required_days:
            # Transition allowed
            logger.info(
                "Regime transition approved after persistence requirement met",
                netuid=subnet.netuid,
                from_regime=current_regime.value,
                to_regime=candidate_regime.value,
                days_required=required_days,
                days_observed=new_candidate_days,
            )
            return candidate_regime, f"{candidate_reason} (persistence: {new_candidate_days}/{required_days} days)", True
        else:
            # Persistence not yet met - stay in current regime
            logger.debug(
                "Regime transition blocked by persistence requirement",
                netuid=subnet.netuid,
                current=current_regime.value,
                candidate=candidate_regime.value,
                days_required=required_days,
                days_observed=new_candidate_days,
            )
            # Update candidate tracking on the subnet
            subnet.regime_candidate = candidate_regime.value
            subnet.regime_candidate_days = new_candidate_days

            return current_regime, f"Holding {current_regime.value} (candidate: {candidate_regime.value} for {new_candidate_days}/{required_days} days)", False

    async def get_emission_history(
        self,
        db,
        netuid: int,
        lookback_days: Optional[int] = None,
    ) -> List[Tuple[datetime, Decimal]]:
        """Get historical emission_share values from SubnetSnapshot.

        Args:
            db: Database session
            netuid: Subnet network ID
            lookback_days: Days to look back (default: emissions_lookback_days config)

        Returns:
            List of (timestamp, emission_share) tuples, most recent first
        """
        days = lookback_days or self.emissions_lookback_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(SubnetSnapshot.timestamp, SubnetSnapshot.emission_share)
            .where(
                SubnetSnapshot.netuid == netuid,
                SubnetSnapshot.timestamp >= cutoff,
            )
            .order_by(SubnetSnapshot.timestamp.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        return [(row.timestamp, row.emission_share) for row in rows]

    async def check_emissions_collapse(
        self,
        db,
        subnet: Subnet,
    ) -> EmissionsCollapseResult:
        """Check if a subnet has experienced emissions collapse.

        Compares current emission_share to 7d baseline from SubnetSnapshot.
        Thresholds:
        - 30% drop: warning -> suggest Risk-Off
        - 50% drop: severe -> suggest Quarantine
        - Near-zero (<0.01%): critical -> suggest Dead

        Args:
            db: Database session
            subnet: Subnet to check

        Returns:
            EmissionsCollapseResult with collapse status and suggested regime
        """
        current_emission = subnet.emission_share or Decimal("0")

        # Check for near-zero emissions first (most severe)
        if current_emission < self.emissions_near_zero_threshold:
            return EmissionsCollapseResult(
                netuid=subnet.netuid,
                has_collapse=True,
                severity="critical",
                suggested_regime=FlowRegime.DEAD,
                current_emission_share=current_emission,
                baseline_emission_share=None,
                delta_pct=Decimal("-100") if current_emission == 0 else None,
                reason=f"Near-zero emissions: {float(current_emission):.4%} < {float(self.emissions_near_zero_threshold):.4%} threshold",
            )

        # Get historical emissions to compute delta
        history = await self.get_emission_history(db, subnet.netuid)

        if not history:
            # No history - cannot compute delta
            return EmissionsCollapseResult(
                netuid=subnet.netuid,
                has_collapse=False,
                severity=None,
                suggested_regime=None,
                current_emission_share=current_emission,
                baseline_emission_share=None,
                delta_pct=None,
                reason="No emission history available for delta calculation",
            )

        # Get baseline (oldest value in lookback window)
        # History is sorted most recent first, so take last item
        _, baseline_emission = history[-1]

        if baseline_emission <= 0:
            # Baseline was zero - cannot compute meaningful delta
            return EmissionsCollapseResult(
                netuid=subnet.netuid,
                has_collapse=False,
                severity=None,
                suggested_regime=None,
                current_emission_share=current_emission,
                baseline_emission_share=baseline_emission,
                delta_pct=None,
                reason="Baseline emission was zero, cannot compute delta",
            )

        # Compute percentage change
        delta_pct = (current_emission - baseline_emission) / baseline_emission

        # Check severity thresholds (negative delta = drop)
        if delta_pct <= -self.emissions_severe_threshold:
            # 50%+ drop -> Quarantine
            return EmissionsCollapseResult(
                netuid=subnet.netuid,
                has_collapse=True,
                severity="severe",
                suggested_regime=FlowRegime.QUARANTINE,
                current_emission_share=current_emission,
                baseline_emission_share=baseline_emission,
                delta_pct=delta_pct,
                reason=f"Severe emissions collapse: {float(delta_pct):.1%} over {self.emissions_lookback_days}d (threshold: -{float(self.emissions_severe_threshold):.0%})",
            )
        elif delta_pct <= -self.emissions_warning_threshold:
            # 30%+ drop -> Risk-Off
            return EmissionsCollapseResult(
                netuid=subnet.netuid,
                has_collapse=True,
                severity="warning",
                suggested_regime=FlowRegime.RISK_OFF,
                current_emission_share=current_emission,
                baseline_emission_share=baseline_emission,
                delta_pct=delta_pct,
                reason=f"Emissions drop: {float(delta_pct):.1%} over {self.emissions_lookback_days}d (threshold: -{float(self.emissions_warning_threshold):.0%})",
            )

        # No collapse detected
        return EmissionsCollapseResult(
            netuid=subnet.netuid,
            has_collapse=False,
            severity=None,
            suggested_regime=None,
            current_emission_share=current_emission,
            baseline_emission_share=baseline_emission,
            delta_pct=delta_pct,
            reason=f"Emissions stable: {float(delta_pct):.1%} over {self.emissions_lookback_days}d",
        )

    def apply_emissions_override(
        self,
        flow_regime: FlowRegime,
        flow_reason: str,
        emissions_result: EmissionsCollapseResult,
    ) -> Tuple[FlowRegime, str, bool]:
        """Apply emissions collapse override to flow-based regime.

        Emissions collapse can only make regime MORE restrictive, never less.
        Severity hierarchy: DEAD > QUARANTINE > RISK_OFF > NEUTRAL > RISK_ON

        Args:
            flow_regime: Regime computed from flow signals
            flow_reason: Reason for flow regime
            emissions_result: Result from check_emissions_collapse

        Returns:
            Tuple of (final_regime, final_reason, was_overridden)
        """
        if not emissions_result.has_collapse:
            return flow_regime, flow_reason, False

        suggested = emissions_result.suggested_regime
        if suggested is None:
            return flow_regime, flow_reason, False

        # Severity ranking (higher = more restrictive)
        severity_rank = {
            FlowRegime.RISK_ON: 1,
            FlowRegime.NEUTRAL: 2,
            FlowRegime.RISK_OFF: 3,
            FlowRegime.QUARANTINE: 4,
            FlowRegime.DEAD: 5,
        }

        flow_severity = severity_rank.get(flow_regime, 2)
        emissions_severity = severity_rank.get(suggested, 2)

        # Only override if emissions suggests MORE restrictive regime
        if emissions_severity > flow_severity:
            combined_reason = f"{flow_reason}; EMISSIONS OVERRIDE: {emissions_result.reason}"
            logger.warning(
                "Emissions collapse overriding flow regime",
                netuid=emissions_result.netuid,
                flow_regime=flow_regime.value,
                emissions_regime=suggested.value,
                emissions_delta=float(emissions_result.delta_pct) if emissions_result.delta_pct else None,
            )
            return suggested, combined_reason, True

        return flow_regime, flow_reason, False

    async def compute_portfolio_regime(self) -> Tuple[FlowRegime, str, Dict[str, int]]:
        """Compute overall portfolio regime based on position-weighted flows.

        Returns:
            Tuple of (regime, reason, regime_counts)
        """
        async with get_db_context() as db:
            # Get all subnets with positions
            from app.models.position import Position

            stmt = select(Position).where(
                Position.wallet_address == self._wallet_address,
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

        When enable_regime_persistence is True, transitions require
        N consecutive days of the candidate regime before being applied.

        When enable_emissions_collapse_detection is True, emissions collapse
        can override flow-based regime to a more restrictive state.

        Returns:
            Summary of regime updates
        """
        logger.info("Updating flow regimes for all subnets",
                   persistence_enabled=self.enable_persistence,
                   emissions_collapse_enabled=self.enable_emissions_collapse)

        results = {
            "subnets_updated": 0,
            "regime_changes": [],
            "regime_counts": {r.value: 0 for r in FlowRegime},
            "persistence_enabled": self.enable_persistence,
            "blocked_transitions": 0,  # Transitions blocked by persistence
            "emissions_collapse_enabled": self.enable_emissions_collapse,
            "emissions_overrides": 0,  # Regimes overridden by emissions collapse
            "emissions_collapses": [],  # Details of detected emissions collapses
        }

        async with get_db_context() as db:
            # Get all subnets with pool liquidity
            stmt = select(Subnet).where(Subnet.pool_tao_reserve > 0)
            result = await db.execute(stmt)
            subnets = list(result.scalars().all())

            now = datetime.now(timezone.utc)

            for subnet in subnets:
                old_regime = subnet.flow_regime

                # Step 1: Compute flow-based regime
                candidate_regime, candidate_reason = await self.compute_subnet_regime(subnet)

                # Step 2: Apply persistence requirement if enabled
                flow_regime, flow_reason, did_transition = self.apply_persistence(
                    subnet, candidate_regime, candidate_reason
                )

                # Step 3: Check for emissions collapse if enabled
                emissions_override_applied = False
                if self.enable_emissions_collapse:
                    emissions_result = await self.check_emissions_collapse(db, subnet)

                    if emissions_result.has_collapse:
                        results["emissions_collapses"].append({
                            "netuid": subnet.netuid,
                            "name": subnet.name,
                            "severity": emissions_result.severity,
                            "suggested_regime": emissions_result.suggested_regime.value if emissions_result.suggested_regime else None,
                            "current_emission": float(emissions_result.current_emission_share),
                            "baseline_emission": float(emissions_result.baseline_emission_share) if emissions_result.baseline_emission_share else None,
                            "delta_pct": float(emissions_result.delta_pct) if emissions_result.delta_pct else None,
                            "reason": emissions_result.reason,
                        })

                    # Apply emissions override (can only make regime MORE restrictive)
                    final_regime, final_reason, emissions_override_applied = self.apply_emissions_override(
                        flow_regime, flow_reason, emissions_result
                    )

                    if emissions_override_applied:
                        results["emissions_overrides"] += 1
                        did_transition = True  # Emissions override counts as a transition
                else:
                    final_regime = flow_regime
                    final_reason = flow_reason

                # Update subnet with final regime
                subnet.flow_regime = final_regime.value

                # Track regime duration and changes
                if old_regime != final_regime.value:
                    subnet.flow_regime_since = now
                    subnet.flow_regime_days = 0
                    # Clear candidate tracking after successful transition
                    subnet.regime_candidate = None
                    subnet.regime_candidate_days = 0
                    results["regime_changes"].append({
                        "netuid": subnet.netuid,
                        "name": subnet.name,
                        "old": old_regime,
                        "new": final_regime.value,
                        "reason": final_reason,
                        "persistence_applied": self.enable_persistence,
                        "emissions_override": emissions_override_applied,
                    })
                else:
                    if subnet.flow_regime_since:
                        subnet.flow_regime_days = (now - subnet.flow_regime_since).days

                # Track if transition was blocked by persistence
                if self.enable_persistence and candidate_regime.value != old_regime and not did_transition:
                    results["blocked_transitions"] += 1

                results["regime_counts"][final_regime.value] += 1
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


# Lazy singleton instance
_regime_calculator: Optional[RegimeCalculator] = None


def get_regime_calculator() -> RegimeCalculator:
    """Get or create the RegimeCalculator singleton."""
    global _regime_calculator
    if _regime_calculator is None:
        _regime_calculator = RegimeCalculator()
    return _regime_calculator


class _LazyRegimeCalculator:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_regime_calculator(), name)


regime_calculator = _LazyRegimeCalculator()
