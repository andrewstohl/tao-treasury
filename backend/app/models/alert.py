"""Alert and acknowledgement models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
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


class Alert(Base):
    """System alerts for risk events and recommendations.

    Per spec: every alert must reference the data snapshot used.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Alert classification
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )  # critical, warning, info
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # drawdown, liquidity, taoflow, rebalance, regime_change, etc.

    # Alert content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Related entities
    wallet_address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    netuid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Metrics snapshot at alert time (per spec: for auditability)
    metrics_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    data_snapshot_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Threshold that triggered the alert
    threshold_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 9), nullable=True)
    actual_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 9), nullable=True)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Resolution
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_alerts_active_severity", "is_active", "severity"),
        Index("ix_alerts_created", "created_at"),
    )


class AlertAcknowledgement(Base):
    """Audit log for alert acknowledgements."""

    __tablename__ = "alert_acknowledgements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("alerts.id"), nullable=False, index=True
    )

    # Action taken
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # acknowledged, dismissed, resolved
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Who and when
    acknowledged_by: Mapped[str] = mapped_column(String(128), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_alert_acks_alert_id", "alert_id"),
    )
