"""Portfolio endpoints."""

import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.portfolio import PortfolioSnapshot, NAVHistory
from app.models.position import Position
from app.models.wallet import Wallet
from app.models.transaction import PositionCostBasis, PositionYieldHistory
from app.models.subnet import Subnet
from app.models.validator import Validator
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
    ClosedPositionSummary,
    MarketPulse,
    # Phase 1 – Overview
    PortfolioOverviewResponse,
    RollingReturn,
    TaoPriceContext,
    DualCurrencyValue,
    ConversionExposure,
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


async def _get_active_wallets(db: AsyncSession) -> List[str]:
    """Get list of active wallet addresses from database."""
    stmt = select(Wallet.address).where(Wallet.is_active == True).order_by(Wallet.created_at)  # noqa: E712
    result = await db.execute(stmt)
    return [row[0] for row in result.fetchall()]


async def _resolve_wallet(db: AsyncSession, wallet: Optional[str] = None) -> Optional[str]:
    """Resolve which wallet to use.

    Returns None for "all wallets" aggregate mode (wallet not specified or "all").
    Returns specific wallet address when a valid address is provided.
    Returns None if no wallets configured.
    """
    if wallet and wallet != "all":
        return wallet
    # No wallet or "all" → aggregate mode (None signals callers to query all)
    return None


@router.get("", response_model=PortfolioSummary)
async def get_portfolio(
    wallet: Optional[str] = Query(default=None, description="Wallet address to query. If not provided, uses first active wallet."),
    db: AsyncSession = Depends(get_db),
) -> PortfolioSummary:
    """Get current portfolio summary."""
    wallet = await _resolve_wallet(db, wallet)
    all_wallets = await _get_active_wallets(db)
    if not all_wallets:
        # Return empty summary if no wallets configured
        return PortfolioSummary(
            wallet_address="",
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
    # Aggregate mode or specific wallet
    target_wallets = [wallet] if wallet else all_wallets
    return await _build_aggregate_portfolio(db, target_wallets, datetime.now(timezone.utc))


@router.get("/history", response_model=PortfolioHistoryResponse)
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365),
    wallet: Optional[str] = Query(default=None, description="Wallet address to query"),
    db: AsyncSession = Depends(get_db),
) -> PortfolioHistoryResponse:
    """Get portfolio NAV history."""
    wallet = await _resolve_wallet(db, wallet)
    if not wallet:
        return PortfolioHistoryResponse(
            wallet_address="",
            history=[],
            total_days=0,
            cumulative_return_pct=Decimal("0"),
            max_drawdown_pct=Decimal("0"),
        )

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


