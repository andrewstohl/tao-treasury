"""Signal registry for Phase 3.

Manages registration and execution of all signals.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

import structlog
from sqlalchemy import select, desc

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.signal import SignalRun
from app.services.signals.base import BaseSignal, SignalDefinition, SignalOutput, SignalStatus

logger = structlog.get_logger()


class SignalRegistry:
    """Registry for all decision support signals.

    Handles signal registration, execution, and result storage.
    """

    def __init__(self):
        self._signals: Dict[str, BaseSignal] = {}
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def register(self, signal: BaseSignal) -> None:
        """Register a signal with the registry."""
        definition = signal.get_definition()
        self._signals[definition.id] = signal
        logger.info("Registered signal", signal_id=definition.id, name=definition.name)

    def get_signal(self, signal_id: str) -> Optional[BaseSignal]:
        """Get a signal by ID."""
        return self._signals.get(signal_id)

    def get_all_signals(self) -> List[BaseSignal]:
        """Get all registered signals."""
        return list(self._signals.values())

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Get catalog of all signal definitions."""
        catalog = []
        for signal in self._signals.values():
            defn = signal.get_definition()
            catalog.append({
                "id": defn.id,
                "name": defn.name,
                "description": defn.description,
                "actionability": defn.actionability,
                "actionability_score": defn.actionability_score,
                "edge_hypothesis": defn.edge_hypothesis,
                "correctness_risks": defn.correctness_risks,
                "required_datasets": defn.required_datasets,
                "ongoing_cost": defn.ongoing_cost,
                "latency_sensitivity": defn.latency_sensitivity,
                "failure_behavior": defn.failure_behavior,
            })
        return catalog

    async def run_signal(self, signal_id: str) -> Optional[SignalOutput]:
        """Run a single signal and return output."""
        signal = self.get_signal(signal_id)
        if signal is None:
            logger.warning("Signal not found", signal_id=signal_id)
            return None

        try:
            output = await signal.run()
            return output
        except Exception as e:
            logger.error("Signal execution failed", signal_id=signal_id, error=str(e))
            return SignalOutput.blocked(f"Signal execution failed: {str(e)}")

    async def run_all_signals(self) -> Dict[str, SignalOutput]:
        """Run all registered signals and return results.

        Returns dict mapping signal_id to output.
        """
        results = {}

        # First run the Data Trust Gate signal
        trust_gate_id = "data_trust_gate"
        trust_gate = self.get_signal(trust_gate_id)

        trust_gate_output = None
        if trust_gate:
            trust_gate_output = await self.run_signal(trust_gate_id)
            results[trust_gate_id] = trust_gate_output

        # If trust gate is blocked, mark other signals as degraded
        trust_blocked = (
            trust_gate_output is not None and
            trust_gate_output.status == SignalStatus.BLOCKED
        )

        # Run remaining signals
        for signal_id, signal in self._signals.items():
            if signal_id == trust_gate_id:
                continue  # Already ran

            if trust_blocked:
                # Force other signals to be aware of trust issues
                defn = signal.get_definition()
                results[signal_id] = SignalOutput(
                    status=SignalStatus.DEGRADED,
                    summary=f"Signal degraded due to data trust issues",
                    recommended_action="Resolve data trust issues before acting on recommendations",
                    guardrails_triggered=["data_trust_gate_blocked"],
                    confidence=SignalOutput.blocked("").confidence,
                    confidence_reason="Data trust gate is blocked - cannot produce high-confidence recommendations",
                )
            else:
                output = await self.run_signal(signal_id)
                if output:
                    results[signal_id] = output

        return results

    async def run_and_store(self) -> str:
        """Run all signals and store results.

        Returns the run_id for this execution.
        """
        run_id = f"signals_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        logger.info("Starting signal run", run_id=run_id)

        results = await self.run_all_signals()

        # Store each result
        async with get_db_context() as db:
            for signal_id, output in results.items():
                signal = self.get_signal(signal_id)
                if signal is None:
                    continue

                defn = signal.get_definition()

                run = SignalRun(
                    run_id=run_id,
                    signal_id=signal_id,
                    signal_name=defn.name,
                    status=output.status.value,
                    confidence=output.confidence.value,
                    confidence_reason=output.confidence_reason,
                    summary=output.summary,
                    recommended_action=output.recommended_action,
                    evidence=output.evidence,
                    guardrails_triggered=output.guardrails_triggered,
                    full_output=output.to_dict(),
                    error_message=output.error_message,
                )
                db.add(run)

            await db.commit()

        logger.info("Completed signal run", run_id=run_id, signal_count=len(results))
        return run_id

    async def get_latest_run(self) -> Optional[Dict[str, Any]]:
        """Get the most recent signal run results."""
        async with get_db_context() as db:
            # Get most recent run_id
            stmt = (
                select(SignalRun.run_id)
                .order_by(desc(SignalRun.created_at))
                .limit(1)
            )
            result = await db.execute(stmt)
            row = result.first()

            if not row:
                return None

            run_id = row[0]

            # Get all signals from that run
            stmt = select(SignalRun).where(SignalRun.run_id == run_id)
            result = await db.execute(stmt)
            runs = result.scalars().all()

            return {
                "run_id": run_id,
                "created_at": runs[0].created_at.isoformat() if runs else None,
                "signal_count": len(runs),
                "signals": {r.signal_id: r.to_dict() for r in runs},
                "summary": self._build_run_summary(runs),
            }

    async def get_signal_history(
        self,
        signal_id: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Get history for a specific signal."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with get_db_context() as db:
            stmt = (
                select(SignalRun)
                .where(
                    SignalRun.signal_id == signal_id,
                    SignalRun.created_at >= cutoff,
                )
                .order_by(desc(SignalRun.created_at))
            )
            result = await db.execute(stmt)
            runs = result.scalars().all()

            return [r.to_dict() for r in runs]

    def _build_run_summary(self, runs: List[SignalRun]) -> Dict[str, Any]:
        """Build a summary of a signal run."""
        total = len(runs)
        ok_count = sum(1 for r in runs if r.status == "ok")
        degraded_count = sum(1 for r in runs if r.status == "degraded")
        blocked_count = sum(1 for r in runs if r.status == "blocked")

        all_guardrails = []
        for r in runs:
            all_guardrails.extend(r.guardrails_triggered or [])

        return {
            "total_signals": total,
            "ok_count": ok_count,
            "degraded_count": degraded_count,
            "blocked_count": blocked_count,
            "overall_status": (
                "blocked" if blocked_count > 0 else
                "degraded" if degraded_count > 0 else
                "ok"
            ),
            "unique_guardrails_triggered": list(set(all_guardrails)),
        }


# Lazy singleton with signal registration
_signal_registry: Optional[SignalRegistry] = None


def get_signal_registry() -> SignalRegistry:
    """Get or create the SignalRegistry singleton.

    Also registers all signals on first access.
    """
    global _signal_registry
    if _signal_registry is None:
        _signal_registry = SignalRegistry()
        _register_all_signals(_signal_registry)
    return _signal_registry


def _register_all_signals(registry: SignalRegistry) -> None:
    """Register all implemented signals."""
    # Import and register signals here to avoid circular imports
    from app.services.signals.implementations.data_trust_gate import DataTrustGateSignal
    from app.services.signals.implementations.earnings_leaderboard import EarningsLeaderboardSignal
    from app.services.signals.implementations.slippage_capacity import SlippageCapacitySignal
    from app.services.signals.implementations.concentration_risk import ConcentrationRiskSignal

    registry.register(DataTrustGateSignal())
    registry.register(EarningsLeaderboardSignal())
    registry.register(SlippageCapacitySignal())
    registry.register(ConcentrationRiskSignal())
