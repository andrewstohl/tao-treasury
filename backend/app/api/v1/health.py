"""Health check endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.common import HealthResponse
from app.services.data.taostats_client import taostats_client
from app.services.data.data_sync import data_sync_service

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

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        timestamp=now,
        version=__version__,
        database=db_status,
        redis=redis_status,
        taostats_api=api_status,
        last_sync=data_sync_service.last_sync,
        data_stale=data_sync_service.is_data_stale(),
    )
