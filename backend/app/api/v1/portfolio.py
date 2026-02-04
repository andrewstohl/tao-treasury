"""Portfolio endpoints."""

import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.portfolio import PortfolioSnapshot, NAVHistory
from app.models.position import Position
from app.models.transaction import PositionYieldHistory
from app.models.subnet import Subnet
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
    MarketPulse,
    # Phase 1 – Overview
    PortfolioOverviewResponse,
    RollingReturn,
    TaoPriceContext,
    DualCurrencyValue,
    OverviewPnL,
    OverviewYield,
    CompoundingProjection,
    # Phase 2 – Attribution
    AttributionResponse,
    WaterfallStep,
    PositionContribution,
    IncomeStatement,
    # Phase 3 – Scenario Analysis
    ScenarioResponse,
    SensitivityPoint,
    StressScenario,
    AllocationExposure,
    RiskExposure,
    # Phase 4 – Risk Metrics
    RiskMetricsResponse,
    DailyReturnPoint,
    BenchmarkComparison,
)
from app.services.data.data_sync import data_sync_service
from app.services.data.taostats_client import taostats_client, TaoStatsError
from app.services.data.coingecko_client import fetch_tao_price as cg_fetch_tao_price
from app.services.analysis.attribution import get_attribution_service
from app.services.analysis.scenario import get_scenario_service
from app.services.analysis.risk_metrics import get_risk_metrics_service

logger = structlog.get_logger()

router = APIRouter()


@router.get("", response_model=PortfolioSummary)
async def get_portfolio(db: AsyncSession = Depends(get_db)) -> PortfolioSummary:
    """Get current portfolio summary."""
    settings = get_settings()
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
    settings = get_settings()
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


