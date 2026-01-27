"""Slippage Capacity Signal implementation.

Computes max safe add size per netuid given a slippage threshold.
Helps prevent large trades that would incur excessive slippage.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.models.slippage import SlippageSurface
from app.models.subnet import Subnet
from app.services.signals.base import (
    BaseSignal,
    SignalConfidence,
    SignalDefinition,
    SignalOutput,
    SignalStatus,
)
from app.services.signals.guardrails import GuardrailChecker

logger = structlog.get_logger()

# Standard sizes for analysis
ANALYSIS_SIZES = [Decimal("2"), Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")]


class SlippageCapacitySignal(BaseSignal):
    """Capacity and Slippage Safety Signal.

    Computes max safe add size per netuid given slippage threshold.
    Warns about positions that would incur high slippage for common trade sizes.
    """

    def get_definition(self) -> SignalDefinition:
        return SignalDefinition(
            id="slippage_capacity",
            name="Capacity and Slippage Safety",
            description=(
                "Analyzes slippage capacity for each subnet. "
                "Computes maximum safe trade size before exceeding slippage threshold. "
                "Identifies low-liquidity subnets where trades would be expensive."
            ),
            actionability=(
                "Use capacity limits when planning position changes. "
                "Avoid large trades in low-capacity subnets. "
                "Consider splitting large trades across time."
            ),
            actionability_score=8,
            edge_hypothesis=(
                "Avoiding high-slippage trades preserves capital. "
                "Small positions in illiquid subnets may be hard to exit. "
                "Capacity awareness prevents execution regret."
            ),
            correctness_risks=[
                "Slippage surfaces may be stale (short TTL)",
                "Pool composition can change rapidly",
                "Large external trades can drain liquidity",
                "Interpolation between cached sizes is approximate",
            ],
            required_datasets=["slippage_surfaces", "positions", "pools"],
            ongoing_cost="Medium - requires slippage surface queries",
            latency_sensitivity="Medium - slippage can change quickly",
            failure_behavior="If slippage data stale/missing, output DEGRADED with warning",
        )

    async def run(self) -> SignalOutput:
        """Run the slippage capacity analysis."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        guardrails = []
        evidence: Dict[str, Any] = {}

        # Get slippage threshold from settings (default 1%)
        slippage_threshold = getattr(settings, "slippage_threshold_pct", Decimal("1.0"))

        # Check guardrails
        guardrail_checker = GuardrailChecker()

        # Check data freshness
        staleness_check = await guardrail_checker.check_data_staleness()
        if staleness_check.triggered:
            guardrails.append(staleness_check.guardrail_id)

        async with get_db_context() as db:
            # Get all positions
            pos_stmt = select(Position).where(
                Position.wallet_address == settings.wallet_address,
                Position.alpha_balance > 0,
            )
            pos_result = await db.execute(pos_stmt)
            positions = list(pos_result.scalars().all())

            if not positions:
                return SignalOutput(
                    status=SignalStatus.OK,
                    summary="No active positions to analyze for slippage",
                    recommended_action="No action required - no positions held",
                    evidence={"positions": []},
                    guardrails_triggered=guardrails,
                    confidence=SignalConfidence.HIGH,
                    confidence_reason="No positions means no slippage concern",
                )

            # Analyze each position
            capacity_analysis = []
            low_capacity_netuids = []
            high_slippage_netuids = []
            stale_data_netuids = []

            for position in positions:
                netuid = position.netuid
                analysis = await self._analyze_position_capacity(
                    db, netuid, slippage_threshold
                )
                analysis["netuid"] = netuid
                analysis["current_tao_value"] = str(position.tao_value_mid)
                capacity_analysis.append(analysis)

                # Check for issues
                if analysis.get("data_stale"):
                    stale_data_netuids.append(netuid)

                max_safe = Decimal(str(analysis.get("max_safe_stake_tao", 0)))
                if max_safe < Decimal("5"):
                    low_capacity_netuids.append(netuid)

                current_slippage = Decimal(str(analysis.get("current_position_exit_slippage_pct", 0)))
                if current_slippage > slippage_threshold:
                    high_slippage_netuids.append(netuid)

            evidence["capacity_analysis"] = capacity_analysis
            evidence["slippage_threshold_pct"] = str(slippage_threshold)
            evidence["low_capacity_netuids"] = low_capacity_netuids
            evidence["high_slippage_netuids"] = high_slippage_netuids

        # Build summary and recommendations
        summary_parts = []
        recommendations = []

        if stale_data_netuids:
            summary_parts.append(f"Stale slippage data for netuids: {stale_data_netuids}")
            guardrails.append("slippage_data_stale")

        if low_capacity_netuids:
            summary_parts.append(f"Low capacity (<5 TAO safe): netuids {low_capacity_netuids}")
            recommendations.append(
                f"Exercise caution trading in low-capacity subnets: {low_capacity_netuids}"
            )
            guardrails.append("low_capacity_detected")

        if high_slippage_netuids:
            summary_parts.append(f"High exit slippage (>{slippage_threshold}%): netuids {high_slippage_netuids}")
            recommendations.append(
                f"Current positions in {high_slippage_netuids} would incur high slippage to exit"
            )
            guardrails.append("high_exit_slippage")

        # Determine status and confidence
        if stale_data_netuids and len(stale_data_netuids) == len(positions):
            status = SignalStatus.DEGRADED
            confidence = SignalConfidence.LOW
            confidence_reason = "All slippage data is stale"
        elif stale_data_netuids:
            status = SignalStatus.DEGRADED
            confidence = SignalConfidence.MEDIUM
            confidence_reason = f"Slippage data stale for {len(stale_data_netuids)}/{len(positions)} positions"
        elif high_slippage_netuids:
            status = SignalStatus.OK
            confidence = SignalConfidence.HIGH
            confidence_reason = "Slippage data is fresh; high slippage positions identified"
        else:
            status = SignalStatus.OK
            confidence = SignalConfidence.HIGH
            confidence_reason = "All positions have acceptable slippage capacity"

        if not summary_parts:
            summary_parts.append("All positions have acceptable slippage capacity")

        if not recommendations:
            recommendations.append("No slippage concerns at current position sizes")

        return SignalOutput(
            status=status,
            summary="; ".join(summary_parts),
            recommended_action=". ".join(recommendations),
            evidence=evidence,
            guardrails_triggered=guardrails,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )

    async def _analyze_position_capacity(
        self,
        db,
        netuid: int,
        threshold_pct: Decimal,
    ) -> Dict[str, Any]:
        """Analyze slippage capacity for a single position."""
        now = datetime.now(timezone.utc)

        # Get all slippage surfaces for this netuid
        stake_stmt = (
            select(SlippageSurface)
            .where(
                SlippageSurface.netuid == netuid,
                SlippageSurface.action == "stake",
            )
            .order_by(SlippageSurface.size_tao)
        )
        stake_result = await db.execute(stake_stmt)
        stake_surfaces = list(stake_result.scalars().all())

        unstake_stmt = (
            select(SlippageSurface)
            .where(
                SlippageSurface.netuid == netuid,
                SlippageSurface.action == "unstake",
            )
            .order_by(SlippageSurface.size_tao)
        )
        unstake_result = await db.execute(unstake_stmt)
        unstake_surfaces = list(unstake_result.scalars().all())

        # Get subnet info
        subnet_stmt = select(Subnet).where(Subnet.netuid == netuid)
        subnet_result = await db.execute(subnet_stmt)
        subnet = subnet_result.scalar_one_or_none()

        # Check for stale data
        is_stale = False
        if stake_surfaces:
            latest_compute = max(s.computed_at for s in stake_surfaces if s.computed_at)
            stale_threshold = getattr(
                get_settings(), "slippage_stale_minutes", 10
            )
            is_stale = (now - latest_compute).total_seconds() > stale_threshold * 60

        # Compute max safe stake size
        max_safe_stake = Decimal("0")
        stake_slippage_curve = []
        for surface in stake_surfaces:
            slippage_curve_point = {
                "size_tao": str(surface.size_tao),
                "slippage_pct": str(surface.slippage_pct),
            }
            stake_slippage_curve.append(slippage_curve_point)
            if surface.slippage_pct <= threshold_pct:
                max_safe_stake = surface.size_tao

        # Compute max safe unstake size
        max_safe_unstake = Decimal("0")
        unstake_slippage_curve = []
        for surface in unstake_surfaces:
            slippage_curve_point = {
                "size_tao": str(surface.size_tao),
                "slippage_pct": str(surface.slippage_pct),
            }
            unstake_slippage_curve.append(slippage_curve_point)
            if surface.slippage_pct <= threshold_pct:
                max_safe_unstake = surface.size_tao

        # Get position to estimate exit slippage
        pos_stmt = select(Position).where(
            Position.wallet_address == get_settings().wallet_address,
            Position.netuid == netuid,
        )
        pos_result = await db.execute(pos_stmt)
        position = pos_result.scalar_one_or_none()

        current_exit_slippage = Decimal("0")
        if position and unstake_surfaces:
            # Estimate slippage for exiting current position
            pos_value = position.tao_value_mid
            # Find surface at or above position size
            for surface in unstake_surfaces:
                if surface.size_tao >= pos_value:
                    current_exit_slippage = surface.slippage_pct
                    break
            if current_exit_slippage == 0 and unstake_surfaces:
                # Position larger than any cached size - use highest
                current_exit_slippage = unstake_surfaces[-1].slippage_pct

        return {
            "max_safe_stake_tao": str(max_safe_stake),
            "max_safe_unstake_tao": str(max_safe_unstake),
            "current_position_exit_slippage_pct": str(current_exit_slippage),
            "stake_slippage_curve": stake_slippage_curve,
            "unstake_slippage_curve": unstake_slippage_curve,
            "pool_tao_reserve": str(subnet.pool_tao_reserve) if subnet else "0",
            "pool_alpha_reserve": str(subnet.pool_alpha_reserve) if subnet else "0",
            "data_stale": is_stale,
            "surfaces_available": len(stake_surfaces) + len(unstake_surfaces),
        }