async def _get_top_positions(db: AsyncSession, wallet: Optional[str] = None, limit: int = 10) -> list[PositionSummary]:
    """Helper to get active positions (alpha_balance > 0) by TAO value.

    When wallet is None, returns positions from all active wallets only.
    Positions from deactivated wallets are excluded.
    """
    conditions = [Position.alpha_balance > 0]
    if wallet:
        conditions.append(Position.wallet_address == wallet)
    else:
        # Aggregate mode: restrict to active wallets only
        active_wallets = await _get_active_wallets(db)
        if not active_wallets:
            return []
        conditions.append(Position.wallet_address.in_(active_wallets))
    stmt = (
        select(Position)
        .where(*conditions)
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

    # Batch-load validators for name and image display
    validator_lookup: Dict[tuple, Validator] = {}
    if any(p.validator_hotkey for p in positions):
        val_stmt = select(Validator).where(Validator.netuid.in_(netuids))
        val_result = await db.execute(val_stmt)
        for v in val_result.scalars().all():
            validator_lookup[(v.hotkey, v.netuid)] = v

    total_value = sum(p.tao_value_mid for p in positions)

    summaries = []
    for p in positions:
        weight_pct = (p.tao_value_mid / total_value * 100) if total_value else Decimal("0")
        subnet = subnet_lookup.get(p.netuid)

        summaries.append(PositionSummary(
            wallet_address=p.wallet_address,
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
            # Decomposed yield and alpha P&L (pre-computed, single source of truth)
            unrealized_yield_tao=p.unrealized_yield_tao,
            realized_yield_tao=p.realized_yield_tao,
            unrealized_alpha_pnl_tao=p.unrealized_alpha_pnl_tao,
            realized_alpha_pnl_tao=p.realized_alpha_pnl_tao,
            exit_slippage_50pct=p.exit_slippage_50pct,
            exit_slippage_100pct=p.exit_slippage_100pct,
            validator_hotkey=p.validator_hotkey,
            validator_name=validator_lookup[(p.validator_hotkey, p.netuid)].name if p.validator_hotkey and (p.validator_hotkey, p.netuid) in validator_lookup else None,
            validator_image_url=validator_lookup[(p.validator_hotkey, p.netuid)].image_url if p.validator_hotkey and (p.validator_hotkey, p.netuid) in validator_lookup else None,
            recommended_action=p.recommended_action,
            action_reason=p.action_reason,
            flow_regime=subnet.flow_regime if subnet else None,
            emission_share=subnet.emission_share if subnet else None,
        ))

    return summaries


@router.get("/positions", response_model=list[PositionSummary])
async def get_positions(
    limit: int = Query(default=100, ge=1, le=500),
    wallet: Optional[str] = Query(default=None, description="Wallet address to query"),
    db: AsyncSession = Depends(get_db),
) -> list[PositionSummary]:
    """Get all positions sorted by TAO value."""
    wallet = await _resolve_wallet(db, wallet)
    return await _get_top_positions(db, wallet, limit)


@router.get("/yield-history")
async def get_yield_history(
    days: int = Query(default=30, ge=1, le=90),
    wallet: Optional[str] = Query(default=None, description="Wallet address to query"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get actual yield history from stake balance tracking.

    Returns actual realized yield based on balance changes,
    not just estimated yield from APY.
    """
    from app.models.transaction import PositionYieldHistory
    from datetime import timedelta

    wallet = await _resolve_wallet(db, wallet)
    if not wallet:
        return {
            "wallet_address": "",
            "days_requested": days,
            "days_with_data": 0,
            "total_yield_tao": "0",
            "avg_daily_yield_tao": "0",
            "avg_apy": "0",
            "daily_breakdown": [],
            "records_count": 0,
        }
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


async def _build_aggregate_portfolio(
    db: AsyncSession, wallets: List[str], now: datetime
) -> PortfolioSummary:
    """Build an aggregated PortfolioSummary from latest snapshots across wallets.

    Sums NAV, yields, and P&L from the most recent snapshot of each wallet.
    """
    # Get the latest snapshot per wallet using a subquery
    snapshots = []
    for w in wallets:
        snap_stmt = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.wallet_address == w)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        snap_result = await db.execute(snap_stmt)
        snap = snap_result.scalar_one_or_none()
        if snap:
            snapshots.append(snap)

    if not snapshots:
        return PortfolioSummary(
            wallet_address="all" if len(wallets) > 1 else (wallets[0] if wallets else ""),
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
            as_of=now,
        )

    # Sum across all wallet snapshots
    nav_mid = sum(s.nav_mid or Decimal("0") for s in snapshots)
    nav_exec_50 = sum(s.nav_exec_50pct or Decimal("0") for s in snapshots)
    nav_exec_100 = sum(s.nav_exec_100pct or Decimal("0") for s in snapshots)
    tao_price_usd = snapshots[0].tao_price_usd or Decimal("0")  # same for all
    nav_usd = sum(s.nav_usd or Decimal("0") for s in snapshots)

    root_tao = sum(s.root_allocation_tao or Decimal("0") for s in snapshots)
    dtao_tao = sum(s.dtao_allocation_tao or Decimal("0") for s in snapshots)
    unstaked_tao = sum(s.unstaked_buffer_tao or Decimal("0") for s in snapshots)
    total = nav_mid or Decimal("1")

    allocation = AllocationBreakdown(
        root_tao=root_tao,
        root_pct=(root_tao / total * 100) if total else Decimal("0"),
        dtao_tao=dtao_tao,
        dtao_pct=(dtao_tao / total * 100) if total else Decimal("0"),
        unstaked_tao=unstaked_tao,
        unstaked_pct=(unstaked_tao / total * 100) if total else Decimal("0"),
    )

    daily_yield = sum(s.daily_yield_tao or Decimal("0") for s in snapshots)
    weekly_yield = sum(s.weekly_yield_tao or Decimal("0") for s in snapshots)
    monthly_yield = sum(s.monthly_yield_tao or Decimal("0") for s in snapshots)

    # Weighted average APY
    active_value = sum(
        (s.nav_mid or Decimal("0")) - (s.unstaked_buffer_tao or Decimal("0"))
        for s in snapshots
    )
    if active_value > 0:
        weighted_apy = sum(
            ((s.nav_mid or Decimal("0")) - (s.unstaked_buffer_tao or Decimal("0")))
            * (s.portfolio_apy or Decimal("0"))
            for s in snapshots
        ) / active_value
    else:
        weighted_apy = Decimal("0")

    yield_summary = YieldSummary(
        portfolio_apy=weighted_apy,
        daily_yield_tao=daily_yield,
        weekly_yield_tao=weekly_yield,
        monthly_yield_tao=monthly_yield,
    )

    total_unrealized = sum(s.total_unrealized_pnl_tao or Decimal("0") for s in snapshots)
    total_realized = sum(s.total_realized_pnl_tao or Decimal("0") for s in snapshots)
    total_cost = sum(s.total_cost_basis_tao or Decimal("0") for s in snapshots)
    unrealized_pct = (total_unrealized / total_cost * 100) if total_cost else Decimal("0")

    pnl_summary = PnLSummary(
        total_unrealized_pnl_tao=total_unrealized,
        total_realized_pnl_tao=total_realized,
        total_cost_basis_tao=total_cost,
        unrealized_pnl_pct=unrealized_pct,
    )

    active_positions = sum(s.active_positions or 0 for s in snapshots)
    eligible_subnets = max((s.eligible_subnets or 0) for s in snapshots)

    wallet_label = wallets[0] if len(wallets) == 1 else "all"

    return PortfolioSummary(
        wallet_address=wallet_label,
        nav_mid=nav_mid,
        nav_exec_50pct=nav_exec_50,
        nav_exec_100pct=nav_exec_100,
        tao_price_usd=tao_price_usd,
        nav_usd=nav_usd,
        allocation=allocation,
        yield_summary=yield_summary,
        pnl_summary=pnl_summary,
        executable_drawdown_pct=Decimal("0"),
        drawdown_from_ath_pct=Decimal("0"),
        nav_ath=Decimal("0"),
        active_positions=active_positions,
        eligible_subnets=eligible_subnets,
        overall_regime=snapshots[0].overall_regime or "neutral",
        daily_turnover_pct=Decimal("0"),
        weekly_turnover_pct=Decimal("0"),
        as_of=max(s.timestamp for s in snapshots),
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    wallet: Optional[str] = Query(default=None, description="Wallet address to query"),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Get complete dashboard data.

    When wallet is not specified or "all", aggregates across all active wallets.
    When a specific wallet is provided, filters to that wallet only.
    """
    now = datetime.now(timezone.utc)
    wallet = await _resolve_wallet(db, wallet)

    # Get all active wallets for the response
    all_wallets = await _get_active_wallets(db)

    # Handle case when no wallets are configured at all
    if not all_wallets:
        empty_portfolio = PortfolioSummary(
            wallet_address="",
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
            as_of=now,
        )
        return DashboardResponse(
            portfolio=empty_portfolio,
            wallets=all_wallets,
            top_positions=[],
            closed_positions=[],
            free_tao_balance=Decimal("0"),
            action_items=[],
            alerts=AlertSummary(critical=0, warning=0, info=0),
            market_pulse=None,
            pending_recommendations=0,
            urgent_recommendations=0,
            last_sync=data_sync_service.last_sync,
            data_stale=data_sync_service.is_data_stale(),
            generated_at=now,
        )

    # Build portfolio summary — aggregate across target wallets
    target_wallets = [wallet] if wallet else all_wallets
    portfolio = await _build_aggregate_portfolio(db, target_wallets, now)

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

    # Count pending recommendations (across target wallets)
    rec_conditions = [TradeRecommendation.status == "pending"]
    if wallet:
        rec_conditions.append(TradeRecommendation.wallet_address == wallet)
    else:
        rec_conditions.append(TradeRecommendation.wallet_address.in_(all_wallets))

    rec_stmt = (
        select(func.count())
        .select_from(TradeRecommendation)
        .where(*rec_conditions)
    )
    rec_result = await db.execute(rec_stmt)
    pending_count = rec_result.scalar() or 0

    urgent_stmt = (
        select(func.count())
        .select_from(TradeRecommendation)
        .where(*rec_conditions, TradeRecommendation.is_urgent == True)
    )
    urgent_result = await db.execute(urgent_stmt)
    urgent_count = urgent_result.scalar() or 0

    # Get all positions for dashboard (no limit)
    top_positions = await _get_top_positions(db, wallet, limit=500)

    # Compute market pulse from TaoStats pool data
    market_pulse = await _compute_market_pulse(top_positions)

    # --- Inactive positions (alpha_balance = 0, realized values preserved) ---
    inactive_conditions = [Position.alpha_balance <= 0]
    if wallet:
        inactive_conditions.append(Position.wallet_address == wallet)
    else:
        # Aggregate mode: restrict to active wallets only
        inactive_conditions.append(Position.wallet_address.in_(all_wallets))
    inactive_stmt = (
        select(Position)
        .where(*inactive_conditions)
        .order_by(Position.netuid)
    )
    inactive_result = await db.execute(inactive_stmt)
    inactive_positions = inactive_result.scalars().all()

    # Enrich with PositionCostBasis data (staked/unstaked totals, dates)
    # Use (wallet_address, netuid) as key for multi-wallet support
    cb_lookup: Dict[tuple, PositionCostBasis] = {}
    if inactive_positions:
        cb_conditions = []
        for p in inactive_positions:
            cb_conditions.append(
                (PositionCostBasis.wallet_address == p.wallet_address) &
                (PositionCostBasis.netuid == p.netuid)
            )
        # Build OR query for all (wallet, netuid) pairs
        cb_stmt = select(PositionCostBasis).where(or_(*cb_conditions))
        cb_result = await db.execute(cb_stmt)
        for cb in cb_result.scalars().all():
            cb_lookup[(cb.wallet_address, cb.netuid)] = cb

    closed_positions = []
    for p in inactive_positions:
        cb = cb_lookup.get((p.wallet_address, p.netuid))
        closed_positions.append(ClosedPositionSummary(
            wallet_address=p.wallet_address,
            netuid=p.netuid,
            subnet_name=p.subnet_name or f"Subnet {p.netuid}",
            total_staked_tao=cb.total_staked_tao if cb else Decimal("0"),
            total_unstaked_tao=cb.total_unstaked_tao if cb else Decimal("0"),
            realized_pnl_tao=p.total_realized_pnl_tao or Decimal("0"),
            first_entry=cb.first_stake_at if cb else p.entry_date,
            last_trade=cb.last_transaction_at if cb else None,
        ))

    # --- Free TAO balance ---
    free_tao = portfolio.allocation.unstaked_tao

    return DashboardResponse(
        portfolio=portfolio,
        wallets=all_wallets,
        top_positions=top_positions,
        closed_positions=closed_positions,
        free_tao_balance=free_tao,
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


async def _compute_conversion_exposure(
    db: AsyncSession,
    wallets: List[str],
    all_positions: List[Position],
    current_tao_price_usd: float,
) -> ConversionExposure:
    """Compute FX exposure with per-position decomposition.

    Decomposes USD P&L into two effects:
    - α/τ effect: TAO P&L from alpha conversion cycle × entry USD price
    - τ/$ effect: residual (total_usd_pnl - α/τ), capturing TAO price movement

    Handles active AND inactive positions uniformly:
    - Active (alpha_balance > 0): unrealized + realized FX from partial unstakes
    - Inactive (alpha_balance = 0): realized FX only (tao_value_mid = 0)
    - Root (netuid = 0): α/τ = 0, all P&L goes to τ/$

    Identity: α/τ + τ/$ = total_usd_pnl (enforced by residual construction).
    """
    current_usd = Decimal(str(current_tao_price_usd))
    # Use (wallet_address, netuid) as key for multi-wallet support
    pos_by_key = {(p.wallet_address, p.netuid): p for p in all_positions}

    # Fetch ALL PositionCostBasis records with USD data across all wallets
    cb_stmt = select(PositionCostBasis).where(
        PositionCostBasis.wallet_address.in_(wallets),
        PositionCostBasis.total_staked_usd > 0,
    )
    cb_result = await db.execute(cb_stmt)
    cb_by_key = {(cb.wallet_address, cb.netuid): cb for cb in cb_result.scalars().all()}

    # Accumulators
    total_alpha_tao_effect = Decimal("0")
    total_tao_usd_effect = Decimal("0")
    total_pnl_usd = Decimal("0")
    total_usd_cost = Decimal("0")
    total_tao_cost = Decimal("0")
    current_tao_value = Decimal("0")
    positions_with_usd = 0
    positions_with_cost_basis = 0
    positions_excluded = []

    # Per-position decomposition: iterate PositionCostBasis (has USD data)
    for (cb_wallet, netuid), cb in cb_by_key.items():
        if not cb.total_staked_tao or cb.total_staked_tao <= 0:
            continue
        if not cb.total_staked_usd or cb.total_staked_usd <= 0:
            continue

        positions_with_usd += 1
        position = pos_by_key.get((cb_wallet, netuid))

        # Position values (default 0 for inactive or missing Position records)
        tao_value = Decimal("0")
        unrealized_pnl = Decimal("0")
        realized_pnl = Decimal("0")
        cost_basis = Decimal("0")

        if position:
            tao_value = position.tao_value_mid or Decimal("0")
            unrealized_pnl = position.unrealized_pnl_tao or Decimal("0")
            realized_pnl = position.total_realized_pnl_tao or Decimal("0")
            cost_basis = position.cost_basis_tao or Decimal("0")

        # Skip active dTAO positions with no cost basis (can't compute entry price)
        if netuid != 0 and cost_basis <= 0 and tao_value > 0:
            positions_excluded.append(netuid)
            continue

        positions_with_cost_basis += 1

        # Per-position entry price (weighted avg TAO/USD at stake time)
        entry_usd_per_tao = cb.total_staked_usd / cb.total_staked_tao

        # Total USD P&L = current value + proceeds received - total invested
        pos_usd_pnl = (
            tao_value * current_usd
            + (cb.total_unstaked_usd or Decimal("0"))
            - cb.total_staked_usd
        )

        # Total TAO P&L = unrealized (from yield_tracker) + realized (from FIFO)
        pos_tao_pnl = unrealized_pnl + realized_pnl

        if netuid == 0:
            # Root: no α/τ (stake IS TAO), all P&L goes to τ/$
            pos_alpha_tao = Decimal("0")
            pos_tao_usd = pos_usd_pnl
        else:
            # dTAO: α/τ = TAO P&L × entry USD price, τ/$ = residual
            pos_alpha_tao = pos_tao_pnl * entry_usd_per_tao
            pos_tao_usd = pos_usd_pnl - pos_alpha_tao

        total_alpha_tao_effect += pos_alpha_tao
        total_tao_usd_effect += pos_tao_usd
        total_pnl_usd += pos_usd_pnl
        total_usd_cost += cb.usd_cost_basis or Decimal("0")
        total_tao_cost += cost_basis
        current_tao_value += tao_value

    # Current USD value of remaining active positions
    current_usd_value = current_tao_value * current_usd

    # Weighted average entry TAO price (remaining lots)
    entry_tao_price_usd = (
        total_usd_cost / total_tao_cost if total_tao_cost > 0 else Decimal("0")
    )

    # P&L percentage based on total USD ever invested
    total_input_usd = sum(
        cb.total_staked_usd for cb in cb_by_key.values()
        if cb.total_staked_usd and cb.total_staked_usd > 0
    )
    total_pnl_pct = (
        (total_pnl_usd / total_input_usd * 100)
        if total_input_usd > 0 else Decimal("0")
    )

    return ConversionExposure(
        usd_cost_basis=total_usd_cost.quantize(Decimal("0.01")),
        tao_cost_basis=total_tao_cost.quantize(Decimal("0.000000001")),
        current_usd_value=current_usd_value.quantize(Decimal("0.01")),
        current_tao_value=current_tao_value.quantize(Decimal("0.000000001")),
        total_pnl_usd=total_pnl_usd.quantize(Decimal("0.01")),
        total_pnl_pct=total_pnl_pct.quantize(Decimal("0.01")),
        alpha_tao_effect_usd=total_alpha_tao_effect.quantize(Decimal("0.01")),
        tao_usd_effect=total_tao_usd_effect.quantize(Decimal("0.01")),
        weighted_avg_entry_tao_price_usd=entry_tao_price_usd.quantize(Decimal("0.01")),
        has_complete_usd_history=(
            positions_with_usd == len(all_positions) and len(all_positions) > 0
        ),
        positions_with_usd_data=positions_with_usd,
        positions_with_cost_basis=positions_with_cost_basis,
        positions_excluded_from_fx=positions_excluded,
        total_positions=len(all_positions),
    )


@router.get("/overview", response_model=PortfolioOverviewResponse)
async def get_portfolio_overview(
    wallet: Optional[str] = Query(default=None, description="Wallet address to query"),
    db: AsyncSession = Depends(get_db),
) -> PortfolioOverviewResponse:
    """Enhanced portfolio overview with dual-currency metrics, rolling returns,
    and compounding projections.

    When wallet is not specified or "all", aggregates across all active wallets.
    """
    now = datetime.now(timezone.utc)
    wallet = await _resolve_wallet(db, wallet)
    all_wallets = await _get_active_wallets(db)
    if not all_wallets:
        return PortfolioOverviewResponse(as_of=now)

    # 1. Get latest portfolio snapshots — aggregate across target wallets
    target_wallets = [wallet] if wallet else all_wallets
    snapshots = []
    for w in target_wallets:
        snap_stmt = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.wallet_address == w)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        snap_result = await db.execute(snap_stmt)
        snap = snap_result.scalar_one_or_none()
        if snap:
            snapshots.append(snap)

    if not snapshots:
        return PortfolioOverviewResponse(as_of=now)

    # Use first snapshot as reference (single wallet) or aggregate (multi-wallet)
    snapshot = snapshots[0]

    # 2. Fetch TAO price context (spot + changes) concurrently with rolling returns
    tao_price_ctx = await _get_tao_price_context()
    tao_usd = float(tao_price_ctx.price_usd) if tao_price_ctx.price_usd else 0.0

    # 3. Compute rolling returns (use first wallet for now; aggregate mode skips)
    if wallet:
        returns_mid = await _compute_rolling_returns(db, wallet, "nav_mid_close")
        returns_exec = await _compute_rolling_returns(db, wallet, "nav_exec_close")
    else:
        returns_mid = []
        returns_exec = []

    # 4. Build dual-currency NAV (sum across all target wallet snapshots)
    nav_mid_tao = sum(s.nav_mid or Decimal("0") for s in snapshots)
    nav_exec_tao = sum(s.nav_exec_100pct or Decimal("0") for s in snapshots)

    nav_mid = DualCurrencyValue(
        tao=nav_mid_tao,
        usd=Decimal(str(round(float(nav_mid_tao) * tao_usd, 2))),
    )
    nav_exec = DualCurrencyValue(
        tao=nav_exec_tao,
        usd=Decimal(str(round(float(nav_exec_tao) * tao_usd, 2))),
    )

    # 5. Build dual-currency P&L (sum across all target wallet snapshots)
    # Get decomposed yield and alpha P&L from snapshots (pre-computed ledger aggregation)
    unrealized_yield_tao_val = sum(s.total_unrealized_yield_tao or Decimal("0") for s in snapshots)
    realized_yield_tao_val = sum(s.total_realized_yield_tao or Decimal("0") for s in snapshots)
    unrealized_alpha_pnl_tao = sum(s.total_unrealized_alpha_pnl_tao or Decimal("0") for s in snapshots)
    realized_alpha_pnl_tao = sum(s.total_realized_alpha_pnl_tao or Decimal("0") for s in snapshots)

    # Unrealized = total unrealized P&L (yield + alpha), so the Current Value
    # card's "Realized + Unrealized = Total" identity holds.
    # The Yield and Alpha cards show the decomposed components separately.
    unrealized_tao = sum(s.total_unrealized_pnl_tao or Decimal("0") for s in snapshots)
    realized_tao = sum(s.total_realized_pnl_tao or Decimal("0") for s in snapshots)
    total_pnl_tao = unrealized_tao + realized_tao
    cost_basis_tao = sum(s.total_cost_basis_tao or Decimal("0") for s in snapshots)
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
        # Decomposed yield and alpha P&L (from pre-computed ledger aggregation)
        unrealized_yield=DualCurrencyValue(
            tao=unrealized_yield_tao_val,
            usd=Decimal(str(round(float(unrealized_yield_tao_val) * tao_usd, 2))),
        ),
        realized_yield=DualCurrencyValue(
            tao=realized_yield_tao_val,
            usd=Decimal(str(round(float(realized_yield_tao_val) * tao_usd, 2))),
        ),
        unrealized_alpha_pnl=DualCurrencyValue(
            tao=unrealized_alpha_pnl_tao,
            usd=Decimal(str(round(float(unrealized_alpha_pnl_tao) * tao_usd, 2))),
        ),
        realized_alpha_pnl=DualCurrencyValue(
            tao=realized_alpha_pnl_tao,
            usd=Decimal(str(round(float(realized_alpha_pnl_tao) * tao_usd, 2))),
        ),
    )

    # 6. Build dual-currency yield (sum across all target wallet snapshots)
    daily_yield = sum(s.daily_yield_tao or Decimal("0") for s in snapshots)
    weekly_yield = sum(s.weekly_yield_tao or Decimal("0") for s in snapshots)
    monthly_yield = sum(s.monthly_yield_tao or Decimal("0") for s in snapshots)
    annualized_yield = daily_yield * 365
    # Weighted average APY across wallets
    active_value = sum(
        (s.nav_mid or Decimal("0")) - (s.unstaked_buffer_tao or Decimal("0"))
        for s in snapshots
    )
    if active_value > 0:
        portfolio_apy = sum(
            ((s.nav_mid or Decimal("0")) - (s.unstaked_buffer_tao or Decimal("0")))
            * (s.portfolio_apy or Decimal("0"))
            for s in snapshots
        ) / active_value
    else:
        portfolio_apy = Decimal("0")

    # 6a. Use pre-computed yield values from snapshot (single source of truth)
    #     These are computed by PositionMetricsService and aggregated in the snapshot.
    #     - unrealized_yield_tao: from open positions (emission_alpha × price)
    #     - realized_yield_tao: from PositionCostBasis (survives position closure)
    unrealized_yield_tao = unrealized_yield_tao_val  # From snapshot (computed above)
    total_yield_tao = unrealized_yield_tao + realized_yield_tao_val
    cumulative_yield_tao = total_yield_tao  # backwards compat

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
        # Yield decomposition
        total_yield=DualCurrencyValue(
            tao=total_yield_tao,
            usd=Decimal(str(round(float(total_yield_tao) * tao_usd, 2))),
        ),
        unrealized_yield=DualCurrencyValue(
            tao=unrealized_yield_tao,
            usd=Decimal(str(round(float(unrealized_yield_tao) * tao_usd, 2))),
        ),
        realized_yield=DualCurrencyValue(
            tao=realized_yield_tao_val,
            usd=Decimal(str(round(float(realized_yield_tao_val) * tao_usd, 2))),
        ),
    )

    # 7. Compounding projection
    compounding = _compute_compounding(nav_mid_tao, portfolio_apy, daily_yield)

    # 8. ATH and drawdown
    ath_conditions = []
    if wallet:
        ath_conditions.append(NAVHistory.wallet_address == wallet)
    else:
        ath_conditions.append(NAVHistory.wallet_address.in_(target_wallets))
    ath_stmt = select(func.max(NAVHistory.nav_exec_ath)).where(*ath_conditions)
    ath_result = await db.execute(ath_stmt)
    nav_ath = ath_result.scalar() or Decimal("0")
    drawdown_pct = (
        ((nav_ath - nav_exec_tao) / nav_ath * 100) if nav_ath > 0 else Decimal("0")
    )

    # 9. Position count (sum across snapshots)
    pos_count = sum(s.active_positions or 0 for s in snapshots)
    eligible = max((s.eligible_subnets or 0) for s in snapshots)

    # 10. Get open positions for conversion exposure calculation
    pos_conditions = []
    if wallet:
        pos_conditions.append(Position.wallet_address == wallet)
    else:
        # Aggregate mode: restrict to active wallets only
        pos_conditions.append(Position.wallet_address.in_(target_wallets))
    pos_stmt = select(Position).where(*pos_conditions)
    pos_result = await db.execute(pos_stmt)
    open_positions = pos_result.scalars().all()

    # 11. Compute conversion exposure (FX risk) across all target wallets
    conversion_exposure = await _compute_conversion_exposure(
        db, target_wallets, open_positions, tao_usd
    )

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
        conversion_exposure=conversion_exposure,
        as_of=max(s.timestamp for s in snapshots),
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

