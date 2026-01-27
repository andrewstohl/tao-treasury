"""Reconciliation models for data integrity verification.

Phase 2: Stores reconciliation run results comparing stored data vs live API.
"""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReconciliationRun(Base):
    """A single reconciliation run comparing stored vs live data.

    Records the overall result and detailed check results for each
    position/netuid comparison.
    """

    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Run identification
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Scope
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    netuids_checked: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Overall result
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Summary values
    total_stored_value_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )
    total_live_value_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )
    total_diff_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0")
    )
    total_diff_pct: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0")
    )

    # Detailed checks (JSON array of check results)
    checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Error info if run failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Tolerances used
    absolute_tolerance_tao: Mapped[Decimal] = mapped_column(
        Numeric(20, 9), nullable=False, default=Decimal("0.0001")
    )
    relative_tolerance_pct: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0.1")
    )

    __table_args__ = (
        Index("ix_reconciliation_runs_wallet_created", "wallet_address", "created_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "wallet_address": self.wallet_address,
            "netuids_checked": self.netuids_checked,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "total_stored_value_tao": str(self.total_stored_value_tao),
            "total_live_value_tao": str(self.total_live_value_tao),
            "total_diff_tao": str(self.total_diff_tao),
            "total_diff_pct": str(self.total_diff_pct),
            "checks": self.checks,
            "error_message": self.error_message,
            "tolerances": {
                "absolute_tao": str(self.absolute_tolerance_tao),
                "relative_pct": str(self.relative_tolerance_pct),
            },
        }

    def to_summary(self) -> dict:
        """Convert to summary dict for Trust Pack."""
        return {
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "failed_checks": self.failed_checks,
            "total_diff_pct": str(self.total_diff_pct),
        }
