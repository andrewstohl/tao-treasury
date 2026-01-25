"""Trade recommendation model."""

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


class TradeRecommendation(Base):
    """Recommended trades from strategy engine.

    Per spec: recommendations only, no auto-execution.
    Includes exit ladder support (tranches).
    """

    __tablename__ = "trade_recommendations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Context
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    netuid: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Trade details
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # buy, sell

    # Sizing
    size_alpha: Mapped[Decimal] = mapped_column(Numeric(20, 9), nullable=False)
    size_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), nullable=False)
    size_pct_of_position: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("1.0"))

    # Expected costs (per spec: show estimated execution costs)
    estimated_slippage_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    estimated_slippage_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    estimated_fee_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    total_estimated_cost_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Expected impact
    expected_nav_impact_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Reasoning (per spec: full audit trail)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # scheduled_rebalance, event_driven_exit, opportunity_entry, risk_reduction,
    # quarantine_trim, dead_exit, regime_shift
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Priority (for ordering when multiple trades)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Exit ladder support (per spec: tranches)
    tranche_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tranches: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_recommendation_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # State
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )  # pending, approved, rejected, executed, expired, cancelled

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Links
    decision_log_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    data_snapshot_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Manual execution tracking (per spec: no auto-execution)
    marked_executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_slippage_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    execution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_trade_recs_wallet_status", "wallet_address", "status"),
        Index("ix_trade_recs_created", "created_at"),
        Index("ix_trade_recs_netuid_status", "netuid", "status"),
    )
