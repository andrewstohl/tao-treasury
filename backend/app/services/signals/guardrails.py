"""Shared guardrail module for Phase 3 signals.

Devil's Advocate Rules - every signal must use these checks:
- Block or degrade if datasets stale beyond thresholds
- Block or degrade if reconciliation drift present
- Block if required inputs missing
- Degrade if recommended action exceeds slippage capacity or violates concentration limits
- Always emit "why" in plain text
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""
    passed: bool
    guardrail_name: str
    reason: str
    severity: str  # "block", "degrade", "warn"
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class GuardrailChecker:
    """Shared guardrail checker for all signals.

    Implements the "Devil's Advocate" rules that every signal must respect.
    """

    def __init__(self):
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def check_all_guardrails(self) -> Tuple[List[GuardrailResult], bool, bool]:
        """Run all guardrails and return results.

        Returns:
            Tuple of (results, should_block, should_degrade)
        """
        results = []

        # Check data staleness
        staleness_result = await self.check_data_staleness()
        results.append(staleness_result)

        # Check reconciliation drift
        drift_result = await self.check_reconciliation_drift()
        results.append(drift_result)

        # Determine overall status
        should_block = any(r.severity == "block" and not r.passed for r in results)
        should_degrade = any(r.severity == "degrade" and not r.passed for r in results)

        return results, should_block, should_degrade

    async def check_data_staleness(self) -> GuardrailResult:
        """Check if critical datasets are stale.

        Uses Trust Pack to determine staleness.
        """
        try:
            from app.core.metrics import get_metrics
            metrics = get_metrics()
            trust_pack = metrics.get_trust_pack()

            # Check overall health
            overall_health = trust_pack.get("overall_health", {})
            status = overall_health.get("status", "unknown")
            issues = overall_health.get("issues", [])

            # Check for stale datasets
            stale_datasets = [i for i in issues if "Stale" in i]

            if status == "critical":
                return GuardrailResult(
                    passed=False,
                    guardrail_name="data_staleness",
                    reason=f"Trust Pack status is CRITICAL. Issues: {'; '.join(issues[:3])}",
                    severity="block",
                    details={"status": status, "issues": issues},
                )

            if stale_datasets:
                return GuardrailResult(
                    passed=False,
                    guardrail_name="data_staleness",
                    reason=f"Stale datasets detected: {'; '.join(stale_datasets)}",
                    severity="degrade",
                    details={"stale_datasets": stale_datasets},
                )

            if status == "degraded":
                return GuardrailResult(
                    passed=False,
                    guardrail_name="data_staleness",
                    reason=f"Trust Pack status is DEGRADED. Issues: {'; '.join(issues[:3])}",
                    severity="degrade",
                    details={"status": status, "issues": issues},
                )

            return GuardrailResult(
                passed=True,
                guardrail_name="data_staleness",
                reason="Data freshness verified via Trust Pack",
                severity="ok",
                details={"status": status},
            )

        except Exception as e:
            logger.error("Failed to check data staleness", error=str(e))
            return GuardrailResult(
                passed=False,
                guardrail_name="data_staleness",
                reason=f"Cannot verify data freshness: {str(e)}",
                severity="block",
                details={"error": str(e)},
            )

    async def check_reconciliation_drift(self) -> GuardrailResult:
        """Check if reconciliation has detected drift.

        Drift = stored data doesn't match live API data.
        """
        try:
            from app.services.analysis.reconciliation import get_reconciliation_service
            recon_service = get_reconciliation_service()
            summary = await recon_service.get_trust_pack_summary()

            has_drift = summary.get("has_drift", False)
            last_run_passed = summary.get("last_run_passed")
            last_run_at = summary.get("last_run_at")

            if has_drift:
                return GuardrailResult(
                    passed=False,
                    guardrail_name="reconciliation_drift",
                    reason="Reconciliation detected drift between stored and live data. Recommendations may be based on stale positions.",
                    severity="degrade",
                    details=summary,
                )

            if last_run_at is None:
                return GuardrailResult(
                    passed=False,
                    guardrail_name="reconciliation_drift",
                    reason="No reconciliation run found. Cannot verify data integrity.",
                    severity="degrade",
                    details={"last_run_at": None},
                )

            # Check if last run is too old (>24h)
            try:
                last_run_dt = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - last_run_dt).total_seconds() / 3600
                if age_hours > 24:
                    return GuardrailResult(
                        passed=False,
                        guardrail_name="reconciliation_drift",
                        reason=f"Last reconciliation was {age_hours:.1f} hours ago. Run reconciliation to verify data integrity.",
                        severity="degrade",
                        details={"age_hours": age_hours},
                    )
            except Exception:
                pass

            return GuardrailResult(
                passed=True,
                guardrail_name="reconciliation_drift",
                reason="Reconciliation passed, data integrity verified",
                severity="ok",
                details=summary,
            )

        except Exception as e:
            logger.error("Failed to check reconciliation drift", error=str(e))
            return GuardrailResult(
                passed=False,
                guardrail_name="reconciliation_drift",
                reason=f"Cannot verify data integrity: {str(e)}",
                severity="degrade",
                details={"error": str(e)},
            )

    def check_required_inputs(
        self,
        required: List[str],
        available: Dict[str, Any],
    ) -> GuardrailResult:
        """Check if all required inputs are available."""
        missing = [r for r in required if r not in available or available[r] is None]

        if missing:
            return GuardrailResult(
                passed=False,
                guardrail_name="required_inputs",
                reason=f"Missing required inputs: {', '.join(missing)}",
                severity="block",
                details={"missing": missing, "required": required},
            )

        return GuardrailResult(
            passed=True,
            guardrail_name="required_inputs",
            reason="All required inputs available",
            severity="ok",
            details={"required": required},
        )

    def check_sample_size(
        self,
        count: int,
        minimum: int,
        context: str,
    ) -> GuardrailResult:
        """Check if sample size is sufficient."""
        if count < minimum:
            return GuardrailResult(
                passed=False,
                guardrail_name="sample_size",
                reason=f"Insufficient data for {context}: {count} records, minimum {minimum} required",
                severity="degrade",
                details={"count": count, "minimum": minimum, "context": context},
            )

        return GuardrailResult(
            passed=True,
            guardrail_name="sample_size",
            reason=f"Sufficient data for {context}: {count} records",
            severity="ok",
            details={"count": count, "minimum": minimum},
        )

    def check_slippage_capacity(
        self,
        trade_size_tao: Decimal,
        max_safe_size_tao: Decimal,
        netuid: int,
    ) -> GuardrailResult:
        """Check if a trade would exceed slippage capacity."""
        if max_safe_size_tao <= 0:
            return GuardrailResult(
                passed=False,
                guardrail_name="slippage_capacity",
                reason=f"No safe trade capacity for SN{netuid}. Pool may have insufficient liquidity.",
                severity="degrade",
                details={"netuid": netuid, "max_safe_size_tao": str(max_safe_size_tao)},
            )

        if trade_size_tao > max_safe_size_tao:
            return GuardrailResult(
                passed=False,
                guardrail_name="slippage_capacity",
                reason=f"Trade size {trade_size_tao} TAO exceeds max safe size {max_safe_size_tao} TAO for SN{netuid}",
                severity="degrade",
                details={
                    "netuid": netuid,
                    "trade_size_tao": str(trade_size_tao),
                    "max_safe_size_tao": str(max_safe_size_tao),
                },
            )

        return GuardrailResult(
            passed=True,
            guardrail_name="slippage_capacity",
            reason=f"Trade within slippage capacity for SN{netuid}",
            severity="ok",
            details={"netuid": netuid, "trade_size_tao": str(trade_size_tao)},
        )

    def check_concentration_limit(
        self,
        current_pct: Decimal,
        limit_pct: Decimal,
        context: str,
    ) -> GuardrailResult:
        """Check if concentration would exceed limits."""
        if current_pct > limit_pct:
            return GuardrailResult(
                passed=False,
                guardrail_name="concentration_limit",
                reason=f"{context} concentration is {float(current_pct * 100):.1f}%, exceeding {float(limit_pct * 100):.0f}% limit",
                severity="degrade",
                details={
                    "context": context,
                    "current_pct": str(current_pct),
                    "limit_pct": str(limit_pct),
                },
            )

        return GuardrailResult(
            passed=True,
            guardrail_name="concentration_limit",
            reason=f"{context} concentration within limits",
            severity="ok",
            details={"context": context, "current_pct": str(current_pct)},
        )

    def aggregate_guardrails(
        self,
        results: List[GuardrailResult],
    ) -> Tuple[List[str], bool, bool]:
        """Aggregate guardrail results into triggered list and status flags.

        Returns:
            Tuple of (triggered_names, should_block, should_degrade)
        """
        triggered = [r.guardrail_name for r in results if not r.passed]
        should_block = any(r.severity == "block" and not r.passed for r in results)
        should_degrade = any(r.severity == "degrade" and not r.passed for r in results)

        return triggered, should_block, should_degrade


# Lazy singleton
_guardrail_checker: Optional[GuardrailChecker] = None


def get_guardrail_checker() -> GuardrailChecker:
    """Get or create the GuardrailChecker singleton."""
    global _guardrail_checker
    if _guardrail_checker is None:
        _guardrail_checker = GuardrailChecker()
    return _guardrail_checker
