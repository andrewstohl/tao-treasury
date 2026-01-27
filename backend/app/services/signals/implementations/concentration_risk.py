"""Concentration and Churn Risk Signal implementation.

Detects portfolio concentration exceeding thresholds and
analyzes position stability metrics.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List

import structlog
from sqlalchemy import select, func

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position, PositionSnapshot
from app.models.subnet import Subnet
from app.services.analysis.risk_monitor import get_risk_monitor
from app.services.signals.base import (
    BaseSignal,
    SignalConfidence,
    SignalDefinition,
    SignalOutput,
    SignalStatus,
)
from app.services.signals.guardrails import GuardrailChecker

logger = structlog.get_logger()

# Concentration thresholds
MAX_SINGLE_POSITION_PCT = Decimal("25.0")  # No single position > 25%
WARN_SINGLE_POSITION_PCT = Decimal("20.0")  # Warn at 20%
MAX_TOP3_CONCENTRATION_PCT = Decimal("60.0")  # Top 3 positions < 60%

# HHI thresholds (Herfindahl-Hirschman Index)
HIGH_HHI_THRESHOLD = 2500  # High concentration
MODERATE_HHI_THRESHOLD = 1500  # Moderate concentration


class ConcentrationRiskSignal(BaseSignal):
    """Concentration and Churn Risk Signal.

    Detects portfolio concentration exceeding thresholds.
    Analyzes position stability and churn metrics.
    """

    def get_definition(self) -> SignalDefinition:
        return SignalDefinition(
            id="concentration_risk",
            name="Concentration and Churn Risk",
            description=(
                "Analyzes portfolio concentration and position stability. "
                "Detects single-position concentration exceeding thresholds. "
                "Monitors position churn and stability metrics."
            ),
            actionability=(
                "If concentration too high: Consider rebalancing to reduce risk. "
                "If high churn detected: Review trading frequency and strategy. "
                "Use diversification recommendations to reduce concentration."
            ),
            actionability_score=8,
            edge_hypothesis=(
                "Concentrated portfolios have higher idiosyncratic risk. "
                "Over-diversification dilutes alpha. "
                "Position churn may indicate strategy drift or costs."
            ),
            correctness_risks=[
                "Concentration may be intentional (high-conviction plays)",
                "HHI doesn't account for correlation between positions",
                "Churn metrics may miss legitimate rebalancing",
                "Market cap / liquidity differences not fully captured",
            ],
            required_datasets=["positions", "position_snapshots"],
            ongoing_cost="Low - uses current position data",
            latency_sensitivity="Low - concentration changes slowly",
            failure_behavior="If no positions, output OK with note",
        )

    async def run(self) -> SignalOutput:
        """Run the concentration risk analysis."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        guardrails = []
        evidence: Dict[str, Any] = {}

        # Check guardrails
        guardrail_checker = GuardrailChecker()

        staleness_check = await guardrail_checker.check_data_staleness()
        if staleness_check.triggered:
            guardrails.append(staleness_check.guardrail_id)

        # Get risk monitor for concentration analysis
        risk_monitor = get_risk_monitor()

        try:
            concentration = await risk_monitor.compute_concentration_risk()
            evidence["concentration"] = self._serialize_concentration(concentration)
        except Exception as e:
            logger.error("Failed to compute concentration", error=str(e))
            return SignalOutput(
                status=SignalStatus.DEGRADED,
                summary=f"Concentration analysis failed: {str(e)}",
                recommended_action="Check position data and retry",
                evidence={"error": str(e)},
                guardrails_triggered=["concentration_check_failed"],
                confidence=SignalConfidence.LOW,
                confidence_reason="Analysis failed",
            )

        # Compute churn metrics
        try:
            churn = await self._compute_churn_metrics(settings.wallet_address)
            evidence["churn"] = churn
        except Exception as e:
            logger.warning("Failed to compute churn metrics", error=str(e))
            evidence["churn"] = {"error": str(e)}

        # Analyze results
        position_count = concentration.get("position_count", 0)
        if position_count == 0:
            return SignalOutput(
                status=SignalStatus.OK,
                summary="No active positions to analyze for concentration",
                recommended_action="No action required - no positions held",
                evidence=evidence,
                guardrails_triggered=guardrails,
                confidence=SignalConfidence.HIGH,
                confidence_reason="No positions means no concentration concern",
            )

        # Check concentration thresholds
        summary_parts = []
        recommendations = []

        largest_pct = Decimal(str(concentration.get("largest_position_pct", 0)))
        hhi = float(concentration.get("hhi", 0))

        # Single position concentration
        if largest_pct >= MAX_SINGLE_POSITION_PCT:
            summary_parts.append(f"CRITICAL: Largest position at {largest_pct:.1f}% exceeds {MAX_SINGLE_POSITION_PCT}% limit")
            recommendations.append("Reduce largest position to below 25% of portfolio")
            guardrails.append("concentration_critical")
        elif largest_pct >= WARN_SINGLE_POSITION_PCT:
            summary_parts.append(f"WARNING: Largest position at {largest_pct:.1f}% approaching limit")
            recommendations.append("Consider reducing concentration in largest position")
            guardrails.append("concentration_warning")

        # Top 3 concentration
        position_weights = concentration.get("position_weights", [])
        if len(position_weights) >= 3:
            top3_pct = sum(Decimal(str(p.get("weight_pct", 0))) for p in position_weights[:3])
            evidence["top3_concentration_pct"] = str(top3_pct)
            if top3_pct >= MAX_TOP3_CONCENTRATION_PCT:
                summary_parts.append(f"Top 3 positions at {top3_pct:.1f}% (target <{MAX_TOP3_CONCENTRATION_PCT}%)")
                guardrails.append("top3_concentration_high")

        # HHI analysis
        if hhi >= HIGH_HHI_THRESHOLD:
            summary_parts.append(f"High concentration (HHI={hhi:.0f})")
            recommendations.append("Portfolio is highly concentrated - consider adding positions")
            guardrails.append("hhi_high")
        elif hhi >= MODERATE_HHI_THRESHOLD:
            summary_parts.append(f"Moderate concentration (HHI={hhi:.0f})")
            guardrails.append("hhi_moderate")
        else:
            summary_parts.append(f"Well diversified (HHI={hhi:.0f})")

        evidence["hhi_threshold_high"] = HIGH_HHI_THRESHOLD
        evidence["hhi_threshold_moderate"] = MODERATE_HHI_THRESHOLD

        # Churn analysis
        churn_data = evidence.get("churn", {})
        if churn_data and not churn_data.get("error"):
            turnover_7d = churn_data.get("turnover_7d_pct", 0)
            if turnover_7d > 50:
                summary_parts.append(f"High 7d turnover ({turnover_7d:.1f}%)")
                recommendations.append("Review trading frequency - high churn may indicate strategy issues")
                guardrails.append("high_churn")

        # Determine status and confidence
        if "concentration_critical" in guardrails:
            status = SignalStatus.BLOCKED
            confidence = SignalConfidence.HIGH
            confidence_reason = "Concentration exceeds hard limit"
        elif "concentration_warning" in guardrails or "hhi_high" in guardrails:
            status = SignalStatus.DEGRADED
            confidence = SignalConfidence.HIGH
            confidence_reason = "Concentration approaching limits"
        else:
            status = SignalStatus.OK
            confidence = SignalConfidence.HIGH
            confidence_reason = "Portfolio concentration within acceptable limits"

        if not summary_parts:
            summary_parts.append("Portfolio concentration within acceptable limits")

        if not recommendations:
            recommendations.append("No concentration concerns at this time")

        return SignalOutput(
            status=status,
            summary="; ".join(summary_parts),
            recommended_action=". ".join(recommendations),
            evidence=evidence,
            guardrails_triggered=guardrails,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )

    def _serialize_concentration(self, concentration: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Decimal values to strings for JSON serialization."""
        result = {}
        for key, value in concentration.items():
            if isinstance(value, Decimal):
                result[key] = str(value)
            elif isinstance(value, list):
                result[key] = [
                    {k: str(v) if isinstance(v, Decimal) else v for k, v in item.items()}
                    if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    async def _compute_churn_metrics(self, wallet_address: str) -> Dict[str, Any]:
        """Compute position churn and stability metrics."""
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        async with get_db_context() as db:
            # Get current positions
            pos_stmt = select(Position).where(
                Position.wallet_address == wallet_address,
                Position.alpha_balance > 0,
            )
            pos_result = await db.execute(pos_stmt)
            current_positions = {p.netuid: p for p in pos_result.scalars().all()}

            # Get snapshots from 7 days ago
            snap_7d_stmt = (
                select(PositionSnapshot)
                .where(
                    PositionSnapshot.wallet_address == wallet_address,
                    PositionSnapshot.timestamp >= seven_days_ago,
                    PositionSnapshot.timestamp < seven_days_ago + timedelta(hours=4),
                )
            )
            snap_7d_result = await db.execute(snap_7d_stmt)
            snapshots_7d = {s.netuid: s for s in snap_7d_result.scalars().all()}

            # Get snapshots from 30 days ago
            snap_30d_stmt = (
                select(PositionSnapshot)
                .where(
                    PositionSnapshot.wallet_address == wallet_address,
                    PositionSnapshot.timestamp >= thirty_days_ago,
                    PositionSnapshot.timestamp < thirty_days_ago + timedelta(hours=4),
                )
            )
            snap_30d_result = await db.execute(snap_30d_stmt)
            snapshots_30d = {s.netuid: s for s in snap_30d_result.scalars().all()}

            # Compute turnover (positions added + removed)
            current_netuids = set(current_positions.keys())
            netuids_7d = set(snapshots_7d.keys())
            netuids_30d = set(snapshots_30d.keys())

            added_7d = current_netuids - netuids_7d
            removed_7d = netuids_7d - current_netuids
            added_30d = current_netuids - netuids_30d
            removed_30d = netuids_30d - current_netuids

            # Compute value turnover
            current_value = sum(p.tao_value_mid or Decimal("0") for p in current_positions.values())
            value_7d = sum(s.tao_value_mid or Decimal("0") for s in snapshots_7d.values())
            value_30d = sum(s.tao_value_mid or Decimal("0") for s in snapshots_30d.values())

            # Turnover = (added + removed value) / average portfolio value
            # Simplified: count of changes / total positions
            if len(current_positions) > 0:
                churn_7d = len(added_7d) + len(removed_7d)
                churn_30d = len(added_30d) + len(removed_30d)
                turnover_7d_pct = (churn_7d / len(current_positions)) * 100
                turnover_30d_pct = (churn_30d / len(current_positions)) * 100
            else:
                turnover_7d_pct = 0
                turnover_30d_pct = 0

            return {
                "current_position_count": len(current_positions),
                "positions_7d_ago": len(snapshots_7d),
                "positions_30d_ago": len(snapshots_30d),
                "added_7d": list(added_7d),
                "removed_7d": list(removed_7d),
                "added_30d": list(added_30d),
                "removed_30d": list(removed_30d),
                "turnover_7d_pct": turnover_7d_pct,
                "turnover_30d_pct": turnover_30d_pct,
                "current_value_tao": str(current_value),
                "value_7d_ago_tao": str(value_7d),
                "value_30d_ago_tao": str(value_30d),
            }
