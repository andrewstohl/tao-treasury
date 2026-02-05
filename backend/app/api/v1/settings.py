"""Settings API endpoints for viability scoring configuration."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.viability_config import ViabilityConfig
from app.schemas.settings import ViabilityConfigResponse, ViabilityConfigUpdateRequest

router = APIRouter()


def _settings_to_response(settings) -> ViabilityConfigResponse:
    """Build a response from env-based defaults."""
    return ViabilityConfigResponse(
        id=None,
        config_name="defaults",
        is_active=True,
        source="defaults",
        min_tao_reserve=settings.viability_min_tao_reserve,
        min_emission_share=settings.viability_min_emission_share,
        min_age_days=settings.viability_min_age_days,
        min_holders=settings.viability_min_holders,
        max_drawdown_30d=settings.viability_max_drawdown_30d,
        max_negative_flow_ratio=settings.viability_max_negative_flow_ratio,
        weight_tao_reserve=settings.viability_weight_tao_reserve,
        weight_net_flow_7d=settings.viability_weight_net_flow_7d,
        weight_emission_share=settings.viability_weight_emission_share,
        weight_price_trend_7d=settings.viability_weight_price_trend_7d,
        weight_subnet_age=settings.viability_weight_subnet_age,
        weight_max_drawdown_30d=settings.viability_weight_max_drawdown_30d,
        tier_1_min=settings.viability_tier_1_min,
        tier_2_min=settings.viability_tier_2_min,
        tier_3_min=settings.viability_tier_3_min,
        age_cap_days=settings.viability_age_cap_days,
        enabled=settings.enable_viability_scoring,
    )


def _row_to_response(row: ViabilityConfig) -> ViabilityConfigResponse:
    """Build a response from a database row."""
    return ViabilityConfigResponse(
        id=row.id,
        config_name=row.config_name,
        is_active=row.is_active,
        source="database",
        min_tao_reserve=row.min_tao_reserve,
        min_emission_share=row.min_emission_share,
        min_age_days=row.min_age_days,
        min_holders=row.min_holders,
        max_drawdown_30d=row.max_drawdown_30d,
        max_negative_flow_ratio=row.max_negative_flow_ratio,
        weight_tao_reserve=row.weight_tao_reserve,
        weight_net_flow_7d=row.weight_net_flow_7d,
        weight_emission_share=row.weight_emission_share,
        weight_price_trend_7d=row.weight_price_trend_7d,
        weight_subnet_age=row.weight_subnet_age,
        weight_max_drawdown_30d=row.weight_max_drawdown_30d,
        tier_1_min=row.tier_1_min,
        tier_2_min=row.tier_2_min,
        tier_3_min=row.tier_3_min,
        age_cap_days=row.age_cap_days,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/viability", response_model=ViabilityConfigResponse)
async def get_viability_config(
    db: AsyncSession = Depends(get_db),
) -> ViabilityConfigResponse:
    """Get current active viability scoring configuration.

    Returns the active database config if one exists, otherwise returns
    env-based defaults from config.py.
    """
    stmt = (
        select(ViabilityConfig)
        .where(ViabilityConfig.is_active == True)  # noqa: E712
        .order_by(ViabilityConfig.updated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is not None:
        return _row_to_response(row)

    return _settings_to_response(get_settings())


@router.put("/viability", response_model=ViabilityConfigResponse)
async def update_viability_config(
    request: ViabilityConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> ViabilityConfigResponse:
    """Update or create the active viability scoring configuration.

    If a database config exists, it is updated in place.
    Otherwise, a new row is created using env defaults as the base,
    then the provided fields are applied on top.
    """
    settings = get_settings()

    # Find existing active config
    stmt = (
        select(ViabilityConfig)
        .where(ViabilityConfig.is_active == True)  # noqa: E712
        .order_by(ViabilityConfig.updated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        # Create from env defaults, then overlay request fields
        row = ViabilityConfig(
            config_name=request.config_name or "custom",
            is_active=True,
            min_tao_reserve=settings.viability_min_tao_reserve,
            min_emission_share=settings.viability_min_emission_share,
            min_age_days=settings.viability_min_age_days,
            min_holders=settings.viability_min_holders,
            max_drawdown_30d=settings.viability_max_drawdown_30d,
            max_negative_flow_ratio=settings.viability_max_negative_flow_ratio,
            weight_tao_reserve=settings.viability_weight_tao_reserve,
            weight_net_flow_7d=settings.viability_weight_net_flow_7d,
            weight_emission_share=settings.viability_weight_emission_share,
            weight_price_trend_7d=settings.viability_weight_price_trend_7d,
            weight_subnet_age=settings.viability_weight_subnet_age,
            weight_max_drawdown_30d=settings.viability_weight_max_drawdown_30d,
            tier_1_min=settings.viability_tier_1_min,
            tier_2_min=settings.viability_tier_2_min,
            tier_3_min=settings.viability_tier_3_min,
            age_cap_days=settings.viability_age_cap_days,
            enabled=settings.enable_viability_scoring,
        )
        db.add(row)

    # Apply partial update
    if request.config_name is not None:
        row.config_name = request.config_name
    if request.min_tao_reserve is not None:
        row.min_tao_reserve = request.min_tao_reserve
    if request.min_emission_share is not None:
        row.min_emission_share = request.min_emission_share
    if request.min_age_days is not None:
        row.min_age_days = request.min_age_days
    if request.min_holders is not None:
        row.min_holders = request.min_holders
    if request.max_drawdown_30d is not None:
        row.max_drawdown_30d = request.max_drawdown_30d
    if request.max_negative_flow_ratio is not None:
        row.max_negative_flow_ratio = request.max_negative_flow_ratio
    if request.weight_tao_reserve is not None:
        row.weight_tao_reserve = request.weight_tao_reserve
    if request.weight_net_flow_7d is not None:
        row.weight_net_flow_7d = request.weight_net_flow_7d
    if request.weight_emission_share is not None:
        row.weight_emission_share = request.weight_emission_share
    if request.weight_price_trend_7d is not None:
        row.weight_price_trend_7d = request.weight_price_trend_7d
    if request.weight_subnet_age is not None:
        row.weight_subnet_age = request.weight_subnet_age
    if request.weight_max_drawdown_30d is not None:
        row.weight_max_drawdown_30d = request.weight_max_drawdown_30d
    if request.tier_1_min is not None:
        row.tier_1_min = request.tier_1_min
    if request.tier_2_min is not None:
        row.tier_2_min = request.tier_2_min
    if request.tier_3_min is not None:
        row.tier_3_min = request.tier_3_min
    if request.age_cap_days is not None:
        row.age_cap_days = request.age_cap_days
    if request.enabled is not None:
        row.enabled = request.enabled

    # Validate weights sum after merging
    weight_sum = (
        row.weight_tao_reserve
        + row.weight_net_flow_7d
        + row.weight_emission_share
        + row.weight_price_trend_7d
        + row.weight_subnet_age
        + row.weight_max_drawdown_30d
    )
    if abs(weight_sum - Decimal("1.0")) > Decimal("0.001"):
        raise HTTPException(
            status_code=422,
            detail=f"Weights must sum to 1.0 after merge (got {weight_sum})",
        )

    await db.flush()
    await db.refresh(row)

    # Reset the viability scorer singleton so it picks up new config
    from app.services.strategy.viability_scorer import reset_viability_scorer
    reset_viability_scorer()

    return _row_to_response(row)


@router.post("/viability/reset", response_model=ViabilityConfigResponse)
async def reset_viability_config(
    db: AsyncSession = Depends(get_db),
) -> ViabilityConfigResponse:
    """Reset to env-based defaults by deactivating all database configs."""
    stmt = select(ViabilityConfig).where(ViabilityConfig.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    for row in rows:
        row.is_active = False

    # Reset the viability scorer singleton
    from app.services.strategy.viability_scorer import reset_viability_scorer
    reset_viability_scorer()

    return _settings_to_response(get_settings())
