"""Position schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class PositionResponse(BaseModel):
    """Position response with full details."""
    id: int
    wallet_address: str
    netuid: int

    # Position size
    alpha_balance: Decimal = Field(default=Decimal("0"))

    # Valuation (TAO)
    tao_value_mid: Decimal = Field(default=Decimal("0"))
    tao_value_exec_50pct: Decimal = Field(default=Decimal("0"))
    tao_value_exec_100pct: Decimal = Field(default=Decimal("0"))

    # Weight in portfolio
    weight_pct: Decimal = Field(default=Decimal("0"))

    # Entry tracking
    entry_price_tao: Decimal = Field(default=Decimal("0"))
    entry_date: Optional[datetime] = None
    cost_basis_tao: Decimal = Field(default=Decimal("0"))

    # PnL
    realized_pnl_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_pct: Decimal = Field(default=Decimal("0"))

    # Slippage
    exit_slippage_50pct: Decimal = Field(default=Decimal("0"))
    exit_slippage_100pct: Decimal = Field(default=Decimal("0"))

    # Validator
    validator_hotkey: Optional[str] = None

    # Recommendation
    recommended_action: Optional[str] = None
    action_reason: Optional[str] = None

    # Subnet info (denormalized)
    subnet_name: Optional[str] = None
    flow_regime: Optional[str] = None
    emission_share: Optional[Decimal] = None

    # Yield metrics
    current_apy: Optional[Decimal] = None
    daily_yield_tao: Optional[Decimal] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PositionListResponse(BaseModel):
    """Response for position list endpoint."""
    positions: List[PositionResponse]
    total: int
    total_tao_value_mid: Decimal
    total_tao_value_exec: Decimal
