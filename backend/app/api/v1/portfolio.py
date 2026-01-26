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
    YieldSummary,
    PnLSummary,
    PositionSummary,
    ActionItem,
    PortfolioHealth,
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
            yield_summary=YieldSummary(),
            pnl_summary=PnLSummary(),
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

    # Build yield summary
    yield_summary = YieldSummary(
        portfolio_apy=getattr(snapshot, 'portfolio_apy', Decimal("0")) or Decimal("0"),
        daily_yield_tao=getattr(snapshot, 'daily_yield_tao', Decimal("0")) or Decimal("0"),
        weekly_yield_tao=getattr(snapshot, 'weekly_yield_tao', Decimal("0")) or Decimal("0"),
        monthly_yield_tao=getattr(snapshot, 'monthly_yield_tao', Decimal("0")) or Decimal("0"),
    )

    # Build P&L summary
    total_unrealized = getattr(snapshot, 'total_unrealized_pnl_tao', Decimal("0")) or Decimal("0")
    total_cost_basis = getattr(snapshot, 'total_cost_basis_tao', Decimal("0")) or Decimal("0")
    unrealized_pct = (total_unrealized / total_cost_basis * 100) if total_cost_basis else Decimal("0")

    pnl_summary = PnLSummary(
        total_unrealized_pnl_tao=total_unrealized,
        total_realized_pnl_tao=getattr(snapshot, 'total_realized_pnl_tao', Decimal("0")) or Decimal("0"),
        total_cost_basis_tao=total_cost_basis,
        unrealized_pnl_pct=unrealized_pct,
    )

    return PortfolioSummary(
        wallet_address=wallet,
        nav_mid=snapshot.nav_mid,
        nav_exec_50pct=snapshot.nav_exec_50pct,
        nav_exec_100pct=snapshot.nav_exec_100pct,
        tao_price_usd=snapshot.tao_price_usd,
        nav_usd=snapshot.nav_usd,
        allocation=allocation,
        yield_summary=yield_summary,
        pnl_summary=pnl_summary,
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


def _compute_position_health(p, weight_pct: Decimal, avg_apy: Decimal) -> tuple[str, str]:
    """Compute health status for a position.

    Returns (status, reason) where status is green/yellow/red.
    """
    reasons = []

    # Check P&L
    pnl_pct = float(p.unrealized_pnl_pct)
    if pnl_pct < -10:
        reasons.append(f"Down {abs(pnl_pct):.1f}% from cost basis")
        status = "red"
    elif pnl_pct < -5:
        reasons.append(f"Down {abs(pnl_pct):.1f}%")
        status = "yellow"
    else:
        status = "green"

    # Check APY relative to portfolio average
    pos_apy = float(p.current_apy)
    avg = float(avg_apy)
    if avg > 0 and pos_apy < avg * 0.5:
        reasons.append(f"APY ({pos_apy:.0f}%) below average ({avg:.0f}%)")
        status = "yellow" if status == "green" else status

    # Check concentration risk
    if float(weight_pct) > 20:
        reasons.append(f"High concentration ({float(weight_pct):.0f}%)")
        status = "yellow" if status == "green" else status

    reason = "; ".join(reasons) if reasons else None
    return status, reason


async def _get_top_positions(db: AsyncSession, wallet: str, limit: int = 10) -> list[PositionSummary]:
    """Helper to get top positions by TAO value with health scoring."""
    stmt = (
        select(Position)
        .where(Position.wallet_address == wallet)
        .order_by(Position.tao_value_mid.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    positions = result.scalars().all()

    # Calculate total value and average APY for weight/health calculation
    total_value = sum(p.tao_value_mid for p in positions)
    total_weighted_apy = sum(p.tao_value_mid * p.current_apy for p in positions)
    avg_apy = total_weighted_apy / total_value if total_value > 0 else Decimal("0")

    summaries = []
    for p in positions:
        weight_pct = (p.tao_value_mid / total_value * 100) if total_value else Decimal("0")
        health_status, health_reason = _compute_position_health(p, weight_pct, avg_apy)

        summaries.append(PositionSummary(
            netuid=p.netuid,
            subnet_name=p.subnet_name or f"Subnet {p.netuid}",
            tao_value_mid=p.tao_value_mid,
            alpha_balance=p.alpha_balance,
            weight_pct=weight_pct,
            current_apy=p.current_apy,
            daily_yield_tao=p.daily_yield_tao,
            cost_basis_tao=p.cost_basis_tao,
            unrealized_pnl_tao=p.unrealized_pnl_tao,
            unrealized_pnl_pct=p.unrealized_pnl_pct,
            health_status=health_status,
            health_reason=health_reason,
            validator_hotkey=p.validator_hotkey,
            recommended_action=p.recommended_action,
        ))

    return summaries


@router.get("/positions", response_model=list[PositionSummary])
async def get_positions(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[PositionSummary]:
    """Get all positions sorted by TAO value."""
    wallet = settings.wallet_address
    return await _get_top_positions(db, wallet, limit)


@router.get("/yield-history")
async def get_yield_history(
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get actual yield history from stake balance tracking.

    Returns actual realized yield based on balance changes,
    not just estimated yield from APY.
    """
    from app.models.transaction import PositionYieldHistory
    from datetime import timedelta

    wallet = settings.wallet_address
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get yield history records
    stmt = (
        select(PositionYieldHistory)
        .where(
            PositionYieldHistory.wallet_address == wallet,
            PositionYieldHistory.date >= cutoff,
        )
        .order_by(PositionYieldHistory.date.desc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    # Aggregate by date
    daily_yields = {}
    for r in records:
        date_key = r.date.strftime("%Y-%m-%d")
        if date_key not in daily_yields:
            daily_yields[date_key] = {
                "date": date_key,
                "yield_tao": Decimal("0"),
                "positions": 0,
                "avg_apy": Decimal("0"),
            }
        daily_yields[date_key]["yield_tao"] += r.yield_tao
        daily_yields[date_key]["positions"] += 1

    # Calculate totals
    total_yield = sum(r.yield_tao for r in records)
    total_days = len(daily_yields)

    # Get actual yield summary from service
    actual_summary = await data_sync_service.get_actual_yield_summary(days=days)

    return {
        "wallet_address": wallet,
        "days_requested": days,
        "days_with_data": total_days,
        "total_yield_tao": str(total_yield),
        "avg_daily_yield_tao": str(total_yield / Decimal(str(days))) if days > 0 else "0",
        "avg_apy": str(actual_summary.get("avg_apy", Decimal("0"))),
        "daily_breakdown": sorted(daily_yields.values(), key=lambda x: x["date"], reverse=True),
        "records_count": len(records),
    }


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

    # Get all positions for dashboard (no limit)
    top_positions = await _get_top_positions(db, wallet, limit=500)

    # Generate action items based on position health
    action_items = []
    red_count = 0
    yellow_count = 0

    for pos in top_positions:
        if pos.health_status == "red":
            red_count += 1
            if float(pos.unrealized_pnl_pct) < -10:
                action_items.append(ActionItem(
                    priority="high",
                    action_type="cut_loss",
                    title=f"Review {pos.subnet_name} position",
                    description=f"Down {abs(float(pos.unrealized_pnl_pct)):.1f}% from cost basis. Consider reducing exposure.",
                    subnet_id=pos.netuid,
                ))
        elif pos.health_status == "yellow":
            yellow_count += 1

        # Check for take profit opportunities
        if float(pos.unrealized_pnl_pct) > 25:
            action_items.append(ActionItem(
                priority="medium",
                action_type="take_profit",
                title=f"Consider taking profit on {pos.subnet_name}",
                description=f"Up {float(pos.unrealized_pnl_pct):.1f}% - you could lock in {float(pos.unrealized_pnl_tao):.2f} TAO profit.",
                subnet_id=pos.netuid,
                potential_gain_tao=pos.unrealized_pnl_tao,
            ))

        # Check for concentration risk
        if float(pos.weight_pct) > 20:
            action_items.append(ActionItem(
                priority="medium",
                action_type="rebalance",
                title=f"High concentration in {pos.subnet_name}",
                description=f"{float(pos.weight_pct):.1f}% of portfolio. Consider diversifying to reduce risk.",
                subnet_id=pos.netuid,
            ))

    # Compute portfolio health
    if red_count > 0:
        health_status = "red"
        health_score = max(0, 100 - red_count * 20 - yellow_count * 5)
        top_issue = f"{red_count} position(s) need immediate attention"
    elif yellow_count > 2:
        health_status = "yellow"
        health_score = max(50, 100 - yellow_count * 10)
        top_issue = f"{yellow_count} positions need review"
    else:
        health_status = "green"
        health_score = min(100, 100 - yellow_count * 5)
        top_issue = None

    portfolio_health = PortfolioHealth(
        status=health_status,
        score=health_score,
        top_issue=top_issue,
        issues_count=red_count + yellow_count,
    )

    # Sort action items by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    action_items.sort(key=lambda x: priority_order.get(x.priority, 99))

    return DashboardResponse(
        portfolio=portfolio,
        portfolio_health=portfolio_health,
        top_positions=top_positions,
        action_items=action_items[:5],  # Top 5 action items
        alerts=alerts,
        pending_recommendations=pending_count,
        urgent_recommendations=urgent_count,
        last_sync=data_sync_service.last_sync,
        data_stale=data_sync_service.is_data_stale(),
        generated_at=now,
    )
