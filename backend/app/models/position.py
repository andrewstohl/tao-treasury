"""Position and position snapshot models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
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


class Position(Base):
    """Current wallet position in a subnet."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    netuid: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    subnet_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Position size
    alpha_balance: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Valuation (TAO) - both mid and executable per spec
    tao_value_mid: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    tao_value_exec_50pct: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    tao_value_exec_100pct: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Entry tracking
    entry_price_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    entry_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cost_basis_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Alpha decomposition for proper yield vs price gain separation
    # alpha_purchased = net alpha purchased (from accounting/tax API token_swap)
    alpha_purchased: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    # total_yield_alpha = sum of daily_income from accounting/tax API (authoritative)
    total_yield_alpha: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Realized PnL tracking
    realized_pnl_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Unrealized PnL (computed: tao_value_mid - cost_basis_tao)
    unrealized_pnl_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    unrealized_pnl_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))

    # Decomposed yield and alpha P&L (single source of truth for ledger aggregation)
    # Yield = TAO earned from emissions (alpha that grew without purchasing)
    unrealized_yield_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    realized_yield_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    # Alpha P&L = price movement on purchased alpha
    unrealized_alpha_pnl_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    realized_alpha_pnl_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    # Total P&L verification fields (should equal yield + alpha_pnl)
    total_unrealized_pnl_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    total_realized_pnl_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Yield metrics (from validator data)
    current_apy: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    apy_30d_avg: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    daily_yield_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    weekly_yield_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Slippage estimates (computed from slippage surfaces)
    exit_slippage_50pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    exit_slippage_100pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Validator used for staking
    validator_hotkey: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Current recommendation from strategy engine
    recommended_action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    action_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_positions_wallet_netuid", "wallet_address", "netuid", unique=True),
    )


class PositionSnapshot(Base):
    """Historical position snapshot for tracking changes and backtesting."""

    __tablename__ = "position_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    netuid: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Position state
    alpha_balance: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    tao_value_mid: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    tao_value_exec_50pct: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    tao_value_exec_100pct: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Market state at snapshot
    alpha_price_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    __table_args__ = (
        Index("ix_position_snapshots_wallet_ts", "wallet_address", "timestamp"),
        Index("ix_position_snapshots_wallet_netuid_ts", "wallet_address", "netuid", "timestamp"),
    )
