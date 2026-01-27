"""Earnings attribution endpoints for Phase 2.

Provides endpoints for computing and querying earnings data.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services.analysis.earnings import get_earnings_service

router = APIRouter()


@router.get("/summary")
async def get_earnings_summary(
    start: Optional[str] = Query(
        default=None,
        description="Start datetime in ISO format (defaults to 30 days ago)"
    ),
    end: Optional[str] = Query(
        default=None,
        description="End datetime in ISO format (defaults to now)"
    ),
    wallet: Optional[str] = Query(
        default=None,
        description="Wallet address (defaults to configured WALLET_ADDRESS)"
    ),
) -> Dict[str, Any]:
    """Get earnings summary for a wallet over a time range.

    Computes:
    - Total start/end values in TAO
    - Net flows (stakes - unstakes) in TAO
    - Earnings = end_value - start_value - net_flows
    - Earnings percentage and annualized APY estimate
    - Per-netuid breakdown

    The core identity used:
        earnings_tao = (end_value_tao - start_value_tao) - net_flows_tao
    """
    settings = get_settings()

    if not settings.enable_earnings_endpoints:
        raise HTTPException(
            status_code=403,
            detail="Earnings endpoints are disabled"
        )

    # Parse dates
    now = datetime.now(timezone.utc)

    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end datetime format. Use ISO format."
            )
    else:
        end_dt = now

    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start datetime format. Use ISO format."
            )
    else:
        start_dt = end_dt - timedelta(days=30)

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=400,
            detail="Start datetime must be before end datetime"
        )

    service = get_earnings_service()
    return await service.get_earnings_summary(
        start=start_dt,
        end=end_dt,
        wallet_address=wallet,
    )


@router.get("/timeseries")
async def get_earnings_timeseries(
    start: Optional[str] = Query(
        default=None,
        description="Start datetime in ISO format (defaults to 7 days ago)"
    ),
    end: Optional[str] = Query(
        default=None,
        description="End datetime in ISO format (defaults to now)"
    ),
    granularity: str = Query(
        default="day",
        pattern="^(hour|day)$",
        description="Time bucket granularity: 'hour' or 'day'"
    ),
    wallet: Optional[str] = Query(
        default=None,
        description="Wallet address (defaults to configured WALLET_ADDRESS)"
    ),
    include_by_netuid: Optional[bool] = Query(
        default=None,
        description="Include per-netuid breakdown (can be heavy)"
    ),
) -> Dict[str, Any]:
    """Get earnings timeseries for a wallet.

    Returns an array of time buckets with earnings metrics.
    Useful for charting earnings over time.
    """
    settings = get_settings()

    if not settings.enable_earnings_endpoints:
        raise HTTPException(
            status_code=403,
            detail="Earnings endpoints are disabled"
        )

    # Parse dates
    now = datetime.now(timezone.utc)

    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end datetime format. Use ISO format."
            )
    else:
        end_dt = now

    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start datetime format. Use ISO format."
            )
    else:
        # Default to 7 days for timeseries
        start_dt = end_dt - timedelta(days=7)

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=400,
            detail="Start datetime must be before end datetime"
        )

    # Limit time range for hourly granularity
    if granularity == "hour":
        max_hours = 168  # 7 days
        hours_requested = (end_dt - start_dt).total_seconds() / 3600
        if hours_requested > max_hours:
            raise HTTPException(
                status_code=400,
                detail=f"Hourly granularity limited to {max_hours} hours (7 days)"
            )

    service = get_earnings_service()
    return await service.get_earnings_timeseries(
        start=start_dt,
        end=end_dt,
        granularity=granularity,
        wallet_address=wallet,
        include_by_netuid=include_by_netuid,
    )
