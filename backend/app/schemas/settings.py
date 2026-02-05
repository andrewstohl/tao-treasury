"""Settings schemas for viability scoring configuration."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ViabilityConfigResponse(BaseModel):
    """Current viability scoring configuration."""

    id: Optional[int] = None
    config_name: str = "default"
    is_active: bool = True
    source: str = Field(
        default="defaults",
        description="Where these settings came from: 'database' or 'defaults'",
    )

    # Hard failure thresholds
    min_tao_reserve: Decimal
    min_emission_share: Decimal
    min_age_days: int
    min_holders: int
    max_drawdown_30d: Decimal
    max_negative_flow_ratio: Decimal

    # Scored metric weights
    weight_tao_reserve: Decimal
    weight_net_flow_7d: Decimal
    weight_emission_share: Decimal
    weight_price_trend_7d: Decimal
    weight_subnet_age: Decimal
    weight_max_drawdown_30d: Decimal

    # Tier boundaries
    tier_1_min: int
    tier_2_min: int
    tier_3_min: int

    # Age cap
    age_cap_days: int

    # Feature flag
    enabled: bool

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ViabilityConfigUpdateRequest(BaseModel):
    """Request to update viability scoring configuration."""

    config_name: Optional[str] = None

    # Hard failure thresholds
    min_tao_reserve: Optional[Decimal] = Field(default=None, ge=0)
    min_emission_share: Optional[Decimal] = Field(default=None, ge=0, le=1)
    min_age_days: Optional[int] = Field(default=None, ge=0)
    min_holders: Optional[int] = Field(default=None, ge=0)
    max_drawdown_30d: Optional[Decimal] = Field(default=None, ge=0, le=1)
    max_negative_flow_ratio: Optional[Decimal] = Field(default=None, ge=0, le=1)

    # Scored metric weights
    weight_tao_reserve: Optional[Decimal] = Field(default=None, ge=0, le=1)
    weight_net_flow_7d: Optional[Decimal] = Field(default=None, ge=0, le=1)
    weight_emission_share: Optional[Decimal] = Field(default=None, ge=0, le=1)
    weight_price_trend_7d: Optional[Decimal] = Field(default=None, ge=0, le=1)
    weight_subnet_age: Optional[Decimal] = Field(default=None, ge=0, le=1)
    weight_max_drawdown_30d: Optional[Decimal] = Field(default=None, ge=0, le=1)

    # Tier boundaries
    tier_1_min: Optional[int] = Field(default=None, ge=0, le=100)
    tier_2_min: Optional[int] = Field(default=None, ge=0, le=100)
    tier_3_min: Optional[int] = Field(default=None, ge=0, le=100)

    # Age cap
    age_cap_days: Optional[int] = Field(default=None, ge=1)

    # Feature flag
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "ViabilityConfigUpdateRequest":
        """If all six weights are provided, they must sum to 1.0."""
        weights = [
            self.weight_tao_reserve,
            self.weight_net_flow_7d,
            self.weight_emission_share,
            self.weight_price_trend_7d,
            self.weight_subnet_age,
            self.weight_max_drawdown_30d,
        ]
        if all(w is not None for w in weights):
            total = sum(w for w in weights if w is not None)
            if abs(total - Decimal("1.0")) > Decimal("0.001"):
                raise ValueError(
                    f"Weights must sum to 1.0 (got {total})"
                )
        return self

    @model_validator(mode="after")
    def validate_tier_ordering(self) -> "ViabilityConfigUpdateRequest":
        """If tier boundaries are provided, ensure tier_1 > tier_2 > tier_3."""
        t1, t2, t3 = self.tier_1_min, self.tier_2_min, self.tier_3_min
        if t1 is not None and t2 is not None and t1 <= t2:
            raise ValueError("tier_1_min must be greater than tier_2_min")
        if t2 is not None and t3 is not None and t2 <= t3:
            raise ValueError("tier_2_min must be greater than tier_3_min")
        return self
