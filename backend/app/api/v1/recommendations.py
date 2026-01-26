"""Trade recommendations endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.trade import TradeRecommendation
from app.models.subnet import Subnet
from app.schemas.trade import (
    TradeRecommendationResponse,
    RecommendationListResponse,
    MarkExecutedRequest,
)

router = APIRouter()


@router.get("", response_model=RecommendationListResponse)
async def list_recommendations(
    db: AsyncSession = Depends(get_db),
    status: str = Query(default="pending", regex="^(pending|approved|executed|expired|all)$"),
) -> RecommendationListResponse:
    """List trade recommendations."""
    settings = get_settings()
    wallet = settings.wallet_address

    stmt = select(TradeRecommendation).where(
        TradeRecommendation.wallet_address == wallet
    )

    if status != "all":
        stmt = stmt.where(TradeRecommendation.status == status)

    stmt = stmt.order_by(
        TradeRecommendation.priority.asc(),
        TradeRecommendation.created_at.desc(),
    )

    result = await db.execute(stmt)
    recs = result.scalars().all()

    # Enrich with subnet names
    responses = []
    total_cost = Decimal("0")
    pending_count = 0

    for rec in recs:
        # Get subnet name
        subnet_stmt = select(Subnet).where(Subnet.netuid == rec.netuid)
        subnet_result = await db.execute(subnet_stmt)
        subnet = subnet_result.scalar_one_or_none()

        responses.append(TradeRecommendationResponse(
            id=rec.id,
            wallet_address=rec.wallet_address,
            netuid=rec.netuid,
            subnet_name=subnet.name if subnet else None,
            direction=rec.direction,
            size_alpha=rec.size_alpha,
            size_tao=rec.size_tao,
            size_pct_of_position=rec.size_pct_of_position,
            estimated_slippage_pct=rec.estimated_slippage_pct,
            estimated_slippage_tao=rec.estimated_slippage_tao,
            total_estimated_cost_tao=rec.total_estimated_cost_tao,
            expected_nav_impact_tao=rec.expected_nav_impact_tao,
            trigger_type=rec.trigger_type,
            reason=rec.reason,
            priority=rec.priority,
            is_urgent=rec.is_urgent,
            tranche_number=rec.tranche_number,
            total_tranches=rec.total_tranches,
            status=rec.status,
            expires_at=rec.expires_at,
            created_at=rec.created_at,
        ))

        if rec.status == "pending":
            pending_count += 1
            total_cost += rec.total_estimated_cost_tao

    return RecommendationListResponse(
        recommendations=responses,
        total=len(responses),
        pending_count=pending_count,
        total_estimated_cost_tao=total_cost,
    )


@router.post("/{rec_id}/mark_executed", response_model=TradeRecommendationResponse)
async def mark_executed(
    rec_id: int,
    request: MarkExecutedRequest,
    db: AsyncSession = Depends(get_db),
) -> TradeRecommendationResponse:
    """Mark a recommendation as manually executed."""
    stmt = select(TradeRecommendation).where(TradeRecommendation.id == rec_id)
    result = await db.execute(stmt)
    rec = result.scalar_one_or_none()

    if rec is None:
        raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")

    if rec.status != "pending":
        raise HTTPException(status_code=400, detail=f"Recommendation is not pending (status: {rec.status})")

    now = datetime.now(timezone.utc)
    rec.status = "executed"
    rec.marked_executed_at = now
    rec.actual_slippage_pct = request.actual_slippage_pct
    rec.execution_notes = request.notes

    await db.commit()
    await db.refresh(rec)

    # Get subnet name
    subnet_stmt = select(Subnet).where(Subnet.netuid == rec.netuid)
    subnet_result = await db.execute(subnet_stmt)
    subnet = subnet_result.scalar_one_or_none()

    return TradeRecommendationResponse(
        id=rec.id,
        wallet_address=rec.wallet_address,
        netuid=rec.netuid,
        subnet_name=subnet.name if subnet else None,
        direction=rec.direction,
        size_alpha=rec.size_alpha,
        size_tao=rec.size_tao,
        size_pct_of_position=rec.size_pct_of_position,
        estimated_slippage_pct=rec.estimated_slippage_pct,
        estimated_slippage_tao=rec.estimated_slippage_tao,
        total_estimated_cost_tao=rec.total_estimated_cost_tao,
        expected_nav_impact_tao=rec.expected_nav_impact_tao,
        trigger_type=rec.trigger_type,
        reason=rec.reason,
        priority=rec.priority,
        is_urgent=rec.is_urgent,
        tranche_number=rec.tranche_number,
        total_tranches=rec.total_tranches,
        status=rec.status,
        expires_at=rec.expires_at,
        created_at=rec.created_at,
    )
