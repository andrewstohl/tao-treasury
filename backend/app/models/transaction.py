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
    )  # Realized gains/losses from unstaking (total: price gain + yield)

    # Realized yield decomposition — separates emission yield from price gain
    # so that yield survives position closure (Position rows get deleted).
    realized_yield_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # TAO value of emission alpha realized on unstakes
    realized_yield_alpha: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # Emission alpha tokens realized on unstakes

    # Fee tracking
    total_fees_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )

    # USD Cost Basis Tracking (for FX/Conversion Exposure)
    usd_cost_basis: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # Net invested USD (total_staked_usd - total_unstaked_usd)
    weighted_avg_entry_price_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # Weighted avg USD per alpha at entry
    total_staked_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # Total USD ever staked into this position
    total_unstaked_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # Total USD received from unstaking
    realized_pnl_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0"),
        server_default="0",
    )  # Realized P&L in USD terms

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


class DelegationEvent(Base):
    """Delegation event record from TaoStats delegation API.

    Tracks staking/unstaking events with their associated yields.
    Used for:
    - Accurate yield tracking (actual rewards received)
    - Historical income analysis
    - Cost basis validation
    """

    __tablename__ = "delegation_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Event identification
    wallet_address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Event type
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'stake', 'unstake', 'reward'
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # Full action name

    # Position details
    netuid: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    hotkey: Mapped[str] = mapped_column(String(64), nullable=True)

    # Amounts
    amount_rao: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )
    alpha_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=True
    )

    # Value at time of event
    tao_price_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    usd_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # Yield/reward info (for reward events)
    is_reward: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reward_source: Mapped[str] = mapped_column(String(32), nullable=True)  # 'emission', 'dividend', etc.

    # Raw data
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_delegation_events_wallet_netuid", "wallet_address", "netuid"),
        Index("ix_delegation_events_wallet_type", "wallet_address", "event_type"),
        Index("ix_delegation_events_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<DelegationEvent {self.event_type} {self.amount_tao} TAO on SN{self.netuid}>"


class PositionYieldHistory(Base):
    """Daily yield history for a position.

    Tracks actual yield received per position per day.
    Computed from stake balance history changes.
    """

    __tablename__ = "position_yield_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    wallet_address: Mapped[str] = mapped_column(String(64), nullable=False)
    netuid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Balance at start and end of day
    alpha_balance_start: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )
    alpha_balance_end: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )

    # TAO values
    tao_value_start: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )
    tao_value_end: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )

    # Computed yield for the day
    yield_alpha: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # Alpha tokens earned
    yield_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )  # TAO value of yield

    # Net staking activity (positive = added, negative = removed)
    net_stake_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )

    # Annualized yield for this day
    daily_apy: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_position_yield_wallet_netuid_date", "wallet_address", "netuid", "date", unique=True),
    )
