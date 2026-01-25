"""Portfolio endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.portfolio import PortfolioSnapshot, NAVHistory
from app.models.position import Position
from app.models.alert import Alert
from app.models.trade import TradeRecommendation
from app.schemas.portfolio import (
    PortfolioSummary,
    PortfolioHistoryResponse,
    PortfolioHistoryPoint,
    DashboardResponse,
    AllocationBreakdown,
    AlertSummary,
)
from app.services.data.data_sync import data_sync_service

router = APIRouter()
settings = get_settings()


@router.get("", response_model=PortfolioSummary)
async def get_portfolio(db: AsyncSession = Depends(get_db)) -> PortfolioSummary:
    """Get current portfolio summary."""
    wallet = settings.wallet_address

    # Get latest portfolio snapshot
    stmt = (
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.wallet_address == wallet)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()

    # Get position count
    pos_stmt = select(func.count()).select_from(Position).where(Position.wallet_address == wallet)
    pos_result = await db.execute(pos_stmt)
    position_count = pos_result.scalar() or 0

    if snapshot is None:
        # Return empty summary if no data
        return PortfolioSummary(
            wallet_address=wallet,
            nav_mid=Decimal("0"),
            nav_exec_50pct=Decimal("0"),
            nav_exec_100pct=Decimal("0"),
            tao_price_usd=Decimal("0"),
            nav_usd=Decimal("0"),
            allocation=AllocationBreakdown(),
            executable_drawdown_pct=Decimal("0"),
            drawdown_from_ath_pct=Decimal("0"),
            nav_ath=Decimal("0"),
            active_positions=0,
            eligible_subnets=0,
            overall_regime="neutral",
            daily_turnover_pct=Decimal("0"),
            weekly_turnover_pct=Decimal("0"),
            as_of=datetime.now(timezone.utc),
        )

    # Calculate allocation percentages
    total = snapshot.nav_mid or Decimal("1")
    allocation = AllocationBreakdown(
        root_tao=snapshot.root_allocation_tao,
        root_pct=(snapshot.root_allocation_tao / total * 100) if total else Decimal("0"),
        dtao_tao=snapshot.dtao_allocation_tao,
        dtao_pct=(snapshot.dtao_allocation_tao / total * 100) if total else Decimal("0"),
        unstaked_tao=snapshot.unstaked_buffer_tao,
        unstaked_pct=(snapshot.unstaked_buffer_tao / total * 100) if total else Decimal("0"),
    )

    return PortfolioSummary(
        wallet_address=wallet,
        nav_mid=snapshot.nav_mid,
        nav_exec_50pct=snapshot.nav_exec_50pct,
        nav_exec_100pct=snapshot.nav_exec_100pct,
        tao_price_usd=snapshot.tao_price_usd,
        nav_usd=snapshot.nav_usd,
        allocation=allocation,
        executable_drawdown_pct=snapshot.executable_drawdown * 100,
        drawdown_from_ath_pct=snapshot.drawdown_from_ath * 100,
        nav_ath=Decimal("0"),  # TODO: compute from NAVHistory
        active_positions=position_count,
        eligible_subnets=snapshot.eligible_subnets,
        overall_regime=snapshot.overall_regime,
        daily_turnover_pct=snapshot.daily_turnover * 100,
        weekly_turnover_pct=snapshot.weekly_turnover * 100,
        as_of=snapshot.timestamp,
    )


@router.get("/history", response_model=PortfolioHistoryResponse)
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> PortfolioHistoryResponse:
    """Get portfolio NAV history."""
    wallet = settings.wallet_address

    stmt = (
        select(NAVHistory)
        .where(NAVHistory.wallet_address == wallet)
        .order_by(NAVHistory.date.desc())
        .limit(days)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    history = [
        PortfolioHistoryPoint(
            date=r.date,
            nav_mid=r.nav_mid_close,
            nav_exec=r.nav_exec_close,
            nav_ath=r.nav_exec_ath,
            drawdown_pct=((r.nav_exec_ath - r.nav_exec_close) / r.nav_exec_ath * 100)
                if r.nav_exec_ath else Decimal("0"),
            daily_return_pct=r.daily_return_pct,
        )
        for r in reversed(records)
    ]

    # Calculate cumulative return and max drawdown
    if history:
        first_nav = history[0].nav_exec
        last_nav = history[-1].nav_exec
        cumulative = ((last_nav - first_nav) / first_nav * 100) if first_nav else Decimal("0")
        max_dd = max((p.drawdown_pct for p in history), default=Decimal("0"))
    else:
        cumulative = Decimal("0")
        max_dd = Decimal("0")

    return PortfolioHistoryResponse(
        wallet_address=wallet,
        history=history,
        total_days=len(history),
        cumulative_return_pct=cumulative,
        max_drawdown_pct=max_dd,
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> DashboardResponse:
    """Get complete dashboard data."""
    wallet = settings.wallet_address
    now = datetime.now(timezone.utc)

    # Get portfolio summary
    portfolio = await get_portfolio(db)

    # Count alerts by severity
    alert_stmt = (
        select(Alert.severity, func.count())
        .where(Alert.is_active == True)
        .group_by(Alert.severity)
    )
    alert_result = await db.execute(alert_stmt)
    alert_counts = dict(alert_result.fetchall())

    alerts = AlertSummary(
        critical=alert_counts.get("critical", 0),
        warning=alert_counts.get("warning", 0),
        info=alert_counts.get("info", 0),
    )

    # Count pending recommendations
    rec_stmt = (
        select(func.count())
        .select_from(TradeRecommendation)
        .where(
            TradeRecommendation.wallet_address == wallet,
            TradeRecommendation.status == "pending",
        )
    )
    rec_result = await db.execute(rec_stmt)
    pending_count = rec_result.scalar() or 0

    urgent_stmt = (
        select(func.count())
        .select_from(TradeRecommendation)
        .where(
            TradeRecommendation.wallet_address == wallet,
            TradeRecommendation.status == "pending",
            TradeRecommendation.is_urgent == True,
        )
    )
    urgent_result = await db.execute(urgent_stmt)
    urgent_count = urgent_result.scalar() or 0

    return DashboardResponse(
        portfolio=portfolio,
        alerts=alerts,
        pending_recommendations=pending_count,
        urgent_recommendations=urgent_count,
        last_sync=data_sync_service.last_sync,
        data_stale=data_sync_service.is_data_stale(),
        generated_at=now,
    )
