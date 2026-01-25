"""Decision log model for full auditability."""

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


class DecisionLog(Base):
    """Full audit log for all recommendations and decisions.

    Per spec: every recommendation must reference the data snapshot used
    and show the full reasoning chain.
    """

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Decision context
    decision_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # trade_recommendation, rebalance, exit_trigger, regime_change, eligibility_update

    # Related entities
    wallet_address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    netuid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Decision output
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # buy, sell, hold, trim, exit

    # Full reasoning chain (per spec: for auditability)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    # All input factors used in decision (immutable snapshot)
    input_factors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Example structure:
    # {
    #   "nav_executable": "1000.5",
    #   "flow_regime": "risk_off",
    #   "flow_1d": "-0.02",
    #   "flow_7d": "-0.05",
    #   "exit_slippage_50pct": "0.03",
    #   "exit_slippage_100pct": "0.07",
    #   "position_size_tao": "50.0",
    #   "position_weight_pct": "0.05",
    #   "liquidity_tao": "5000",
    #   "emission_share": "0.02",
    #   "holder_count": 150,
    #   "eligibility_checks": {...}
    # }

    # Rule/model that generated decision
    rule_triggered: Mapped[str] = mapped_column(String(128), nullable=False)
    # Examples: "taoflow_regime_exit", "max_slippage_breach", "weekly_rebalance",
    #           "quarantine_trim", "eligibility_fail"

    # Computed output values
    computed_outputs: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Example: {"recommended_size_tao": "25.0", "estimated_slippage": "0.02", ...}

    # Recommended trade details (if applicable)
    recommended_size_tao: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 9), nullable=True)
    recommended_size_alpha: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 9), nullable=True)
    estimated_slippage: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    estimated_cost_tao: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 9), nullable=True)

    # Execution tracking
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Data snapshot reference
    data_snapshot_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_decision_logs_type_created", "decision_type", "created_at"),
        Index("ix_decision_logs_wallet_created", "wallet_address", "created_at"),
        Index("ix_decision_logs_netuid_created", "netuid", "created_at"),
    )
