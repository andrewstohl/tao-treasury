"""Data Trust Gate Signal implementation.

This is the most critical signal - it gates all other signals.
If data is stale or has drift, it blocks high-confidence recommendations.
"""

from datetime import datetime, timezone
from typing import Any, Dict

import structlog

from app.core.config import get_settings
from app.services.data.data_sync import data_sync_service
from app.services.signals.base import (
    BaseSignal,
    SignalConfidence,
    SignalDefinition,
    SignalOutput,
    SignalStatus,
)

logger = structlog.get_logger()


class DataTrustGateSignal(BaseSignal):
    """Data Trust Gate Signal.

    Reads Trust Pack staleness and reconciliation drift.
    If degraded, blocks all other signals from high confidence.

    This is a forcing function. No exceptions.
    """

    def get_definition(self) -> SignalDefinition:
        return SignalDefinition(
            id="data_trust_gate",
            name="Data Trust Gate",
            description=(
                "Validates data freshness and reconciliation status. "
                "Gates all other signals from producing high-confidence "
                "recommendations if data is stale or has drift."
            ),
            actionability=(
                "If blocked: Stop making decisions until data issues resolved. "
                "If degraded: Proceed with extreme caution, verify manually. "
                "If OK: Data is trustworthy for decision-making."
            ),
            actionability_score=10,  # Highest - directly blocks other signals
            edge_hypothesis=(
                "Stale or drifted data leads to incorrect recommendations. "
                "By blocking high-confidence outputs when data quality is poor, "
                "we prevent bad decisions based on outdated information."
            ),
            correctness_risks=[
                "False positive: Good data flagged as stale (blocks valid recommendations)",
                "False negative: Bad data passes checks (allows incorrect recommendations)",
                "Clock drift between servers could cause spurious staleness alerts",
            ],
            required_datasets=["trust_pack", "reconciliation"],
            ongoing_cost="Low - reads cached metadata only",
            latency_sensitivity="High - should run first before all other signals",
            failure_behavior="If this signal fails to run, all other signals must output LOW confidence",
        )

    async def run(self) -> SignalOutput:
        """Run the data trust gate check."""
        settings = get_settings()
        issues = []
        guardrails = []
        evidence: Dict[str, Any] = {}

        # Check data staleness
        try:
            is_stale = data_sync_service.is_data_stale()
            last_sync = data_sync_service.last_sync

            evidence["data_staleness"] = {
                "is_stale": is_stale,
                "last_sync": last_sync.isoformat() if last_sync else None,
                "stale_threshold_minutes": settings.stale_data_threshold_minutes,
            }

            if is_stale:
                issues.append("Data is stale - last sync too old")
                guardrails.append("data_staleness")
                if last_sync is None:
                    issues.append("No sync has ever been completed")
                    guardrails.append("no_sync_ever")
        except Exception as e:
            logger.error("Failed to check data staleness", error=str(e))
            issues.append(f"Could not verify data freshness: {str(e)}")
            guardrails.append("staleness_check_failed")
            evidence["data_staleness"] = {"error": str(e)}

        # Check reconciliation drift
        try:
            from app.services.analysis.reconciliation import get_reconciliation_service

            if settings.enable_reconciliation:
                recon_service = get_reconciliation_service()
                recon_summary = await recon_service.get_trust_pack_summary()

                evidence["reconciliation"] = recon_summary

                has_drift = recon_summary.get("has_drift", False)
                last_run_passed = recon_summary.get("last_run_passed", True)
                failed_checks = recon_summary.get("failed_checks", 0)

                if has_drift:
                    issues.append(f"Reconciliation detected drift ({failed_checks} failed checks)")
                    guardrails.append("reconciliation_drift")

                if not last_run_passed and failed_checks > 0:
                    issues.append("Last reconciliation run failed")
                    guardrails.append("reconciliation_failed")
            else:
                evidence["reconciliation"] = {"enabled": False}
        except Exception as e:
            logger.error("Failed to check reconciliation", error=str(e))
            issues.append(f"Could not verify reconciliation status: {str(e)}")
            guardrails.append("reconciliation_check_failed")
            evidence["reconciliation"] = {"error": str(e)}

        # Check sync metrics if available
        try:
            if settings.enable_sync_metrics:
                from app.core.metrics import get_metrics
                metrics = get_metrics()
                sync_status = metrics.get_sync_status()

                evidence["sync_metrics"] = sync_status

                # Check for recent failures
                for dataset, status in sync_status.items():
                    if isinstance(status, dict):
                        if status.get("last_success") is None:
                            issues.append(f"Dataset '{dataset}' has never synced successfully")
                            guardrails.append(f"never_synced_{dataset}")
                        elif status.get("consecutive_failures", 0) > 3:
                            issues.append(f"Dataset '{dataset}' has {status['consecutive_failures']} consecutive failures")
                            guardrails.append(f"sync_failures_{dataset}")
        except Exception as e:
            # Sync metrics are optional
            evidence["sync_metrics"] = {"error": str(e)}

        # Determine output status
        if not issues:
            return SignalOutput(
                status=SignalStatus.OK,
                summary="All data trust checks passed",
                recommended_action="Proceed with normal confidence in data-driven decisions",
                evidence=evidence,
                guardrails_triggered=[],
                confidence=SignalConfidence.HIGH,
                confidence_reason="All data sources are fresh and reconciled",
            )

        # Check severity - any staleness or drift is at least DEGRADED
        is_blocked = (
            "data_staleness" in guardrails or
            "no_sync_ever" in guardrails or
            "reconciliation_drift" in guardrails or
            "staleness_check_failed" in guardrails or
            "reconciliation_check_failed" in guardrails
        )

        if is_blocked:
            return SignalOutput(
                status=SignalStatus.BLOCKED,
                summary=f"Data trust gate BLOCKED: {'; '.join(issues)}",
                recommended_action=(
                    "DO NOT make high-confidence decisions. "
                    "Run data sync and reconciliation to restore data trust. "
                    "All recommendations from other signals should be treated as UNTRUSTED."
                ),
                evidence=evidence,
                guardrails_triggered=guardrails,
                confidence=SignalConfidence.LOW,
                confidence_reason="Data quality issues prevent reliable recommendations",
            )

        # Less severe issues - degraded
        return SignalOutput(
            status=SignalStatus.DEGRADED,
            summary=f"Data trust gate DEGRADED: {'; '.join(issues)}",
            recommended_action=(
                "Proceed with caution. Verify recommendations manually. "
                "Consider running data sync to improve confidence."
            ),
            evidence=evidence,
            guardrails_triggered=guardrails,
            confidence=SignalConfidence.MEDIUM,
            confidence_reason="Some data quality concerns but not critical",
        )
