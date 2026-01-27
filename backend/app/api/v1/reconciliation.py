"""Reconciliation endpoints for Phase 2.

Provides endpoints for running and querying reconciliation checks.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services.analysis.reconciliation import get_reconciliation_service

router = APIRouter()


@router.post("/run")
async def run_reconciliation(
    wallet: Optional[str] = Query(
        default=None,
        description="Wallet address (defaults to configured WALLET_ADDRESS)"
    ),
) -> Dict[str, Any]:
    """Run a reconciliation check.

    Compares stored position data vs live TaoStats API data.

    For each position:
    - Compares TAO value (stored vs live)
    - Compares alpha balance
    - Checks validator hotkey

    Uses tolerances from settings:
    - Absolute: reconciliation_absolute_tolerance_tao (default 0.0001 TAO)
    - Relative: reconciliation_relative_tolerance_pct (default 0.1%)

    A check passes if within either tolerance.
    """
    settings = get_settings()

    if not settings.enable_reconciliation_endpoints:
        raise HTTPException(
            status_code=403,
            detail="Reconciliation endpoints are disabled"
        )

    service = get_reconciliation_service()
    run = await service.run_reconciliation(wallet_address=wallet)

    return run.to_dict()


@router.get("/latest")
async def get_latest_reconciliation(
    wallet: Optional[str] = Query(
        default=None,
        description="Wallet address (defaults to configured WALLET_ADDRESS)"
    ),
) -> Dict[str, Any]:
    """Get the most recent reconciliation run.

    Returns the full reconciliation run record including:
    - Overall pass/fail status
    - Per-netuid check results
    - Value diffs and tolerance analysis
    """
    settings = get_settings()

    if not settings.enable_reconciliation_endpoints:
        raise HTTPException(
            status_code=403,
            detail="Reconciliation endpoints are disabled"
        )

    service = get_reconciliation_service()
    run = await service.get_latest_run(wallet_address=wallet)

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No reconciliation runs found"
        )

    return run.to_dict()


@router.get("/summary")
async def get_reconciliation_summary() -> Dict[str, Any]:
    """Get reconciliation summary for dashboard.

    Returns a lightweight summary of the latest reconciliation status.
    Used by Trust Pack and monitoring dashboards.
    """
    settings = get_settings()

    if not settings.enable_reconciliation_endpoints:
        raise HTTPException(
            status_code=403,
            detail="Reconciliation endpoints are disabled"
        )

    service = get_reconciliation_service()
    return await service.get_trust_pack_summary()
