"""Subnet schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class SubnetResponse(BaseModel):
    """Subnet response with full details."""
    id: int
    netuid: int
    name: str
    description: Optional[str] = None

    # Ownership
    owner_address: Optional[str] = None
    owner_take: Decimal = Field(default=Decimal("0"))

    # Age
    registered_at: Optional[datetime] = None
    age_days: int = 0

    # Metrics
    emission_share: Decimal = Field(default=Decimal("0"))
    total_stake_tao: Decimal = Field(default=Decimal("0"))

    # Pool metrics
    pool_tao_reserve: Decimal = Field(default=Decimal("0"))
    pool_alpha_reserve: Decimal = Field(default=Decimal("0"))
    alpha_price_tao: Decimal = Field(default=Decimal("0"))

    # Holders
    holder_count: int = 0

    # Taoflow
    taoflow_1d: Decimal = Field(default=Decimal("0"))
    taoflow_3d: Decimal = Field(default=Decimal("0"))
    taoflow_7d: Decimal = Field(default=Decimal("0"))
    taoflow_14d: Decimal = Field(default=Decimal("0"))

    # Regime
    flow_regime: str = "neutral"
    flow_regime_since: Optional[datetime] = None

    # Validator
    validator_apy: Decimal = Field(default=Decimal("0"))

    # Eligibility
    is_eligible: bool = False
    ineligibility_reasons: Optional[str] = None
    category: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubnetListResponse(BaseModel):
    """Response for subnet list endpoint."""
    subnets: List[SubnetResponse]
    total: int
    eligible_count: int
