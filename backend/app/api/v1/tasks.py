"""Task/operations endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks

from app.schemas.common import SyncResponse
from app.services.data.data_sync import data_sync_service

router = APIRouter()


@router.post("/refresh", response_model=SyncResponse)
async def trigger_refresh(background_tasks: BackgroundTasks) -> SyncResponse:
    """Manually trigger a data refresh with full analysis.

    This runs:
    - Subnet and pool sync
    - Position sync
    - Validator sync
    - Transaction history sync
    - Cost basis computation
    - Slippage surface sync
    - NAV calculation with executable pricing
    - Risk check (drawdown, concentration)
    """
    results = await data_sync_service.sync_all(include_analysis=True)

    return SyncResponse(
        success=len(results.get("errors", [])) == 0,
        timestamp=datetime.now(timezone.utc),
        subnets=results.get("subnets", 0),
        pools=results.get("pools", 0),
        positions=results.get("positions", 0),
        validators=results.get("validators", 0),
        transactions=results.get("transactions", 0),
        slippage_surfaces=results.get("slippage_surfaces", 0),
        cost_basis_computed=results.get("cost_basis_computed", False),
        nav_computed=results.get("nav_computed", False),
        nav_executable_tao=results.get("nav_executable_tao"),
        risk_check=results.get("risk_check", False),
        risk_score=results.get("risk_score"),
        alerts=results.get("alerts", 0),
        errors=results.get("errors", []),
    )
