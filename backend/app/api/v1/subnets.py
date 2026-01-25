"""Subnets endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.subnet import Subnet
from app.schemas.subnet import SubnetResponse, SubnetListResponse

router = APIRouter()


@router.get("", response_model=SubnetListResponse)
async def list_subnets(
    db: AsyncSession = Depends(get_db),
    eligible_only: bool = Query(default=False),
    sort_by: str = Query(default="emission_share", regex="^(emission_share|pool_tao_reserve|holder_count|netuid)$"),
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
            registered_at=s.registered_at,
            age_days=s.age_days,
            emission_share=s.emission_share,
            total_stake_tao=s.total_stake_tao,
            pool_tao_reserve=s.pool_tao_reserve,
            pool_alpha_reserve=s.pool_alpha_reserve,
            alpha_price_tao=s.alpha_price_tao,
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
        registered_at=subnet.registered_at,
        age_days=subnet.age_days,
        emission_share=subnet.emission_share,
        total_stake_tao=subnet.total_stake_tao,
        pool_tao_reserve=subnet.pool_tao_reserve,
        pool_alpha_reserve=subnet.pool_alpha_reserve,
        alpha_price_tao=subnet.alpha_price_tao,
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
        created_at=subnet.created_at,
        updated_at=subnet.updated_at,
    )
