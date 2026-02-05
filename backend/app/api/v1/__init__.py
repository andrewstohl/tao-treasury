"""API v1 router."""

from fastapi import APIRouter

from app.api.v1 import health, portfolio, positions, subnets, alerts, recommendations, tasks, strategy
from app.api.v1 import earnings, reconciliation, signals, examples, settings, backtest

router = APIRouter(prefix="/api/v1")

router.include_router(health.router, tags=["Health"])
router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
router.include_router(positions.router, prefix="/positions", tags=["Positions"])
router.include_router(subnets.router, prefix="/subnets", tags=["Subnets"])
router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
router.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])
router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
router.include_router(strategy.router, prefix="/strategy", tags=["Strategy"])
router.include_router(earnings.router, prefix="/earnings", tags=["Earnings"])
router.include_router(reconciliation.router, prefix="/reconciliation", tags=["Reconciliation"])
router.include_router(signals.router, prefix="/signals", tags=["Signals"])
router.include_router(examples.router, prefix="/examples", tags=["Examples"])
router.include_router(settings.router, prefix="/settings", tags=["Settings"])
router.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])
