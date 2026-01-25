"""Positions endpoints."""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.position import Position
from app.models.subnet import Subnet
from app.schemas.position import PositionResponse, PositionListResponse

router = APIRouter()
settings = get_settings()


@router.get("", response_model=PositionListResponse)
async def list_positions(
    db: AsyncSession = Depends(get_db),
    sort_by: str = Query(default="tao_value_mid", regex="^(tao_value_mid|alpha_balance|netuid)$"),
    order: str = Query(default="desc", regex="^(asc|desc)$"),
) -> PositionListResponse:
    """List all positions for the configured wallet."""
    wallet = settings.wallet_address

    # Build query
    stmt = select(Position).where(Position.wallet_address == wallet)

    # Apply sorting
    sort_col = getattr(Position, sort_by)
    if order == "desc":
        stmt = stmt.order_by(sort_col.desc())
    else:
        stmt = stmt.order_by(sort_col.asc())

    result = await db.execute(stmt)
    positions = result.scalars().all()

    # Calculate totals
    total_mid = sum(p.tao_value_mid for p in positions)
    total_exec = sum(p.tao_value_exec_50pct for p in positions)

    # Enrich with subnet data and calculate weights
    enriched = []
    for pos in positions:
        # Get subnet info
        subnet_stmt = select(Subnet).where(Subnet.netuid == pos.netuid)
        subnet_result = await db.execute(subnet_stmt)
        subnet = subnet_result.scalar_one_or_none()

        # Calculate unrealized PnL
        unrealized = pos.tao_value_mid - pos.cost_basis_tao
        unrealized_pct = (unrealized / pos.cost_basis_tao * 100) if pos.cost_basis_tao else Decimal("0")

        enriched.append(PositionResponse(
            id=pos.id,
            wallet_address=pos.wallet_address,
            netuid=pos.netuid,
            alpha_balance=pos.alpha_balance,
            tao_value_mid=pos.tao_value_mid,
            tao_value_exec_50pct=pos.tao_value_exec_50pct,
            tao_value_exec_100pct=pos.tao_value_exec_100pct,
            weight_pct=(pos.tao_value_mid / total_mid * 100) if total_mid else Decimal("0"),
            entry_price_tao=pos.entry_price_tao,
            entry_date=pos.entry_date,
            cost_basis_tao=pos.cost_basis_tao,
            realized_pnl_tao=pos.realized_pnl_tao,
            unrealized_pnl_tao=unrealized,
            unrealized_pnl_pct=unrealized_pct,
            exit_slippage_50pct=pos.exit_slippage_50pct,
            exit_slippage_100pct=pos.exit_slippage_100pct,
            validator_hotkey=pos.validator_hotkey,
            recommended_action=pos.recommended_action,
            action_reason=pos.action_reason,
            subnet_name=subnet.name if subnet else None,
            flow_regime=subnet.flow_regime if subnet else None,
            emission_share=subnet.emission_share if subnet else None,
            created_at=pos.created_at,
            updated_at=pos.updated_at,
        ))

    return PositionListResponse(
        positions=enriched,
        total=len(enriched),
        total_tao_value_mid=total_mid,
        total_tao_value_exec=total_exec,
    )


@router.get("/{netuid}", response_model=PositionResponse)
async def get_position(
    netuid: int,
    db: AsyncSession = Depends(get_db),
) -> PositionResponse:
    """Get position details for a specific subnet."""
    wallet = settings.wallet_address

    stmt = select(Position).where(
        Position.wallet_address == wallet,
        Position.netuid == netuid,
    )
    result = await db.execute(stmt)
    pos = result.scalar_one_or_none()

    if pos is None:
        raise HTTPException(status_code=404, detail=f"Position not found for netuid {netuid}")

    # Get subnet info
    subnet_stmt = select(Subnet).where(Subnet.netuid == netuid)
    subnet_result = await db.execute(subnet_stmt)
    subnet = subnet_result.scalar_one_or_none()

    # Get total for weight calculation
    total_stmt = select(Position).where(Position.wallet_address == wallet)
    total_result = await db.execute(total_stmt)
    all_positions = total_result.scalars().all()
    total_mid = sum(p.tao_value_mid for p in all_positions)

    # Calculate unrealized PnL
    unrealized = pos.tao_value_mid - pos.cost_basis_tao
    unrealized_pct = (unrealized / pos.cost_basis_tao * 100) if pos.cost_basis_tao else Decimal("0")

    return PositionResponse(
        id=pos.id,
        wallet_address=pos.wallet_address,
        netuid=pos.netuid,
        alpha_balance=pos.alpha_balance,
        tao_value_mid=pos.tao_value_mid,
        tao_value_exec_50pct=pos.tao_value_exec_50pct,
        tao_value_exec_100pct=pos.tao_value_exec_100pct,
        weight_pct=(pos.tao_value_mid / total_mid * 100) if total_mid else Decimal("0"),
        entry_price_tao=pos.entry_price_tao,
        entry_date=pos.entry_date,
        cost_basis_tao=pos.cost_basis_tao,
        realized_pnl_tao=pos.realized_pnl_tao,
        unrealized_pnl_tao=unrealized,
        unrealized_pnl_pct=unrealized_pct,
        exit_slippage_50pct=pos.exit_slippage_50pct,
        exit_slippage_100pct=pos.exit_slippage_100pct,
        validator_hotkey=pos.validator_hotkey,
        recommended_action=pos.recommended_action,
        action_reason=pos.action_reason,
        subnet_name=subnet.name if subnet else None,
        flow_regime=subnet.flow_regime if subnet else None,
        emission_share=subnet.emission_share if subnet else None,
        created_at=pos.created_at,
        updated_at=pos.updated_at,
    )
