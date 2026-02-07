"""Subnets endpoints."""

import asyncio
import time
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.subnet import Subnet
from app.schemas.subnet import (
    SubnetResponse,
    SubnetListResponse,
    EnrichedSubnetResponse,
    EnrichedSubnetListResponse,
    VolatilePoolData,
    SparklinePoint,
    SubnetIdentity,
    DevActivity,
)
from app.services.data.taostats_client import taostats_client

logger = structlog.get_logger()

router = APIRouter()


@router.get("", response_model=SubnetListResponse)
async def list_subnets(
    db: AsyncSession = Depends(get_db),
    eligible_only: bool = Query(default=False),
    sort_by: str = Query(default="emission_share", regex="^(emission_share|pool_tao_reserve|holder_count|netuid|rank|market_cap_tao|viability_score)$"),
    order: str = Query(default="desc", regex="^(asc|desc)$"),
) -> SubnetListResponse:
    """List all subnets with current metrics."""
    stmt = select(Subnet)

    if eligible_only:
        stmt = stmt.where(Subnet.is_eligible == True)

    # Apply sorting
    sort_col = getattr(Subnet, sort_by)
    if order == "desc":
        stmt = stmt.order_by(sort_col.desc())
    else:
        stmt = stmt.order_by(sort_col.asc())

    result = await db.execute(stmt)
    subnets = result.scalars().all()

    # Count eligible
    eligible_count = sum(1 for s in subnets if s.is_eligible)

    responses = [
        SubnetResponse(
            id=s.id,
            netuid=s.netuid,
            name=s.name,
            description=s.description,
            owner_address=s.owner_address,
            owner_take=s.owner_take,
            fee_rate=s.fee_rate,
            incentive_burn=s.incentive_burn,
            registered_at=s.registered_at,
            age_days=s.age_days,
            emission_share=s.emission_share,
            total_stake_tao=s.total_stake_tao,
            pool_tao_reserve=s.pool_tao_reserve,
            pool_alpha_reserve=s.pool_alpha_reserve,
            alpha_price_tao=s.alpha_price_tao,
            rank=s.rank,
            market_cap_tao=s.market_cap_tao,
            holder_count=s.holder_count,
            taoflow_1d=s.taoflow_1d,
            taoflow_3d=s.taoflow_3d,
            taoflow_7d=s.taoflow_7d,
            taoflow_14d=s.taoflow_14d,
            flow_regime=s.flow_regime,
            flow_regime_since=s.flow_regime_since,
            validator_apy=s.validator_apy,
            is_eligible=s.is_eligible,
            ineligibility_reasons=s.ineligibility_reasons,
            category=s.category,
            viability_score=s.viability_score,
            viability_tier=s.viability_tier,
            viability_factors=s.viability_factors,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in subnets
    ]

    return SubnetListResponse(
        subnets=responses,
        total=len(responses),
        eligible_count=eligible_count,
    )


def _extract_volatile(pool_data: Dict) -> VolatilePoolData:
    """Extract volatile fields from a TaoStats pool record.

    TaoStats API field naming conventions:
    - Time periods: _1_hour, _1_day, _1_week, _1_month
    - 24hr metrics: _24_hr (e.g., buys_24_hr, tao_volume_24_hr)
    - Price extremes: highest_price_24_hr, lowest_price_24_hr
    - Sentiment: fear_and_greed_index, fear_and_greed_sentiment
    - Sparkline: seven_day_prices (list of {timestamp, price, block_number})
    - Alpha/pool values: returned as strings in rao (divide by 1e9 for tokens)
    """
    RAO_DIVISOR = 1e9

    # Parse sparkline data (TaoStats uses "seven_day_prices")
    sparkline_raw = pool_data.get("seven_day_prices") or []
    sparkline = None
    if sparkline_raw and isinstance(sparkline_raw, list):
        sparkline = [
            SparklinePoint(
                timestamp=pt.get("timestamp", ""),
                price=float(pt.get("price", 0) or 0),
            )
            for pt in sparkline_raw
            if isinstance(pt, dict)
        ]

    def _float(key: str) -> Optional[float]:
        val = pool_data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _int(key: str) -> Optional[int]:
        val = pool_data.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def _rao_to_float(key: str) -> Optional[float]:
        """Convert a rao string value to float token count."""
        val = pool_data.get(key)
        if val is None:
            return None
        try:
            return float(val) / RAO_DIVISOR
        except (ValueError, TypeError):
            return None

    # TaoStats volume values are in rao - convert to TAO
    tao_vol_raw = _float("tao_volume_24_hr")
    tao_buy_vol_raw = _float("tao_buy_volume_24_hr")
    tao_sell_vol_raw = _float("tao_sell_volume_24_hr")

    return VolatilePoolData(
        price_change_1h=_float("price_change_1_hour"),
        price_change_24h=_float("price_change_1_day"),
        price_change_7d=_float("price_change_1_week"),
        price_change_30d=_float("price_change_1_month"),
        high_24h=_float("highest_price_24_hr"),
        low_24h=_float("lowest_price_24_hr"),
        market_cap_change_24h=_float("market_cap_change_1_day"),
        tao_volume_24h=tao_vol_raw / RAO_DIVISOR if tao_vol_raw is not None else None,
        tao_buy_volume_24h=tao_buy_vol_raw / RAO_DIVISOR if tao_buy_vol_raw is not None else None,
        tao_sell_volume_24h=tao_sell_vol_raw / RAO_DIVISOR if tao_sell_vol_raw is not None else None,
        buys_24h=_int("buys_24_hr"),
        sells_24h=_int("sells_24_hr"),
        buyers_24h=_int("buyers_24_hr"),
        sellers_24h=_int("sellers_24_hr"),
        fear_greed_index=_float("fear_and_greed_index"),
        fear_greed_sentiment=pool_data.get("fear_and_greed_sentiment"),
        sparkline_7d=sparkline,
        alpha_in_pool=_rao_to_float("alpha_in_pool"),
        alpha_staked=_rao_to_float("alpha_staked"),
        total_alpha=_rao_to_float("total_alpha"),
        root_prop=_float("root_prop"),
        startup_mode=pool_data.get("startup_mode"),
    )


def _extract_identity(identity_data: Dict) -> SubnetIdentity:
    """Extract identity fields from a TaoStats subnet identity record.

    Note: TaoStats 'description' is a short tagline, mapped to 'tagline'
    to avoid confusion with the DB 'description' field.
    """
    return SubnetIdentity(
        tagline=identity_data.get("description"),
        summary=identity_data.get("summary"),
        tags=identity_data.get("tags") or [],
        github_repo=identity_data.get("github_repo"),
        subnet_url=identity_data.get("subnet_url"),
        logo_url=identity_data.get("logo_url"),
        discord=identity_data.get("discord"),
        twitter=identity_data.get("twitter"),
        subnet_contact=identity_data.get("subnet_contact"),
    )


def _extract_dev_activity(activity_data: Dict) -> DevActivity:
    """Extract dev activity fields from a TaoStats dev_activity record."""
    def _int_or_none(key: str) -> Optional[int]:
        val = activity_data.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    return DevActivity(
        repo_url=activity_data.get("repo_url"),
        commits_1d=_int_or_none("commits_1d"),
        commits_7d=_int_or_none("commits_7d"),
        commits_30d=_int_or_none("commits_30d"),
        prs_opened_7d=_int_or_none("prs_opened_7d"),
        prs_merged_7d=_int_or_none("prs_merged_7d"),
        issues_opened_30d=_int_or_none("issues_opened_30d"),
        issues_closed_30d=_int_or_none("issues_closed_30d"),
        reviews_30d=_int_or_none("reviews_30d"),
        unique_contributors_7d=_int_or_none("unique_contributors_7d"),
        unique_contributors_30d=_int_or_none("unique_contributors_30d"),
        last_event_at=activity_data.get("last_event_at"),
        days_since_last_event=_int_or_none("days_since_last_event"),
    )


@router.get("/enriched", response_model=EnrichedSubnetListResponse)
async def list_enriched_subnets(
    db: AsyncSession = Depends(get_db),
    eligible_only: bool = Query(default=False),
) -> EnrichedSubnetListResponse:
    """List subnets enriched with volatile market data, identity, and dev activity.

    Merges stable DB data with live TaoStats data (pool: 2-min cache,
    identity/dev_activity: 30-min cache). All three TaoStats fetches run
    in parallel. Gracefully degrades per-source if any fetch fails.
    """
    # 1. Query all subnets from DB
    stmt = select(Subnet)
    if eligible_only:
        stmt = stmt.where(Subnet.is_eligible == True)

    result = await db.execute(stmt)
    subnets = result.scalars().all()

    # 2. Fetch pool, identity, and dev activity data in parallel
    taostats_available = True
    volatile_lookup: Dict[int, VolatilePoolData] = {}
    identity_lookup: Dict[int, SubnetIdentity] = {}
    dev_activity_lookup: Dict[int, DevActivity] = {}
    cache_age_seconds: Optional[int] = None

    try:
        fetch_start = time.monotonic()

        results = await asyncio.gather(
            taostats_client.get_pools_full(),
            taostats_client.get_subnet_identity(),
            taostats_client.get_dev_activity(),
            return_exceptions=True,
        )

        fetch_elapsed = time.monotonic() - fetch_start
        cache_age_seconds = int(fetch_elapsed) if fetch_elapsed > 1 else 0

        # Process pool data
        pool_response = results[0]
        if isinstance(pool_response, Exception):
            taostats_available = False
            logger.warning("Pool data fetch failed", error=str(pool_response))
        else:
            pools_data = pool_response.get("data", [])
            for pool in pools_data:
                netuid = pool.get("netuid")
                if netuid is not None:
                    volatile_lookup[int(netuid)] = _extract_volatile(pool)

        # Process identity data (non-critical: log and continue)
        identity_response = results[1]
        if isinstance(identity_response, Exception):
            logger.warning("Identity fetch failed", error=str(identity_response))
        else:
            identity_data = identity_response.get("data", [])
            for item in identity_data:
                netuid = item.get("netuid")
                if netuid is not None:
                    identity_lookup[int(netuid)] = _extract_identity(item)

        # Process dev activity (non-critical: log and continue)
        dev_response = results[2]
        if isinstance(dev_response, Exception):
            logger.warning("Dev activity fetch failed", error=str(dev_response))
        else:
            dev_data = dev_response.get("data", [])
            for item in dev_data:
                netuid = item.get("netuid")
                if netuid is not None:
                    dev_activity_lookup[int(netuid)] = _extract_dev_activity(item)

        logger.info(
            "Enriched endpoint fetched all data",
            pool_count=len(volatile_lookup),
            identity_count=len(identity_lookup),
            dev_activity_count=len(dev_activity_lookup),
        )
    except Exception as e:
        taostats_available = False
        logger.warning("TaoStats unavailable for enriched endpoint", error=str(e))

    # 3. Merge and build response
    eligible_count = sum(1 for s in subnets if s.is_eligible)

    # Fill in missing logo_url with TaoStats fallback images
    TAOSTATS_LOGO_FALLBACK = "https://taostats.io/images/subnets/{netuid}.webp"

    enriched = []
    for s in subnets:
        identity = identity_lookup.get(s.netuid)
        if identity and not identity.logo_url:
            identity.logo_url = TAOSTATS_LOGO_FALLBACK.format(netuid=s.netuid)
        elif not identity:
            identity = SubnetIdentity(
                logo_url=TAOSTATS_LOGO_FALLBACK.format(netuid=s.netuid),
            )

        enriched.append(EnrichedSubnetResponse(
            netuid=s.netuid,
            name=s.name,
            description=s.description,
            owner_address=s.owner_address,
            owner_take=s.owner_take,
            fee_rate=s.fee_rate,
            incentive_burn=s.incentive_burn,
            registered_at=s.registered_at,
            age_days=s.age_days,
            emission_share=s.emission_share,
            total_stake_tao=s.total_stake_tao,
            pool_tao_reserve=s.pool_tao_reserve,
            pool_alpha_reserve=s.pool_alpha_reserve,
            alpha_price_tao=s.alpha_price_tao,
            rank=s.rank,
            market_cap_tao=s.market_cap_tao,
            holder_count=s.holder_count,
            taoflow_1d=s.taoflow_1d,
            taoflow_3d=s.taoflow_3d,
            taoflow_7d=s.taoflow_7d,
            taoflow_14d=s.taoflow_14d,
            flow_regime=s.flow_regime,
            flow_regime_since=s.flow_regime_since,
            validator_apy=s.validator_apy,
            is_eligible=s.is_eligible,
            ineligibility_reasons=s.ineligibility_reasons,
            category=s.category,
            viability_score=s.viability_score,
            viability_tier=s.viability_tier,
            viability_factors=s.viability_factors,
            volatile=volatile_lookup.get(s.netuid),
            identity=identity,
            dev_activity=dev_activity_lookup.get(s.netuid),
        ))

    # Sort by rank (nulls last)
    enriched.sort(key=lambda x: (x.rank is None, x.rank or 0))

    return EnrichedSubnetListResponse(
        subnets=enriched,
        total=len(enriched),
        eligible_count=eligible_count,
        taostats_available=taostats_available,
        cache_age_seconds=cache_age_seconds,
    )


@router.get("/{netuid}", response_model=SubnetResponse)
async def get_subnet(
    netuid: int,
    db: AsyncSession = Depends(get_db),
) -> SubnetResponse:
    """Get subnet details."""
    stmt = select(Subnet).where(Subnet.netuid == netuid)
    result = await db.execute(stmt)
    subnet = result.scalar_one_or_none()

    if subnet is None:
        raise HTTPException(status_code=404, detail=f"Subnet {netuid} not found")

    return SubnetResponse(
        id=subnet.id,
        netuid=subnet.netuid,
        name=subnet.name,
        description=subnet.description,
        owner_address=subnet.owner_address,
        owner_take=subnet.owner_take,
        fee_rate=subnet.fee_rate,
        incentive_burn=subnet.incentive_burn,
        registered_at=subnet.registered_at,
        age_days=subnet.age_days,
        emission_share=subnet.emission_share,
        total_stake_tao=subnet.total_stake_tao,
        pool_tao_reserve=subnet.pool_tao_reserve,
        pool_alpha_reserve=subnet.pool_alpha_reserve,
        alpha_price_tao=subnet.alpha_price_tao,
        rank=subnet.rank,
        market_cap_tao=subnet.market_cap_tao,
        holder_count=subnet.holder_count,
        taoflow_1d=subnet.taoflow_1d,
        taoflow_3d=subnet.taoflow_3d,
        taoflow_7d=subnet.taoflow_7d,
        taoflow_14d=subnet.taoflow_14d,
        flow_regime=subnet.flow_regime,
        flow_regime_since=subnet.flow_regime_since,
        validator_apy=subnet.validator_apy,
        is_eligible=subnet.is_eligible,
        ineligibility_reasons=subnet.ineligibility_reasons,
        category=subnet.category,
        viability_score=subnet.viability_score,
        viability_tier=subnet.viability_tier,
        viability_factors=subnet.viability_factors,
        created_at=subnet.created_at,
        updated_at=subnet.updated_at,
    )


@router.get("/{netuid}/chart")
async def get_subnet_chart(
    netuid: int,
    resolution: str = Query(
        default="60",
        regex="^(1|5|15|30|60|240|D|W)$",
        description="Candle resolution: 1,5,15,30,60,240 (minutes) or D (daily), W (weekly)"
    ),
    days: int = Query(default=30, ge=1, le=365, description="Number of days of data"),
) -> dict:
    """Get OHLC candlestick chart data for a subnet.

    Returns TradingView-compatible OHLC data for proper candlestick charts.

    Args:
        netuid: Subnet ID
        resolution: Candle timeframe (1,5,15,30,60,240 minutes or D/W)
        days: Number of days of history (default 30, max 365)

    Returns:
        OHLC data with timestamps, open, high, low, close arrays
    """
    import time as time_module

    timestamp_end = int(time_module.time())
    timestamp_start = timestamp_end - (days * 24 * 60 * 60)

    try:
        response = await taostats_client.get_tradingview_ohlc(
            netuid=netuid,
            resolution=resolution,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
        )

        # TradingView UDF format returns arrays
        # Transform to a more frontend-friendly format
        status = response.get("s", "no_data")

        if status != "ok":
            return {
                "netuid": netuid,
                "resolution": resolution,
                "status": status,
                "candles": [],
            }

        timestamps = response.get("t", [])
        opens = response.get("o", [])
        highs = response.get("h", [])
        lows = response.get("l", [])
        closes = response.get("c", [])
        volumes = response.get("v", [])

        # Build candle array
        candles = []
        for i in range(len(timestamps)):
            candle = {
                "time": timestamps[i],
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": closes[i] if i < len(closes) else None,
            }
            if volumes and i < len(volumes):
                candle["volume"] = volumes[i]
            candles.append(candle)

        return {
            "netuid": netuid,
            "resolution": resolution,
            "status": "ok",
            "candles": candles,
        }

    except Exception as e:
        logger.error("Failed to fetch OHLC data", netuid=netuid, error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch chart data from TaoStats: {str(e)}"
        )
