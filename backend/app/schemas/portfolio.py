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


class YieldSummary(BaseModel):
    """Yield summary for portfolio."""
    portfolio_apy: Decimal = Field(default=Decimal("0"))
    daily_yield_tao: Decimal = Field(default=Decimal("0"))
    weekly_yield_tao: Decimal = Field(default=Decimal("0"))
    monthly_yield_tao: Decimal = Field(default=Decimal("0"))


class PnLSummary(BaseModel):
    """P&L summary for portfolio."""
    total_unrealized_pnl_tao: Decimal = Field(default=Decimal("0"))
    total_realized_pnl_tao: Decimal = Field(default=Decimal("0"))
    total_cost_basis_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_pct: Decimal = Field(default=Decimal("0"))


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

    # Yield metrics
    yield_summary: YieldSummary = Field(default_factory=YieldSummary)

    # P&L metrics
    pnl_summary: PnLSummary = Field(default_factory=PnLSummary)

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


class PositionSummary(BaseModel):
    """Position summary for API responses."""
    netuid: int
    subnet_name: str
    tao_value_mid: Decimal = Field(default=Decimal("0"))
    alpha_balance: Decimal = Field(default=Decimal("0"))
    weight_pct: Decimal = Field(default=Decimal("0"))
    # Yield
    current_apy: Decimal = Field(default=Decimal("0"))
    daily_yield_tao: Decimal = Field(default=Decimal("0"))
    # P&L
    cost_basis_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_pct: Decimal = Field(default=Decimal("0"))
    # Health status: green (good), yellow (needs attention), red (action required)
    health_status: str = "green"
    health_reason: Optional[str] = None
    # Status
    validator_hotkey: Optional[str] = None
    recommended_action: Optional[str] = None

    class Config:
        from_attributes = True


class ActionItem(BaseModel):
    """Single actionable recommendation."""
    priority: str  # "high", "medium", "low"
    action_type: str  # "rebalance", "take_profit", "cut_loss", "opportunity"
    title: str
    description: str
    subnet_id: Optional[int] = None
    potential_gain_tao: Optional[Decimal] = None


class AlertSummary(BaseModel):
    """Alert summary for dashboard."""
    critical: int = 0
    warning: int = 0
    info: int = 0


class PortfolioHealth(BaseModel):
    """Overall portfolio health assessment."""
    status: str = "green"  # green, yellow, red
    score: int = 100  # 0-100
    top_issue: Optional[str] = None
    issues_count: int = 0


class DashboardResponse(BaseModel):
    """Complete dashboard response."""
    portfolio: PortfolioSummary
    portfolio_health: PortfolioHealth = Field(default_factory=PortfolioHealth)
    top_positions: List[PositionSummary] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    alerts: AlertSummary
    pending_recommendations: int = 0
    urgent_recommendations: int = 0
    last_sync: Optional[datetime] = None
    data_stale: bool = False
    generated_at: datetime
