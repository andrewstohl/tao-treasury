"""Backtest API endpoints for viability scoring validation."""

import asyncio
from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, Query

from app.services.backtest.backtest_engine import BacktestEngine
from app.services.data.history_backfill import HistoryBackfillService, get_backfill_status

router = APIRouter()


@router.get("/run")
async def run_backtest(
    interval_days: int = Query(default=1, ge=1, le=7, description="Days between scoring dates"),
):
    """Run viability scoring backtest over all available historical data.

    Uses the current active viability config (from DB or env defaults).
    Returns tier-level performance metrics and tier separation analysis.
    """
    engine = BacktestEngine()
    result = await engine.run(interval_days=interval_days)
    return asdict(result)


@router.get("/run-detailed")
async def run_backtest_detailed(
    interval_days: int = Query(default=1, ge=1, le=7, description="Days between scoring dates"),
):
    """Run backtest with per-subnet detail in daily results.

    Same as /run but includes individual subnet scores and returns
    in each daily result. Can be large for many subnets and dates.
    """
    engine = BacktestEngine()
    result = await engine.run(
        interval_days=interval_days,
        include_subnet_detail=True,
    )
    return asdict(result)


@router.post("/backfill")
async def trigger_backfill(
    lookback_days: int = Query(default=365, ge=30, le=730, description="Days of history to fetch"),
    netuids: Optional[str] = Query(default=None, description="Comma-separated netuids, or omit for all"),
):
    """Trigger historical data backfill from TaoStats pool_history API.

    Runs in the background. Use GET /backtest/backfill/status to monitor progress.
    Fetches daily pool snapshots and creates SubnetSnapshot records for backtesting.
    """
    status = get_backfill_status()
    if status.running:
        return {"message": "Backfill already running", "status": status.to_dict()}

    parsed_netuids: Optional[List[int]] = None
    if netuids:
        parsed_netuids = [int(n.strip()) for n in netuids.split(",") if n.strip()]

    service = HistoryBackfillService()

    async def _run_backfill():
        await service.backfill(lookback_days=lookback_days, netuids=parsed_netuids)

    # Run as a background asyncio task
    asyncio.get_event_loop().create_task(_run_backfill())

    return {
        "message": "Backfill started",
        "lookback_days": lookback_days,
        "netuids": parsed_netuids,
    }


@router.get("/backfill/status")
async def backfill_status():
    """Get current backfill progress."""
    status = get_backfill_status()
    return status.to_dict()


@router.get("/simulate")
async def simulate_portfolio(
    interval_days: int = Query(default=3, ge=1, le=14, description="Days between rebalances"),
    initial_capital: float = Query(default=100.0, ge=1, le=1000000, description="Starting TAO"),
    tier: str = Query(default="tier_1", description="Single target tier (ignored if tier_weights provided)"),
    start_date: Optional[str] = Query(default=None, description="Start date ISO format (YYYY-MM-DD), default 6 months ago"),
    tier_weights: Optional[str] = Query(default=None, description="Multi-tier weights, e.g. 'tier_1:0.4,tier_2:0.3,tier_3:0.3'"),
):
    """Simulate a portfolio holding qualifying subnets.

    Supports single-tier (equal-weight) or multi-tier weighted allocation.
    For multi-tier, pass tier_weights as 'tier_1:0.4,tier_2:0.3,tier_3:0.3'.
    Within each tier, subnets are equal-weighted.
    If a tier has no qualifying subnets, that allocation is parked in root (0% return).
    """
    parsed_weights = None
    if tier_weights:
        parsed_weights = {}
        for part in tier_weights.split(","):
            part = part.strip()
            if ":" in part:
                t, w = part.split(":", 1)
                parsed_weights[t.strip()] = float(w.strip())

    engine = BacktestEngine()
    result = await engine.simulate_portfolio(
        interval_days=interval_days,
        initial_capital=initial_capital,
        target_tier=tier,
        start_date=start_date,
        tier_weights=parsed_weights,
    )
    return asdict(result)
