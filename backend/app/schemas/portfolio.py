"""Portfolio schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class AllocationBreakdown(BaseModel):
    """Allocation breakdown by type."""
    root_tao: Decimal = Field(default=Decimal("0"))
    root_pct: Decimal = Field(default=Decimal("0"))
    dtao_tao: Decimal = Field(default=Decimal("0"))
    dtao_pct: Decimal = Field(default=Decimal("0"))
    unstaked_tao: Decimal = Field(default=Decimal("0"))
    unstaked_pct: Decimal = Field(default=Decimal("0"))


class PortfolioSummary(BaseModel):
    """Portfolio summary for API responses."""
    wallet_address: str

    # NAV values (TAO)
    nav_mid: Decimal = Field(default=Decimal("0"))
    nav_exec_50pct: Decimal = Field(default=Decimal("0"))
    nav_exec_100pct: Decimal = Field(default=Decimal("0"))

    # USD values (informational only)
    tao_price_usd: Decimal = Field(default=Decimal("0"))
    nav_usd: Decimal = Field(default=Decimal("0"))

    # Allocation
    allocation: AllocationBreakdown

    # Risk metrics
    executable_drawdown_pct: Decimal = Field(default=Decimal("0"))
    drawdown_from_ath_pct: Decimal = Field(default=Decimal("0"))
    nav_ath: Decimal = Field(default=Decimal("0"))

    # Position counts
    active_positions: int = 0
    eligible_subnets: int = 0

    # Regime
    overall_regime: str = "neutral"

    # Turnover
    daily_turnover_pct: Decimal = Field(default=Decimal("0"))
    weekly_turnover_pct: Decimal = Field(default=Decimal("0"))

    # Timestamp
    as_of: datetime

    class Config:
        from_attributes = True


class PortfolioHistoryPoint(BaseModel):
    """Single point in portfolio history."""
    date: datetime
    nav_mid: Decimal
    nav_exec: Decimal
    nav_ath: Decimal
    drawdown_pct: Decimal
    daily_return_pct: Decimal


class PortfolioHistoryResponse(BaseModel):
    """Portfolio history response."""
    wallet_address: str
    history: List[PortfolioHistoryPoint]
    total_days: int
    cumulative_return_pct: Decimal
    max_drawdown_pct: Decimal


class AlertSummary(BaseModel):
    """Alert summary for dashboard."""
    critical: int = 0
    warning: int = 0
    info: int = 0


class DashboardResponse(BaseModel):
    """Complete dashboard response."""
    portfolio: PortfolioSummary
    alerts: AlertSummary
    pending_recommendations: int = 0
    urgent_recommendations: int = 0
    last_sync: Optional[datetime] = None
    data_stale: bool = False
    generated_at: datetime
