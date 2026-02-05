"""Viability scoring configuration model.

Stores user-adjusted viability parameters in the database,
allowing on-the-fly tuning without editing config.py or restarting.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ViabilityConfig(Base):
    """Single-row active viability scoring configuration."""

    __tablename__ = "viability_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_name: Mapped[str] = mapped_column(String(255), default="default")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Hard failure thresholds
    min_tao_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    min_emission_share: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    min_age_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_holders: Mapped[int] = mapped_column(Integer, nullable=False)
    max_drawdown_30d: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    max_negative_flow_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    # Scored metric weights (must sum to 1.0)
    weight_tao_reserve: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_net_flow_7d: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_emission_share: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_price_trend_7d: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_subnet_age: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_max_drawdown_30d: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    # Tier boundaries
    tier_1_min: Mapped[int] = mapped_column(Integer, nullable=False)
    tier_2_min: Mapped[int] = mapped_column(Integer, nullable=False)
    tier_3_min: Mapped[int] = mapped_column(Integer, nullable=False)

    # Age cap
    age_cap_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # Feature flag
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
