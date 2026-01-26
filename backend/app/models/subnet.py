"""Subnet and subnet snapshot models."""

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
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subnet(Base):
    """Subnet metadata and current state."""

    __tablename__ = "subnets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    netuid: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ownership and governance
    owner_address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    owner_take: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Registration and age
    registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    age_days: Mapped[int] = mapped_column(Integer, default=0)

    # Current metrics
    emission_share: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    total_stake_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # dTAO pool metrics
    pool_tao_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    pool_alpha_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    alpha_price_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Holder metrics
    holder_count: Mapped[int] = mapped_column(Integer, default=0)

    # Taoflow metrics (multi-horizon per spec)
    taoflow_1d: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    taoflow_3d: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    taoflow_7d: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    taoflow_14d: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Flow regime (state machine per spec)
    flow_regime: Mapped[str] = mapped_column(
        String(32), default="neutral"
    )  # risk_on, neutral, risk_off, quarantine, dead
    flow_regime_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    flow_regime_days: Mapped[int] = mapped_column(Integer, default=0)

    # Regime persistence tracking (anti-whipsaw)
    # Stores the "candidate" regime that would be assigned without persistence requirement
    regime_candidate: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    regime_candidate_days: Mapped[int] = mapped_column(Integer, default=0)

    # Validator info
    top_validator_hotkey: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    validator_apy: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Universe eligibility
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    ineligibility_reasons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Category for concentration limits
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_subnets_eligible_netuid", "is_eligible", "netuid"),
        Index("ix_subnets_flow_regime", "flow_regime"),
    )


class SubnetSnapshot(Base):
    """Historical subnet metrics snapshot for backtesting and analysis."""

    __tablename__ = "subnet_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    netuid: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Price and liquidity
    alpha_price_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    pool_tao_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    pool_alpha_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Emissions
    emission_share: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Taoflow
    taoflow_net: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Holders
    holder_count: Mapped[int] = mapped_column(Integer, default=0)

    # Validator yield
    validator_apy: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Flow regime at snapshot time
    flow_regime: Mapped[str] = mapped_column(String(32), default="neutral")

    __table_args__ = (
        Index("ix_subnet_snapshots_netuid_ts", "netuid", "timestamp"),
    )
