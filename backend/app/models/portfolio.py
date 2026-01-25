"""Portfolio-level models."""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioSnapshot(Base):
    """Portfolio-level snapshot with NAV and risk metrics."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # NAV (TAO-denominated) - per spec: mid for diagnostics, executable for risk
    total_tao_balance: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_mid: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_exec_50pct: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_exec_100pct: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # USD values (informational only per spec)
    tao_price_usd: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))

    # Allocation breakdown (per spec: root, dtao sleeve, unstaked buffer)
    root_allocation_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    dtao_allocation_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    unstaked_buffer_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Risk metrics
    executable_drawdown: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    drawdown_from_ath: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Position counts
    active_positions: Mapped[int] = mapped_column(Integer, default=0)
    eligible_subnets: Mapped[int] = mapped_column(Integer, default=0)

    # Regime summary
    overall_regime: Mapped[str] = mapped_column(String(32), default="neutral")

    # Turnover tracking
    daily_turnover: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    weekly_turnover: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    __table_args__ = (
        Index("ix_portfolio_snapshots_wallet_ts", "wallet_address", "timestamp"),
    )


class NAVHistory(Base):
    """Daily NAV history for drawdown calculations and performance tracking."""

    __tablename__ = "nav_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Daily NAV values (OHLC style for precise drawdown)
    nav_mid_open: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_mid_high: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_mid_low: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_mid_close: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    nav_exec_open: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_exec_high: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_exec_low: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    nav_exec_close: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # All-time high tracking for drawdown
    nav_exec_ath: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Daily returns
    daily_return_tao: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    daily_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    __table_args__ = (
        Index("ix_nav_history_wallet_date", "wallet_address", "date", unique=True),
    )
