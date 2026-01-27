"""Signal run storage model for Phase 3.

Stores signal execution results for history and audit.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SignalRun(Base):
    """A single signal execution result.

    Records the output of running a signal for history and debugging.
    """

    __tablename__ = "signal_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Run identification
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Signal identification
    signal_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signal_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Status: ok, degraded, blocked
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Confidence: low, medium, high
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Output
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)

    # Evidence (metrics, numbers, windows)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Guardrails triggered
    guardrails_triggered: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Full payload for debugging
    full_output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Input versioning
    inputs_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Error if failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_signal_runs_signal_created", "signal_id", "created_at"),
        Index("ix_signal_runs_created", "created_at"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "signal_id": self.signal_id,
            "signal_name": self.signal_name,
            "status": self.status,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "summary": self.summary,
            "recommended_action": self.recommended_action,
            "evidence": self.evidence,
            "guardrails_triggered": self.guardrails_triggered,
            "error_message": self.error_message,
        }

    def to_summary(self) -> dict:
        """Convert to summary dict."""
        return {
            "signal_id": self.signal_id,
            "signal_name": self.signal_name,
            "status": self.status,
            "confidence": self.confidence,
            "summary": self.summary,
            "guardrails_count": len(self.guardrails_triggered),
        }