async def _get_top_positions(db: AsyncSession, wallet: str, limit: int = 10) -> list[PositionSummary]:
    """Helper to get top positions by TAO value."""
    stmt = (
        select(Position)
        .where(Position.wallet_address == wallet)
        .order_by(Position.tao_value_mid.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    positions = result.scalars().all()

    # Batch-load subnets for flow_regime and emission_share
    netuids = [p.netuid for p in positions]
    subnet_lookup: Dict[int, Subnet] = {}
    if netuids:
        subnet_stmt = select(Subnet).where(Subnet.netuid.in_(netuids))
        subnet_result = await db.execute(subnet_stmt)
        for s in subnet_result.scalars().all():
            subnet_lookup[s.netuid] = s

    total_value = sum(p.tao_value_mid for p in positions)

    summaries = []
    for p in positions:
        weight_pct = (p.tao_value_mid / total_value * 100) if total_value else Decimal("0")
        subnet = subnet_lookup.get(p.netuid)

        summaries.append(PositionSummary(
            netuid=p.netuid,
            subnet_name=p.subnet_name or f"Subnet {p.netuid}",
            tao_value_mid=p.tao_value_mid,
            tao_value_exec_50pct=p.tao_value_exec_50pct,
            tao_value_exec_100pct=p.tao_value_exec_100pct,
            alpha_balance=p.alpha_balance,
            weight_pct=weight_pct,
            entry_price_tao=p.entry_price_tao,
            entry_date=p.entry_date,
            current_apy=p.current_apy,
            daily_yield_tao=p.daily_yield_tao,
            cost_basis_tao=p.cost_basis_tao,
            realized_pnl_tao=p.realized_pnl_tao,
            unrealized_pnl_tao=p.unrealized_pnl_tao,
            unrealized_pnl_pct=p.unrealized_pnl_pct,
            exit_slippage_50pct=p.exit_slippage_50pct,
            exit_slippage_100pct=p.exit_slippage_100pct,
            validator_hotkey=p.validator_hotkey,
            recommended_action=p.recommended_action,
            action_reason=p.action_reason,
            flow_regime=subnet.flow_regime if subnet else None,
            emission_share=subnet.emission_share if subnet else None,
        ))

    return summaries


@router.get("/positions", response_model=list[PositionSummary])
async def get_positions(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[PositionSummary]:
    """Get all positions sorted by TAO value."""
    settings = get_settings()
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

    settings = get_settings()
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


async def _compute_market_pulse(
    positions: List[PositionSummary],
) -> Optional[MarketPulse]:
    """Compute aggregated market pulse from TaoStats pool data.

    Filters to only held netuids and computes portfolio-weighted averages.
    Returns None if no positions or TaoStats unavailable.
    """
    if not positions:
        return MarketPulse(taostats_available=False)

    try:
        pool_response = await taostats_client.get_pools_full()
        pools_data = pool_response.get("data", [])
    except (TaoStatsError, Exception) as e:
        logger.warning("TaoStats unavailable for market pulse", error=str(e))
        return MarketPulse(taostats_available=False)

    # Build lookup by netuid
    pool_lookup: Dict[int, dict] = {}
    for pool in pools_data:
        netuid = pool.get("netuid")
        if netuid is not None:
            pool_lookup[int(netuid)] = pool

    # Get held netuids and their values
    held_netuids = {p.netuid for p in positions}
    total_value = sum(float(p.tao_value_mid) for p in positions)
    if total_value <= 0:
        return MarketPulse(taostats_available=True)

    # Compute weighted averages
    weighted_24h_change = 0.0
    weighted_7d_change = 0.0
    weighted_sentiment = 0.0
    total_volume = 0.0
    total_buy_volume = 0.0
    total_sell_volume = 0.0
    sentiment_weight_total = 0.0
    top_mover_netuid = None
    top_mover_name = None
    top_mover_change = 0.0

    RAO_DIVISOR = 1e9

    for pos in positions:
        pool = pool_lookup.get(pos.netuid)
        if not pool:
            continue

        pos_value = float(pos.tao_value_mid)
        weight = pos_value / total_value if total_value > 0 else 0

        # Price changes (TaoStats uses _1_day, _1_week naming)
        change_24h = pool.get("price_change_1_day")
        if change_24h is not None:
            try:
                change_24h = float(change_24h)
                weighted_24h_change += weight * change_24h
                # Track top mover
                if abs(change_24h) > abs(top_mover_change):
                    top_mover_change = change_24h
                    top_mover_netuid = pos.netuid
                    top_mover_name = pos.subnet_name
            except (ValueError, TypeError):
                pass

        change_7d = pool.get("price_change_1_week")
        if change_7d is not None:
            try:
                weighted_7d_change += weight * float(change_7d)
            except (ValueError, TypeError):
                pass

        # Sentiment (TaoStats uses fear_and_greed_index)
        fg_index = pool.get("fear_and_greed_index")
        if fg_index is not None:
            try:
                weighted_sentiment += weight * float(fg_index)
                sentiment_weight_total += weight
            except (ValueError, TypeError):
                pass

        # Volume (TaoStats uses _24_hr suffix, values in rao)
        vol_24h = pool.get("tao_volume_24_hr")
        if vol_24h is not None:
            try:
                total_volume += float(vol_24h) / RAO_DIVISOR
            except (ValueError, TypeError):
                pass

        buy_vol = pool.get("tao_buy_volume_24_hr")
        if buy_vol is not None:
            try:
                total_buy_volume += float(buy_vol) / RAO_DIVISOR
            except (ValueError, TypeError):
                pass

        sell_vol = pool.get("tao_sell_volume_24_hr")
        if sell_vol is not None:
            try:
                total_sell_volume += float(sell_vol) / RAO_DIVISOR
            except (ValueError, TypeError):
                pass

    # Determine sentiment label
    avg_sentiment = weighted_sentiment / sentiment_weight_total if sentiment_weight_total > 0 else None
    sentiment_label = None
    if avg_sentiment is not None:
        if avg_sentiment >= 75:
            sentiment_label = "Extreme Greed"
        elif avg_sentiment >= 55:
            sentiment_label = "Greed"
        elif avg_sentiment >= 45:
            sentiment_label = "Neutral"
        elif avg_sentiment >= 25:
            sentiment_label = "Fear"
        else:
            sentiment_label = "Extreme Fear"

    # Net buy pressure
    net_buy_pressure = None
    if total_volume > 0:
        net_buy_pressure = Decimal(str(
            round((total_buy_volume - total_sell_volume) / total_volume * 100, 2)
        ))

    return MarketPulse(
        portfolio_24h_change_pct=Decimal(str(round(weighted_24h_change, 4))),
        portfolio_7d_change_pct=Decimal(str(round(weighted_7d_change, 4))),
        avg_sentiment_index=Decimal(str(round(avg_sentiment, 1))) if avg_sentiment is not None else None,
        avg_sentiment_label=sentiment_label,
        total_volume_24h_tao=Decimal(str(round(total_volume, 4))) if total_volume > 0 else None,
        net_buy_pressure_pct=net_buy_pressure,
        top_mover_netuid=top_mover_netuid,
        top_mover_name=top_mover_name,
        top_mover_change_24h=Decimal(str(round(top_mover_change, 4))) if top_mover_netuid else None,
        taostats_available=True,
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> DashboardResponse:
    """Get complete dashboard data."""
    settings = get_settings()
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

    # Compute market pulse from TaoStats pool data
    market_pulse = await _compute_market_pulse(top_positions)

    return DashboardResponse(
        portfolio=portfolio,
        top_positions=top_positions,
        action_items=[],
        alerts=alerts,
        market_pulse=market_pulse,
        pending_recommendations=pending_count,
        urgent_recommendations=urgent_count,
        last_sync=data_sync_service.last_sync,
        data_stale=data_sync_service.is_data_stale(),
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# Phase 1 – Portfolio Overview
# ---------------------------------------------------------------------------

_ROLLING_PERIODS = [
    ("1d", 1),
    ("7d", 7),
    ("30d", 30),
    ("90d", 90),
]


async def _compute_rolling_returns(
    db: AsyncSession,
    wallet: str,
    nav_field_close: str,  # "nav_mid_close" or "nav_exec_close"
) -> list[RollingReturn]:
    """Compute rolling returns from NAVHistory for a given NAV variant.

    Returns a list of RollingReturn objects for 1d/7d/30d/90d/inception.
    """
    now = datetime.now(timezone.utc)

    # Fetch last 90 days of history (covers all rolling windows)
    stmt = (
        select(NAVHistory)
        .where(NAVHistory.wallet_address == wallet)
        .order_by(NAVHistory.date.desc())
        .limit(365)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    if not records:
        return [
            RollingReturn(period=p, data_points=0)
            for p, _ in _ROLLING_PERIODS
        ] + [RollingReturn(period="inception", data_points=0)]

    # records are newest-first; build date->nav lookup
    nav_by_date: dict[datetime, Decimal] = {}
    for r in records:
        nav_by_date[r.date.date() if hasattr(r.date, "date") else r.date] = getattr(r, nav_field_close)

    latest_record = records[0]
    latest_nav = getattr(latest_record, nav_field_close)
    oldest_record = records[-1]

    returns: list[RollingReturn] = []

    for period_label, days_back in _ROLLING_PERIODS:
        target_date = (now - timedelta(days=days_back)).date()

        # Find the closest record on or before the target date
        best_nav: Optional[Decimal] = None
        best_dist = 999
        for d, nav in nav_by_date.items():
            d_date = d if not isinstance(d, datetime) else d.date()
            dist = abs((d_date - target_date).days)
            if dist < best_dist:
                best_dist = dist
                best_nav = nav

        if best_nav and best_nav > 0:
            return_tao = latest_nav - best_nav
            return_pct = (return_tao / best_nav) * 100
            returns.append(RollingReturn(
                period=period_label,
                return_pct=return_pct.quantize(Decimal("0.01")),
                return_tao=return_tao.quantize(Decimal("0.000000001")),
                nav_start=best_nav,
                nav_end=latest_nav,
                data_points=len(records),
            ))
        else:
            returns.append(RollingReturn(period=period_label, data_points=len(records)))

    # Inception return (oldest record to latest)
    oldest_nav = getattr(oldest_record, nav_field_close)
    if oldest_nav and oldest_nav > 0:
        return_tao = latest_nav - oldest_nav
        return_pct = (return_tao / oldest_nav) * 100
        returns.append(RollingReturn(
            period="inception",
            return_pct=return_pct.quantize(Decimal("0.01")),
            return_tao=return_tao.quantize(Decimal("0.000000001")),
            nav_start=oldest_nav,
            nav_end=latest_nav,
            data_points=len(records),
        ))
    else:
        returns.append(RollingReturn(period="inception", data_points=len(records)))

    return returns


def _compute_compounding(
    nav_tao: Decimal,
    apy: Decimal,
    daily_yield_tao: Decimal,
) -> CompoundingProjection:
    """Compute forward yield projections with continuous compounding."""
    nav_f = float(nav_tao) if nav_tao else 0.0
    apy_f = float(apy) if apy else 0.0
    daily_f = float(daily_yield_tao) if daily_yield_tao else 0.0

    if nav_f <= 0 or apy_f <= 0:
        return CompoundingProjection(
            current_nav_tao=nav_tao,
            current_apy=apy,
        )

    # Simple (linear) projection: daily_yield * days
    simple_30 = daily_f * 30
    simple_90 = daily_f * 90
    simple_365 = daily_f * 365

    # Continuous compounding: NAV * (e^(r*t) - 1)
    # where r = ln(1 + APY/100) is the continuously compounded rate
    r = math.log(1 + apy_f / 100)
    comp_30 = nav_f * (math.exp(r * 30 / 365) - 1)
    comp_90 = nav_f * (math.exp(r * 90 / 365) - 1)
    comp_365 = nav_f * (math.exp(r) - 1)

    return CompoundingProjection(
        current_nav_tao=nav_tao,
        current_apy=apy,
        projected_30d_tao=Decimal(str(round(simple_30, 9))),
        projected_90d_tao=Decimal(str(round(simple_90, 9))),
        projected_365d_tao=Decimal(str(round(simple_365, 9))),
        compounded_30d_tao=Decimal(str(round(comp_30, 9))),
        compounded_90d_tao=Decimal(str(round(comp_90, 9))),
        compounded_365d_tao=Decimal(str(round(comp_365, 9))),
        projected_nav_365d_tao=Decimal(str(round(nav_f + comp_365, 9))),
    )


async def _get_tao_price_context() -> TaoPriceContext:
    """Fetch TAO spot price and recent changes.

    Primary source: CoinGecko (returns price + 24h/7d changes in one call).
    Fallback: TaoStats price endpoint.
    """
    # 1. Try CoinGecko first — gives price + changes in a single call
    try:
        cg = await cg_fetch_tao_price()
        if cg is not None and cg.price_usd > 0:
            return TaoPriceContext(
                price_usd=cg.price_usd,
                change_24h_pct=cg.change_24h_pct,
                change_7d_pct=cg.change_7d_pct,
            )
    except Exception as e:
        logger.warning("CoinGecko price fetch failed, trying TaoStats", error=str(e))

    # 2. Fallback to TaoStats
    try:
        price_data = await taostats_client.get_tao_price()
        # TaoStats wraps response in {"data": [{"price": ...}]}
        price_info = price_data.get("data", [{}])[0] if price_data.get("data") else {}
        price_usd = Decimal(str(price_info.get("price", 0) or 0))

        if price_usd <= 0:
            logger.warning("TaoStats returned zero/negative price")
            return TaoPriceContext()

        return TaoPriceContext(price_usd=price_usd)
    except (TaoStatsError, Exception) as e:
        logger.warning("Failed to fetch TAO price from all sources", error=str(e))
        return TaoPriceContext()


@router.get("/overview", response_model=PortfolioOverviewResponse)
async def get_portfolio_overview(
    db: AsyncSession = Depends(get_db),
) -> PortfolioOverviewResponse:
    """Enhanced portfolio overview with dual-currency metrics, rolling returns,
    and compounding projections.
    """
    settings = get_settings()
    wallet = settings.wallet_address
    now = datetime.now(timezone.utc)

    # 1. Get latest portfolio snapshot for current values
    snap_stmt = (
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.wallet_address == wallet)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(1)
    )
    snap_result = await db.execute(snap_stmt)
    snapshot = snap_result.scalar_one_or_none()

    if snapshot is None:
        return PortfolioOverviewResponse(as_of=now)

    # 2. Fetch TAO price context (spot + changes) concurrently with rolling returns
    tao_price_ctx = await _get_tao_price_context()
    tao_usd = float(tao_price_ctx.price_usd) if tao_price_ctx.price_usd else 0.0

    # 3. Compute rolling returns for both mid and exec NAV
    returns_mid = await _compute_rolling_returns(db, wallet, "nav_mid_close")
    returns_exec = await _compute_rolling_returns(db, wallet, "nav_exec_close")

    # 4. Build dual-currency NAV
    nav_mid_tao = snapshot.nav_mid or Decimal("0")
    nav_exec_tao = snapshot.nav_exec_100pct or Decimal("0")

    nav_mid = DualCurrencyValue(
        tao=nav_mid_tao,
        usd=Decimal(str(round(float(nav_mid_tao) * tao_usd, 2))),
    )
    nav_exec = DualCurrencyValue(
        tao=nav_exec_tao,
        usd=Decimal(str(round(float(nav_exec_tao) * tao_usd, 2))),
    )

    # 5. Build dual-currency P&L
    unrealized_tao = snapshot.total_unrealized_pnl_tao or Decimal("0")
    realized_tao = snapshot.total_realized_pnl_tao or Decimal("0")
    total_pnl_tao = unrealized_tao + realized_tao
    cost_basis_tao = snapshot.total_cost_basis_tao or Decimal("0")
    total_pnl_pct = (
        (total_pnl_tao / cost_basis_tao * 100) if cost_basis_tao else Decimal("0")
    )

    pnl = OverviewPnL(
        unrealized=DualCurrencyValue(
            tao=unrealized_tao,
            usd=Decimal(str(round(float(unrealized_tao) * tao_usd, 2))),
        ),
        realized=DualCurrencyValue(
            tao=realized_tao,
            usd=Decimal(str(round(float(realized_tao) * tao_usd, 2))),
        ),
        total=DualCurrencyValue(
            tao=total_pnl_tao,
            usd=Decimal(str(round(float(total_pnl_tao) * tao_usd, 2))),
        ),
        cost_basis=DualCurrencyValue(
            tao=cost_basis_tao,
            usd=Decimal(str(round(float(cost_basis_tao) * tao_usd, 2))),
        ),
        total_pnl_pct=total_pnl_pct.quantize(Decimal("0.01")) if isinstance(total_pnl_pct, Decimal) else Decimal("0"),
    )

    # 6. Build dual-currency yield
    daily_yield = snapshot.daily_yield_tao or Decimal("0")
    weekly_yield = snapshot.weekly_yield_tao or Decimal("0")
    monthly_yield = snapshot.monthly_yield_tao or Decimal("0")
    annualized_yield = daily_yield * 365
    portfolio_apy = snapshot.portfolio_apy or Decimal("0")

    # 6a. Compute cumulative yield from emission alpha (not PositionYieldHistory).
    #
    #     For each open position we know:
    #       - alpha_balance:     total alpha tokens currently held
    #       - cost_basis_tao:    TAO invested in remaining FIFO lots
    #       - entry_price_tao:   weighted-avg TAO-per-alpha at purchase
    #
    #     alpha_purchased  = cost_basis_tao / entry_price_tao
    #     emission_alpha   = alpha_balance - alpha_purchased
    #     yield_gain       = emission_alpha × current_alpha_price
    #
    #     This cleanly separates "income from emissions" from "alpha repricing".
    pos_stmt = select(Position).where(Position.wallet_address == wallet)
    pos_result = await db.execute(pos_stmt)
    open_positions = pos_result.scalars().all()

    cumulative_yield_tao = Decimal("0")
    for pos in open_positions:
        if (
            pos.entry_price_tao
            and pos.entry_price_tao > 0
            and pos.alpha_balance
            and pos.alpha_balance > 0
            and pos.cost_basis_tao is not None
        ):
            alpha_purchased = pos.cost_basis_tao / pos.entry_price_tao
            emission_alpha = pos.alpha_balance - alpha_purchased
            if emission_alpha > 0:
                current_alpha_price = pos.tao_value_mid / pos.alpha_balance
                cumulative_yield_tao += emission_alpha * current_alpha_price

    yield_income = OverviewYield(
        daily=DualCurrencyValue(
            tao=daily_yield,
            usd=Decimal(str(round(float(daily_yield) * tao_usd, 2))),
        ),
        weekly=DualCurrencyValue(
            tao=weekly_yield,
            usd=Decimal(str(round(float(weekly_yield) * tao_usd, 2))),
        ),
        monthly=DualCurrencyValue(
            tao=monthly_yield,
            usd=Decimal(str(round(float(monthly_yield) * tao_usd, 2))),
        ),
        annualized=DualCurrencyValue(
            tao=annualized_yield,
            usd=Decimal(str(round(float(annualized_yield) * tao_usd, 2))),
        ),
        portfolio_apy=portfolio_apy,
        cumulative_tao=cumulative_yield_tao,
        yield_1d_tao=daily_yield,
        yield_7d_tao=weekly_yield,
        yield_30d_tao=monthly_yield,
    )

    # 7. Compounding projection
    compounding = _compute_compounding(nav_mid_tao, portfolio_apy, daily_yield)

    # 8. ATH and drawdown
    ath_stmt = (
        select(func.max(NAVHistory.nav_exec_ath))
        .where(NAVHistory.wallet_address == wallet)
    )
    ath_result = await db.execute(ath_stmt)
    nav_ath = ath_result.scalar() or Decimal("0")
    drawdown_pct = (
        ((nav_ath - nav_exec_tao) / nav_ath * 100) if nav_ath > 0 else Decimal("0")
    )

    # 9. Position count
    pos_count = snapshot.active_positions or 0
    eligible = snapshot.eligible_subnets or 0

    return PortfolioOverviewResponse(
        nav_mid=nav_mid,
        nav_exec=nav_exec,
        tao_price=tao_price_ctx,
        returns_mid=returns_mid,
        returns_exec=returns_exec,
        pnl=pnl,
        yield_income=yield_income,
        compounding=compounding,
        nav_ath_tao=nav_ath,
        drawdown_from_ath_pct=drawdown_pct.quantize(Decimal("0.01")) if isinstance(drawdown_pct, Decimal) else Decimal("0"),
        active_positions=pos_count,
        eligible_subnets=eligible,
        overall_regime=snapshot.overall_regime or "neutral",
        as_of=snapshot.timestamp,
    )


# ---------------------------------------------------------------------------
# Phase 2 – Performance Attribution
# ---------------------------------------------------------------------------

@router.get("/attribution", response_model=AttributionResponse)
async def get_attribution(
    days: int = Query(default=7, ge=1, le=90),
) -> AttributionResponse:
    """Decompose portfolio returns into yield, price, and fee components.

    Returns a waterfall breakdown, per-position contributions, and
    a period income statement.
    """
    svc = get_attribution_service()
    try:
        result = await svc.compute_attribution(days=days)
    except Exception:
        logger.exception("Attribution computation failed", days=days)
        now = datetime.now(timezone.utc)
        return AttributionResponse(
            period_days=days, start=now - timedelta(days=days), end=now,
            nav_start_tao=Decimal("0"), nav_end_tao=Decimal("0"),
            total_return_tao=Decimal("0"), total_return_pct=Decimal("0"),
            yield_income_tao=Decimal("0"), yield_income_pct=Decimal("0"),
            price_effect_tao=Decimal("0"), price_effect_pct=Decimal("0"),
            fees_tao=Decimal("0"), fees_pct=Decimal("0"),
            net_flows_tao=Decimal("0"), waterfall=[], position_contributions=[],
            income_statement=IncomeStatement(
                yield_income_tao=Decimal("0"), realized_gains_tao=Decimal("0"),
                fees_tao=Decimal("0"), net_income_tao=Decimal("0"),
            ),
        )

    return AttributionResponse(
        period_days=result["period_days"],
        start=datetime.fromisoformat(result["start"]),
        end=datetime.fromisoformat(result["end"]),
        nav_start_tao=Decimal(result["nav_start_tao"]),
        nav_end_tao=Decimal(result["nav_end_tao"]),
        total_return_tao=Decimal(result["total_return_tao"]),
        total_return_pct=Decimal(result["total_return_pct"]),
        yield_income_tao=Decimal(result["yield_income_tao"]),
        yield_income_pct=Decimal(result["yield_income_pct"]),
        price_effect_tao=Decimal(result["price_effect_tao"]),
        price_effect_pct=Decimal(result["price_effect_pct"]),
        fees_tao=Decimal(result["fees_tao"]),
        fees_pct=Decimal(result["fees_pct"]),
        net_flows_tao=Decimal(result["net_flows_tao"]),
        waterfall=[
            WaterfallStep(
                label=w["label"],
                value_tao=Decimal(w["value_tao"]),
                is_total=w["is_total"],
            )
            for w in result["waterfall"]
        ],
        position_contributions=[
            PositionContribution(
                netuid=pc["netuid"],
                subnet_name=pc["subnet_name"],
                start_value_tao=Decimal(pc["start_value_tao"]),
                return_tao=Decimal(pc["return_tao"]),
                return_pct=Decimal(pc["return_pct"]),
                yield_tao=Decimal(pc["yield_tao"]),
                price_effect_tao=Decimal(pc["price_effect_tao"]),
                weight_pct=Decimal(pc["weight_pct"]),
                contribution_pct=Decimal(pc["contribution_pct"]),
            )
            for pc in result["position_contributions"]
        ],
        income_statement=IncomeStatement(
            yield_income_tao=Decimal(result["income_statement"]["yield_income_tao"]),
            realized_gains_tao=Decimal(result["income_statement"]["realized_gains_tao"]),
            fees_tao=Decimal(result["income_statement"]["fees_tao"]),
            net_income_tao=Decimal(result["income_statement"]["net_income_tao"]),
        ),
    )


# ---------------------------------------------------------------------------
# Phase 3 – TAO Price Sensitivity & Scenario Analysis
# ---------------------------------------------------------------------------

@router.get("/scenarios", response_model=ScenarioResponse)
async def get_scenarios() -> ScenarioResponse:
    """TAO price sensitivity table, stress scenarios, and risk exposure.

    Computes portfolio USD value at various TAO price shocks (±10/20/50%),
    runs pre-built stress scenarios (crash, contagion, pump, rotation),
    and reports portfolio risk exposure including exit slippage.
    """
    svc = get_scenario_service()
    try:
        result = await svc.compute_scenarios()
    except Exception:
        logger.exception("Scenario computation failed")
        result = svc._empty_result()

    return ScenarioResponse(
        current_tao_price_usd=Decimal(str(result["current_tao_price_usd"])),
        nav_tao=Decimal(str(result["nav_tao"])),
        nav_usd=Decimal(str(result["nav_usd"])),
        allocation=AllocationExposure(
            root_tao=Decimal(str(result["allocation"]["root_tao"])),
            root_pct=Decimal(str(result["allocation"]["root_pct"])),
            dtao_tao=Decimal(str(result["allocation"]["dtao_tao"])),
            dtao_pct=Decimal(str(result["allocation"]["dtao_pct"])),
            unstaked_tao=Decimal(str(result["allocation"]["unstaked_tao"])),
        ),
        sensitivity=[
            SensitivityPoint(
                shock_pct=s["shock_pct"],
                tao_price_usd=Decimal(str(s["tao_price_usd"])),
                nav_tao=Decimal(str(s["nav_tao"])),
                nav_usd=Decimal(str(s["nav_usd"])),
                usd_change=Decimal(str(s["usd_change"])),
                usd_change_pct=Decimal(str(s["usd_change_pct"])),
            )
            for s in result["sensitivity"]
        ],
        scenarios=[
            StressScenario(
                id=sc["id"],
                name=sc["name"],
                description=sc["description"],
                tao_price_change_pct=sc["tao_price_change_pct"],
                alpha_impact_pct=sc["alpha_impact_pct"],
                new_tao_price_usd=Decimal(str(sc["new_tao_price_usd"])),
                nav_tao=Decimal(str(sc["nav_tao"])),
                nav_usd=Decimal(str(sc["nav_usd"])),
                tao_impact=Decimal(str(sc["tao_impact"])),
                usd_impact=Decimal(str(sc["usd_impact"])),
                usd_impact_pct=Decimal(str(sc["usd_impact_pct"])),
            )
            for sc in result["scenarios"]
        ],
        risk_exposure=RiskExposure(
            tao_beta=Decimal(str(result["risk_exposure"]["tao_beta"])),
            dtao_weight_pct=Decimal(str(result["risk_exposure"]["dtao_weight_pct"])),
            root_weight_pct=Decimal(str(result["risk_exposure"]["root_weight_pct"])),
            total_exit_slippage_pct=Decimal(str(result["risk_exposure"]["total_exit_slippage_pct"])),
            total_exit_slippage_tao=Decimal(str(result["risk_exposure"]["total_exit_slippage_tao"])),
            note=result["risk_exposure"]["note"],
        ),
    )


# ---------------------------------------------------------------------------
# Phase 4 – Risk-Adjusted Returns & Benchmarking
# ---------------------------------------------------------------------------

@router.get("/risk-metrics", response_model=RiskMetricsResponse)
async def get_risk_metrics(
    days: int = Query(default=90, ge=7, le=365),
) -> RiskMetricsResponse:
    """Risk-adjusted return metrics with benchmark comparisons.

    Computes Sharpe ratio, Sortino ratio, Calmar ratio, annualized
    volatility, max drawdown, and win rate from daily NAV returns.
    Uses Root (SN0) validator APY as the risk-free rate.

    Benchmarks: Root-only staking, Hold TAO, and High-emission top 3.
    """
    svc = get_risk_metrics_service()
    try:
        result = await svc.compute_risk_metrics(days=days)
    except Exception:
        logger.exception("Risk metrics computation failed", days=days)
        result = svc._empty_result(days)

    return RiskMetricsResponse(
        period_days=result["period_days"],
        start=result["start"],
        end=result["end"],
        annualized_return_pct=Decimal(str(result["annualized_return_pct"])),
        annualized_volatility_pct=Decimal(str(result["annualized_volatility_pct"])),
        downside_deviation_pct=Decimal(str(result["downside_deviation_pct"])),
        sharpe_ratio=Decimal(str(result["sharpe_ratio"])),
        sortino_ratio=Decimal(str(result["sortino_ratio"])),
        calmar_ratio=Decimal(str(result["calmar_ratio"])),
        max_drawdown_pct=Decimal(str(result["max_drawdown_pct"])),
        max_drawdown_tao=Decimal(str(result["max_drawdown_tao"])),
        risk_free_rate_pct=Decimal(str(result["risk_free_rate_pct"])),
        risk_free_source=result["risk_free_source"],
        win_rate_pct=Decimal(str(result["win_rate_pct"])),
        best_day_pct=Decimal(str(result["best_day_pct"])),
        worst_day_pct=Decimal(str(result["worst_day_pct"])),
        benchmarks=[
            BenchmarkComparison(
                id=b["id"],
                name=b["name"],
                description=b["description"],
                annualized_return_pct=Decimal(str(b["annualized_return_pct"])),
                annualized_volatility_pct=Decimal(str(b["annualized_volatility_pct"])) if b.get("annualized_volatility_pct") is not None else None,
                sharpe_ratio=Decimal(str(b["sharpe_ratio"])) if b.get("sharpe_ratio") is not None else None,
                alpha_pct=Decimal(str(b["alpha_pct"])),
            )
            for b in result["benchmarks"]
        ],
        daily_returns=[
            DailyReturnPoint(
                date=d["date"],
                return_pct=Decimal(str(d["return_pct"])),
                nav_tao=Decimal(str(d["nav_tao"])),
            )
            for d in result["daily_returns"]
        ],
    )

