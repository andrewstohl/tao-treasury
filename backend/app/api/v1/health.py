"""Health check and observability endpoints.

Phase 0: Trust Pack endpoint for observability dashboard.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.config import get_settings
from app.schemas.common import HealthResponse
from app.services.data.taostats_client import taostats_client
from app.services.data.data_sync import data_sync_service
from app.core.scheduler import get_scheduler_status

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Check health of all services."""
    now = datetime.now(timezone.utc)

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)[:50]}"

    # Check Redis
    try:
        redis = await get_redis()
        await redis.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {str(e)[:50]}"

    # Check TaoStats API
    try:
        if await taostats_client.health_check():
            api_status = "healthy"
        else:
            api_status = "unhealthy"
    except Exception as e:
        api_status = f"unhealthy: {str(e)[:50]}"

    # Overall status
    all_healthy = all(s == "healthy" for s in [db_status, redis_status, api_status])

    # Get scheduler status
    scheduler_status = get_scheduler_status()

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        timestamp=now,
        version=__version__,
        database=db_status,
        redis=redis_status,
        taostats_api=api_status,
        last_sync=data_sync_service.last_sync,
        data_stale=data_sync_service.is_data_stale(),
        scheduler=scheduler_status,
    )


@router.get("/trust-pack")
async def get_trust_pack(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Get Trust Pack - comprehensive observability data for Phase 0.

    Returns:
        - API call metrics (success rate, latency, error counts)
        - Cache metrics (hit/miss rates)
        - Sync status per dataset (last success, staleness flags)
        - Feature flag states
        - System health summary

    This endpoint is designed for observability dashboards and
    debugging sync/API issues.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # Get metrics from collector
    try:
        from app.core.metrics import get_metrics
        metrics = get_metrics()
        trust_pack = metrics.get_trust_pack()
    except Exception as e:
        trust_pack = {
            "error": f"Failed to collect metrics: {str(e)}",
            "api_metrics": {},
            "cache_metrics": {},
            "sync_status": {},
        }

    # Add feature flag states
    trust_pack["feature_flags"] = {
        "enable_cache_metrics": settings.enable_cache_metrics,
        "enable_api_metrics": settings.enable_api_metrics,
        "enable_sync_metrics": settings.enable_sync_metrics,
        "enable_retry_after": settings.enable_retry_after,
        "enable_response_validation": settings.enable_response_validation,
        "enable_partial_failure_protection": settings.enable_partial_failure_protection,
        "enable_client_side_slippage": settings.enable_client_side_slippage,
        "enable_reconciliation": settings.enable_reconciliation,
        "enable_earnings_endpoints": settings.enable_earnings_endpoints,
        "enable_reconciliation_endpoints": settings.enable_reconciliation_endpoints,
        "enable_reconciliation_in_trust_pack": settings.enable_reconciliation_in_trust_pack,
    }

    # Add reconciliation status if enabled (Phase 2)
    if settings.enable_reconciliation_in_trust_pack:
        try:
            from app.services.analysis.reconciliation import get_reconciliation_service
            recon_service = get_reconciliation_service()
            trust_pack["reconciliation"] = await recon_service.get_trust_pack_summary()
        except Exception as e:
            trust_pack["reconciliation"] = {
                "error": f"Failed to get reconciliation status: {str(e)}",
                "has_drift": False,
            }

    # Add staleness thresholds for context
    trust_pack["staleness_config"] = {
        "warning_minutes": settings.sync_staleness_warning_minutes,
        "critical_minutes": settings.sync_staleness_critical_minutes,
    }

    # Add basic health status
    trust_pack["health"] = {
        "last_sync": data_sync_service.last_sync.isoformat() if data_sync_service.last_sync else None,
        "data_stale": data_sync_service.is_data_stale(),
        "timestamp": now.isoformat(),
        "version": __version__,
    }

    return trust_pack
