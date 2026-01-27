"""Signal endpoints for Phase 3.

Provides endpoints for running and querying decision support signals.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services.signals.registry import get_signal_registry

router = APIRouter()


@router.get("/catalog")
async def get_signal_catalog() -> List[Dict[str, Any]]:
    """Get catalog of all registered signals.

    Returns signal definitions including:
    - id: Unique signal identifier
    - name: Human-readable name
    - description: What the signal does
    - actionability: What actions it enables
    - actionability_score: 1-10 score
    - edge_hypothesis: Why this signal provides value
    - correctness_risks: Known limitations
    - required_datasets: Data dependencies
    - ongoing_cost: Compute cost estimate
    - latency_sensitivity: How time-sensitive the signal is
    - failure_behavior: What happens on failure
    """
    settings = get_settings()

    if not getattr(settings, "enable_signal_endpoints", True):
        raise HTTPException(
            status_code=403,
            detail="Signal endpoints are disabled"
        )

    registry = get_signal_registry()
    return registry.get_catalog()


@router.post("/run")
async def run_signals(
    signal_id: Optional[str] = Query(
        default=None,
        description="Specific signal ID to run (runs all if not specified)"
    ),
) -> Dict[str, Any]:
    """Run signals and return results.

    If signal_id is provided, runs only that signal.
    Otherwise, runs all signals (with trust gate first).

    Returns signal outputs including:
    - status: ok, degraded, or blocked
    - summary: Human-readable summary
    - recommended_action: What to do based on signal
    - evidence: Supporting data/metrics
    - guardrails_triggered: Any guardrail violations
    - confidence: low, medium, or high
    - confidence_reason: Why this confidence level
    """
    settings = get_settings()

    if not getattr(settings, "enable_signal_endpoints", True):
        raise HTTPException(
            status_code=403,
            detail="Signal endpoints are disabled"
        )

    registry = get_signal_registry()

    if signal_id:
        # Run single signal
        output = await registry.run_signal(signal_id)
        if output is None:
            raise HTTPException(
                status_code=404,
                detail=f"Signal '{signal_id}' not found"
            )
        return {
            "signal_id": signal_id,
            "output": output.to_dict(),
        }

    # Run all signals
    results = await registry.run_all_signals()
    return {
        "signal_count": len(results),
        "signals": {
            signal_id: output.to_dict()
            for signal_id, output in results.items()
        },
    }


@router.post("/run-and-store")
async def run_and_store_signals() -> Dict[str, Any]:
    """Run all signals and store results to database.

    Returns the run_id that can be used to retrieve results later.
    """
    settings = get_settings()

    if not getattr(settings, "enable_signal_endpoints", True):
        raise HTTPException(
            status_code=403,
            detail="Signal endpoints are disabled"
        )

    registry = get_signal_registry()
    run_id = await registry.run_and_store()

    return {
        "run_id": run_id,
        "status": "completed",
    }


@router.get("/latest")
async def get_latest_signals() -> Dict[str, Any]:
    """Get the most recent signal run results.

    Returns the stored results from the last run-and-store operation.
    """
    settings = get_settings()

    if not getattr(settings, "enable_signal_endpoints", True):
        raise HTTPException(
            status_code=403,
            detail="Signal endpoints are disabled"
        )

    registry = get_signal_registry()
    result = await registry.get_latest_run()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No signal runs found"
        )

    return result


@router.get("/history/{signal_id}")
async def get_signal_history(
    signal_id: str,
    days: int = Query(default=7, ge=1, le=90, description="Number of days of history"),
) -> List[Dict[str, Any]]:
    """Get historical runs for a specific signal.

    Returns the signal output history for the specified number of days.
    """
    settings = get_settings()

    if not getattr(settings, "enable_signal_endpoints", True):
        raise HTTPException(
            status_code=403,
            detail="Signal endpoints are disabled"
        )

    # Verify signal exists
    registry = get_signal_registry()
    if registry.get_signal(signal_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Signal '{signal_id}' not found"
        )

    history = await registry.get_signal_history(signal_id, days=days)
    return history


@router.get("/{signal_id}")
async def get_signal_definition(signal_id: str) -> Dict[str, Any]:
    """Get definition for a specific signal.

    Returns the signal's metadata and configuration.
    """
    settings = get_settings()

    if not getattr(settings, "enable_signal_endpoints", True):
        raise HTTPException(
            status_code=403,
            detail="Signal endpoints are disabled"
        )

    registry = get_signal_registry()
    signal = registry.get_signal(signal_id)

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail=f"Signal '{signal_id}' not found"
        )

    defn = signal.get_definition()
    return {
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
    }
