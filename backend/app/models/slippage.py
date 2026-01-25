"""Slippage surface model for executable pricing."""

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


class SlippageSurface(Base):
    """Cached slippage estimates by subnet, size, and action.

    Per spec: maintain slippage surfaces for stake/unstake at sizes
    2, 5, 10, 15, and optionally 20 TAO.
    """

    __tablename__ = "slippage_surfaces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    netuid: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Action type: stake (buy alpha) or unstake (sell alpha)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # stake, unstake

    # Trade size in TAO
    size_tao: Mapped[Decimal] = mapped_column(Numeric(20, 9), nullable=False)

    # Slippage percentage (0.01 = 1%)
    slippage_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))

    # Expected output after slippage
    expected_output: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Pool state at computation time (for validation)
    pool_tao_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))
    pool_alpha_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 9), default=Decimal("0"))

    # Timestamps
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_slippage_netuid_action_size", "netuid", "action", "size_tao"),
        Index("ix_slippage_computed", "computed_at"),
    )
