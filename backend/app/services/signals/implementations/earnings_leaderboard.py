"""Earnings Leaderboard Signal implementation.

Uses the earnings identity (earnings = end_value - start_value - net_flows)
to rank subnets by performance over 7d and 30d windows.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List

import structlog

from app.core.config import get_settings
from app.services.analysis.earnings import get_earnings_service
from app.services.signals.base import (
    BaseSignal,
    SignalConfidence,
    SignalDefinition,
    SignalOutput,
    SignalStatus,
)
from app.services.signals.guardrails import GuardrailChecker

logger = structlog.get_logger()


class EarningsLeaderboardSignal(BaseSignal):
    """Earnings Attribution Leaderboard Signal.

    Computes 7d and 30d earnings per netuid and produces:
    - Top performers (highest earnings)
    - Under performers (lowest/negative earnings)
    - Recommendation for portfolio rebalancing
    """

    def get_definition(self) -> SignalDefinition:
        return SignalDefinition(
            id="earnings_leaderboard",
            name="Earnings Leaderboard",
            description=(
                "Ranks subnets by actual earnings attribution over 7d and 30d windows. "
                "Uses the core identity: earnings = end_value - start_value - net_flows. "
                "Identifies top performers and underperformers for potential rebalancing."
            ),
            actionability=(
                "Review top/under performers for rebalancing decisions. "
                "Consider reducing allocation to consistent underperformers. "
                "Consider increasing allocation to consistent top performers."
            ),
            actionability_score=7,
            edge_hypothesis=(
                "Past earnings performance provides signal for future performance. "
                "Consistent underperformers may indicate fundamental issues. "
                "Concentration in top performers improves risk-adjusted returns."
            ),
            correctness_risks=[
                "Short-term noise: 7d performance may not predict long-term",
                "Mean reversion: top performers may regress",
                "Survivorship bias: only tracks positions we hold",
                "Price movements vs actual yield conflation",
            ],
            required_datasets=["position_snapshots", "delegation_events"],
            ongoing_cost="Medium - requires snapshot history queries",
            latency_sensitivity="Low - can be computed async",
            failure_behavior="If insufficient data, output with LOW confidence and explain data gaps",
        )

    async def run(self) -> SignalOutput:
        """Run the earnings leaderboard analysis."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        guardrails = []
        evidence: Dict[str, Any] = {}

        # Check guardrails
        guardrail_checker = GuardrailChecker()

        # Check data freshness first
        staleness_check = await guardrail_checker.check_data_staleness()
        if staleness_check.triggered:
            guardrails.append(staleness_check.guardrail_id)
            evidence["staleness_check"] = staleness_check.details

        # Get earnings service
        earnings_service = get_earnings_service()

        # Compute 7-day earnings
        try:
            end_7d = now
            start_7d = now - timedelta(days=7)
            earnings_7d = await earnings_service.get_earnings_summary(
                start=start_7d,
                end=end_7d,
            )
            evidence["earnings_7d"] = earnings_7d
        except Exception as e:
            logger.error("Failed to compute 7d earnings", error=str(e))
            evidence["earnings_7d"] = {"error": str(e)}
            guardrails.append("earnings_7d_failed")

        # Compute 30-day earnings
        try:
            end_30d = now
            start_30d = now - timedelta(days=30)
            earnings_30d = await earnings_service.get_earnings_summary(
                start=start_30d,
                end=end_30d,
            )
            evidence["earnings_30d"] = earnings_30d
        except Exception as e:
            logger.error("Failed to compute 30d earnings", error=str(e))
            evidence["earnings_30d"] = {"error": str(e)}
            guardrails.append("earnings_30d_failed")

        # Check sample size
        by_netuid_7d = evidence.get("earnings_7d", {}).get("by_netuid", [])
        by_netuid_30d = evidence.get("earnings_30d", {}).get("by_netuid", [])

        sample_check = guardrail_checker.check_sample_size(
            sample_size=len(by_netuid_7d),
            min_required=1,
            dataset_name="7d_positions",
        )
        if sample_check.triggered:
            guardrails.append(sample_check.guardrail_id)

        # If no data, return degraded
        if not by_netuid_7d and not by_netuid_30d:
            return SignalOutput(
                status=SignalStatus.DEGRADED,
                summary="Insufficient position data for earnings analysis",
                recommended_action="Ensure positions exist and data sync has run",
                evidence=evidence,
                guardrails_triggered=guardrails,
                confidence=SignalConfidence.LOW,
                confidence_reason="No position data available for earnings calculation",
            )

        # Sort by earnings to find top and under performers
        leaderboard_7d = self._build_leaderboard(by_netuid_7d)
        leaderboard_30d = self._build_leaderboard(by_netuid_30d)

        evidence["leaderboard_7d"] = leaderboard_7d
        evidence["leaderboard_30d"] = leaderboard_30d

        # Build summary and recommendations
        summary_parts = []
        recommendations = []

        # 7-day analysis
        top_7d = leaderboard_7d.get("top_performers", [])
        under_7d = leaderboard_7d.get("under_performers", [])

        if top_7d:
            top_names = [f"netuid {p['netuid']}" for p in top_7d[:3]]
            summary_parts.append(f"7d top: {', '.join(top_names)}")

        if under_7d:
            under_names = [f"netuid {p['netuid']}" for p in under_7d[:3]]
            summary_parts.append(f"7d under: {', '.join(under_names)}")
            if any(Decimal(str(p.get("earnings_tao", 0))) < 0 for p in under_7d):
                recommendations.append("Review underperforming positions for potential rebalancing")
                guardrails.append("negative_earnings_detected")

        # 30-day analysis
        top_30d = leaderboard_30d.get("top_performers", [])
        under_30d = leaderboard_30d.get("under_performers", [])

        if top_30d:
            total_30d_earnings = sum(
                Decimal(str(p.get("earnings_tao", 0)))
                for p in by_netuid_30d
            )
            evidence["total_30d_earnings_tao"] = str(total_30d_earnings)
            if total_30d_earnings > 0:
                recommendations.append(f"Total 30d earnings: {total_30d_earnings:.4f} TAO")

        # Check for consistent underperformers (in both windows)
        under_7d_netuids = {p["netuid"] for p in under_7d}
        under_30d_netuids = {p["netuid"] for p in under_30d}
        consistent_under = under_7d_netuids & under_30d_netuids

        if consistent_under:
            recommendations.append(
                f"Consistent underperformers (7d+30d): netuids {sorted(consistent_under)}"
            )
            guardrails.append("consistent_underperformers")

        # Determine status and confidence
        if guardrails and "data_staleness" in guardrails:
            status = SignalStatus.DEGRADED
            confidence = SignalConfidence.LOW
            confidence_reason = "Data staleness affects earnings accuracy"
        elif "earnings_7d_failed" in guardrails or "earnings_30d_failed" in guardrails:
            status = SignalStatus.DEGRADED
            confidence = SignalConfidence.LOW
            confidence_reason = "Earnings calculation partially failed"
        elif len(by_netuid_7d) < 3:
            status = SignalStatus.OK
            confidence = SignalConfidence.MEDIUM
            confidence_reason = "Limited sample size for reliable ranking"
        else:
            status = SignalStatus.OK
            confidence = SignalConfidence.HIGH
            confidence_reason = "Sufficient data for earnings analysis"

        summary = "; ".join(summary_parts) if summary_parts else "No significant earnings patterns detected"
        action = ". ".join(recommendations) if recommendations else "No action recommended at this time"

        return SignalOutput(
            status=status,
            summary=summary,
            recommended_action=action,
            evidence=evidence,
            guardrails_triggered=guardrails,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )

    def _build_leaderboard(self, by_netuid: List[Dict]) -> Dict[str, Any]:
        """Build leaderboard from netuid earnings data."""
        if not by_netuid:
            return {
                "top_performers": [],
                "under_performers": [],
                "neutral": [],
            }

        # Sort by earnings (descending)
        sorted_by_earnings = sorted(
            by_netuid,
            key=lambda x: Decimal(str(x.get("earnings_tao", 0))),
            reverse=True,
        )

        # Top performers (positive earnings, top 3)
        top_performers = [
            n for n in sorted_by_earnings
            if Decimal(str(n.get("earnings_tao", 0))) > 0
        ][:3]

        # Under performers (lowest earnings, including negative, bottom 3)
        under_performers = [
            n for n in sorted_by_earnings
            if Decimal(str(n.get("earnings_tao", 0))) < 0
        ][-3:][::-1]  # Reverse to show worst first

        # If no negative, take lowest positive
        if not under_performers and len(sorted_by_earnings) > len(top_performers):
            under_performers = sorted_by_earnings[-3:][::-1]

        # Neutral (everyone else)
        top_netuids = {p["netuid"] for p in top_performers}
        under_netuids = {p["netuid"] for p in under_performers}
        neutral = [
            n for n in sorted_by_earnings
            if n["netuid"] not in top_netuids and n["netuid"] not in under_netuids
        ]

        return {
            "top_performers": top_performers,
            "under_performers": under_performers,
            "neutral": neutral,
        }
