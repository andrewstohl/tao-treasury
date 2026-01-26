"""Positions endpoints."""

from decimal import Decimal
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.position import Position
from app.models.subnet import Subnet
from app.models.validator import Validator
from app.schemas.position import PositionResponse, PositionListResponse

router = APIRouter()
settings = get_settings()


def _compute_position_health(
    unrealized_pnl_pct: Decimal,
    weight_pct: Decimal,
    current_apy: Optional[Decimal],
    avg_apy: Decimal,
) -> Tuple[str, Optional[str]]:
    """Compute health status and reason for a position."""
    reasons = []
    status = "green"

    pnl_pct = float(unrealized_pnl_pct)

    # Check P&L
    if pnl_pct < -10:
        reasons.append(f"Down {abs(pnl_pct):.1f}% from cost basis")
        status = "red"
    elif pnl_pct < -5:
        reasons.append(f"Down {abs(pnl_pct):.1f}% from cost basis")
        status = "yellow" if status != "red" else status

    # Check APY relative to average
    if current_apy and avg_apy and avg_apy > 0:
        apy_ratio = float(current_apy / avg_apy)
        if apy_ratio < 0.5:
            reasons.append(f"APY below average ({float(current_apy):.1f}% vs {float(avg_apy):.1f}%)")
            status = "yellow" if status == "green" else status

    # Check concentration
    if float(weight_pct) > 20:
        reasons.append(f"High concentration ({float(weight_pct):.1f}% of portfolio)")
        status = "yellow" if status == "green" else status

    reason = "; ".join(reasons) if reasons else None
    return status, reason


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

    # Fetch all validators for APY lookup
    validator_apy_map = {}
    if positions:
        val_stmt = select(Validator).where(
            Validator.netuid.in_([p.netuid for p in positions])
        )
        val_result = await db.execute(val_stmt)
        validators = val_result.scalars().all()
        # Create map of (hotkey, netuid) -> apy
        for v in validators:
            key = (v.hotkey, v.netuid)
            validator_apy_map[key] = v.apy

    # Calculate average APY for health scoring
    all_apys = [apy for apy in validator_apy_map.values() if apy and apy > 0]
    avg_apy = sum(all_apys) / len(all_apys) if all_apys else Decimal("0")

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

        # Calculate weight
        weight_pct = (pos.tao_value_mid / total_mid * 100) if total_mid else Decimal("0")

        # Get validator APY
        current_apy = None
        if pos.validator_hotkey and pos.netuid:
            current_apy = validator_apy_map.get((pos.validator_hotkey, pos.netuid))

        # Calculate daily yield
        daily_yield_tao = None
        if current_apy and current_apy > 0:
            daily_yield_tao = pos.tao_value_mid * current_apy / Decimal("100") / Decimal("365")

        # Compute health status
        health_status, health_reason = _compute_position_health(
            unrealized_pnl_pct=unrealized_pct,
            weight_pct=weight_pct,
            current_apy=current_apy,
            avg_apy=avg_apy,
        )

        enriched.append(PositionResponse(
            id=pos.id,
            wallet_address=pos.wallet_address,
            netuid=pos.netuid,
            alpha_balance=pos.alpha_balance,
            tao_value_mid=pos.tao_value_mid,
            tao_value_exec_50pct=pos.tao_value_exec_50pct,
            tao_value_exec_100pct=pos.tao_value_exec_100pct,
            weight_pct=weight_pct,
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
            current_apy=current_apy,
            daily_yield_tao=daily_yield_tao,
            health_status=health_status,
            health_reason=health_reason,
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

    # Calculate weight
    weight_pct = (pos.tao_value_mid / total_mid * 100) if total_mid else Decimal("0")

    # Get validator APY
    current_apy = None
    if pos.validator_hotkey:
        val_stmt = select(Validator).where(
            Validator.hotkey == pos.validator_hotkey,
            Validator.netuid == netuid,
        )
        val_result = await db.execute(val_stmt)
        validator = val_result.scalar_one_or_none()
        if validator:
            current_apy = validator.apy

    # Calculate daily yield
    daily_yield_tao = None
    if current_apy and current_apy > 0:
        daily_yield_tao = pos.tao_value_mid * current_apy / Decimal("100") / Decimal("365")

    # Get average APY for health scoring
    all_val_stmt = select(Validator.apy).where(
        Validator.netuid.in_([p.netuid for p in all_positions])
    )
    all_val_result = await db.execute(all_val_stmt)
    all_apys = [row[0] for row in all_val_result.fetchall() if row[0] and row[0] > 0]
    avg_apy = sum(all_apys) / len(all_apys) if all_apys else Decimal("0")

    # Compute health status
    health_status, health_reason = _compute_position_health(
        unrealized_pnl_pct=unrealized_pct,
        weight_pct=weight_pct,
        current_apy=current_apy,
        avg_apy=avg_apy,
    )

    return PositionResponse(
        id=pos.id,
        wallet_address=pos.wallet_address,
        netuid=pos.netuid,
        alpha_balance=pos.alpha_balance,
        tao_value_mid=pos.tao_value_mid,
        tao_value_exec_50pct=pos.tao_value_exec_50pct,
        tao_value_exec_100pct=pos.tao_value_exec_100pct,
        weight_pct=weight_pct,
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
        current_apy=current_apy,
        daily_yield_tao=daily_yield_tao,
        health_status=health_status,
        health_reason=health_reason,
        created_at=pos.created_at,
        updated_at=pos.updated_at,
    )
