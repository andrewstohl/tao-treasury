"""APScheduler configuration for automatic data sync.

Runs sync_all() at configured intervals to keep data fresh without manual refresh.
Includes rate limit detection and backoff to handle TaoStats API limits gracefully.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from app.core.config import get_settings

logger = structlog.get_logger()

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None

# Track sync state for observability
_last_sync_result: dict = {
    "success": None,
    "timestamp": None,
    "error": None,
    "consecutive_failures": 0,
    "rate_limited": False,
}


async def _run_scheduled_sync() -> None:
    """Run the scheduled data sync job with rate limit handling."""
    global _last_sync_result
    from app.services.data import data_sync_service
    from app.services.data.taostats_client import TaoStatsRateLimitError

    logger.info("Scheduled sync starting")
    try:
        results = await data_sync_service.sync_all(include_analysis=True)

        # Check if sync had errors (including rate limit)
        errors = results.get("errors", [])
        has_rate_limit = any("rate limit" in str(e).lower() for e in errors)

        if has_rate_limit:
            _last_sync_result["rate_limited"] = True
            _last_sync_result["consecutive_failures"] += 1
            _last_sync_result["error"] = "Rate limit exceeded"
            _last_sync_result["success"] = False
            _last_sync_result["timestamp"] = datetime.now(timezone.utc).isoformat()

            # Back off: reschedule next sync with exponential delay
            _handle_rate_limit_backoff()
        elif len(errors) > 0:
            _last_sync_result["consecutive_failures"] += 1
            _last_sync_result["error"] = errors[0] if errors else "Unknown error"
            _last_sync_result["success"] = False
            _last_sync_result["rate_limited"] = False
            _last_sync_result["timestamp"] = datetime.now(timezone.utc).isoformat()
            logger.warning("Scheduled sync completed with errors", errors=errors)
        else:
            # Success - reset failure counter and restore normal interval
            _last_sync_result["consecutive_failures"] = 0
            _last_sync_result["error"] = None
            _last_sync_result["success"] = True
            _last_sync_result["rate_limited"] = False
            _last_sync_result["timestamp"] = datetime.now(timezone.utc).isoformat()

            # Restore normal scheduling interval after backoff
            reset_to_normal_interval()

            logger.info(
                "Scheduled sync completed",
                subnets=results.get("subnets", 0),
                positions=results.get("positions", 0),
                pools=results.get("pools", 0),
            )

    except TaoStatsRateLimitError as e:
        _last_sync_result["rate_limited"] = True
        _last_sync_result["consecutive_failures"] += 1
        _last_sync_result["error"] = str(e)
        _last_sync_result["success"] = False
        _last_sync_result["timestamp"] = datetime.now(timezone.utc).isoformat()
        logger.warning("Scheduled sync rate limited", error=str(e), retry_after=getattr(e, 'retry_after', None))
        _handle_rate_limit_backoff(retry_after=getattr(e, 'retry_after', None))

    except Exception as e:
        _last_sync_result["consecutive_failures"] += 1
        _last_sync_result["error"] = str(e)
        _last_sync_result["success"] = False
        _last_sync_result["rate_limited"] = False
        _last_sync_result["timestamp"] = datetime.now(timezone.utc).isoformat()
        logger.error("Scheduled sync failed", error=str(e))


def _handle_rate_limit_backoff(retry_after: int | None = None) -> None:
    """Handle rate limit by backing off the scheduler.

    If retry_after is provided, use that. Otherwise use exponential backoff
    based on consecutive failures (5, 10, 20, 30 minutes max).
    """
    scheduler = get_scheduler()
    if not scheduler.running:
        return

    # Calculate backoff delay
    if retry_after and retry_after > 0:
        delay_minutes = max(1, retry_after // 60)
    else:
        # Exponential backoff: 5, 10, 20, 30 minutes
        base_delay = 5
        failures = _last_sync_result.get("consecutive_failures", 1)
        delay_minutes = min(30, base_delay * (2 ** (failures - 1)))

    next_run = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

    logger.info(
        "Rate limited - backing off scheduler",
        delay_minutes=delay_minutes,
        next_sync=next_run.isoformat(),
        consecutive_failures=_last_sync_result.get("consecutive_failures", 0),
    )

    # Reschedule the job to run after the backoff period
    job = scheduler.get_job("data_sync")
    if job:
        job.reschedule(trigger=DateTrigger(run_date=next_run))


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler() -> None:
    """Start the background scheduler with configured sync interval."""
    settings = get_settings()
    scheduler = get_scheduler()

    # Don't start twice
    if scheduler.running:
        logger.warning("Scheduler already running")
        return

    # Add the sync job - runs every 5 minutes by default (uses wallet_refresh_minutes)
    interval_minutes = settings.wallet_refresh_minutes

    scheduler.add_job(
        _run_scheduled_sync,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="data_sync",
        name="Automatic Data Sync",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping syncs
        coalesce=True,  # If missed runs, only run once
    )

    scheduler.start()
    logger.info(
        "Scheduler started",
        sync_interval_minutes=interval_minutes,
        next_run=scheduler.get_job("data_sync").next_run_time,
    )


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    """Get current scheduler status for health checks."""
    scheduler = get_scheduler()
    job = scheduler.get_job("data_sync") if scheduler.running else None

    return {
        "running": scheduler.running,
        "next_sync": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "job_count": len(scheduler.get_jobs()) if scheduler.running else 0,
        "last_sync": _last_sync_result.copy(),
    }


def reset_to_normal_interval() -> None:
    """Reset the scheduler to normal interval after backoff period.

    Call this after a successful sync to restore normal scheduling.
    """
    settings = get_settings()
    scheduler = get_scheduler()

    if not scheduler.running:
        return

    job = scheduler.get_job("data_sync")
    if job:
        # Restore normal interval trigger
        job.reschedule(trigger=IntervalTrigger(minutes=settings.wallet_refresh_minutes))
        logger.info(
            "Scheduler reset to normal interval",
            interval_minutes=settings.wallet_refresh_minutes,
        )
