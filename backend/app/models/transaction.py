"""Stake transaction model for tracking historical buys/sells."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StakeTransaction(Base):
    """Individual stake/unstake transaction record.

    Used to compute:
    - True weighted average entry price
    - Cost basis per position
    - Realized P&L on sells
    - Fee attribution
    """

    __tablename__ = "stake_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Transaction identification
    wallet_address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extrinsic_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=True)

    # Transaction type
    tx_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'stake', 'unstake', 'unstake_all'
    call_name: Mapped[str] = mapped_column(String(64), nullable=False)  # Full call name from extrinsic

    # Position details
    netuid: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    hotkey: Mapped[str] = mapped_column(String(64), nullable=True)  # Validator hotkey

    # Amounts (in TAO, converted from rao)
    amount_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Amount staked/unstaked in TAO

    alpha_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=True
    )  # Alpha tokens received (stake) or sold (unstake)

    # USD value at time of transaction
    usd_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=True
    )  # USD value at time of trade

    # Pricing
    limit_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=True
    )  # Effective price (TAO per alpha)
    execution_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=True
    )  # Actual execution price if available

    # Fees
    fee_rao: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    fee_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )

    # Transaction status
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # Raw data for debugging
    raw_args: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_stake_tx_wallet_netuid", "wallet_address", "netuid"),
        Index("ix_stake_tx_wallet_type", "wallet_address", "tx_type"),
        Index("ix_stake_tx_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<StakeTransaction {self.tx_type} {self.amount_tao} TAO on SN{self.netuid}>"


class PositionCostBasis(Base):
    """Computed cost basis for a position.

    Derived from aggregating all stake transactions.
    Updated whenever new transactions are synced.
    """

    __tablename__ = "position_cost_basis"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    wallet_address: Mapped[str] = mapped_column(String(64), nullable=False)
    netuid: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Cost basis metrics
    total_staked_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Total TAO ever staked into this position
    total_unstaked_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Total TAO ever unstaked from this position
    net_invested_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Net TAO invested (staked - unstaked at cost)

    # Weighted average entry price
    weighted_avg_entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Weighted average price paid per alpha

    # Realized P&L
    realized_pnl_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Realized gains/losses from unstaking

    # Fee tracking
    total_fees_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )

    # Transaction counts
    stake_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unstake_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # First and last transaction dates
    first_stake_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_transaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Last computation
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_cost_basis_wallet_netuid", "wallet_address", "netuid", unique=True),
    )

    def __repr__(self) -> str:
        return f"<PositionCostBasis SN{self.netuid} avg_price={self.weighted_avg_entry_price}>"
