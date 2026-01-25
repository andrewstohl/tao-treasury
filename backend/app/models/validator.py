"""Validator model for tracking validator metrics and yields."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Validator(Base):
    """Validator metrics and yields for staking decisions."""

    __tablename__ = "validators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotkey: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    netuid: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Validator identity
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    coldkey: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Performance metrics
    vtrust: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    stake_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Take rate (per spec: validator quality check)
    take_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Yield metrics
    apy: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    apy_7d_avg: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    apy_30d_avg: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Emissions
    daily_emissions_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Quality flags (for eligibility filtering)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meets_vtrust_floor: Mapped[bool] = mapped_column(Boolean, default=False)
    meets_take_cap: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_validators_hotkey_netuid", "hotkey", "netuid", unique=True),
        Index("ix_validators_netuid_active", "netuid", "is_active"),
    )
