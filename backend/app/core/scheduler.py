"""APScheduler configuration for automatic data sync.

Runs sync_all() at configured intervals to keep data fresh without manual refresh.
"""

import asyncio
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings

logger = structlog.get_logger()

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


async def _run_scheduled_sync() -> None:
    """Run the scheduled data sync job."""
    from app.services.data import data_sync_service

    logger.info("Scheduled sync starting")
    try:
        results = await data_sync_service.sync_all(include_analysis=True)
        logger.info(
            "Scheduled sync completed",
            subnets=results.get("subnets", 0),
            positions=results.get("positions", 0),
            pools=results.get("pools", 0),
        )
    except Exception as e:
        logger.error("Scheduled sync failed", error=str(e))


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
    }
