"""Portfolio schemas."""

import math
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
    tao_value_exec_50pct: Decimal = Field(default=Decimal("0"))
    tao_value_exec_100pct: Decimal = Field(default=Decimal("0"))
    alpha_balance: Decimal = Field(default=Decimal("0"))
    weight_pct: Decimal = Field(default=Decimal("0"))
    # Entry tracking
    entry_price_tao: Decimal = Field(default=Decimal("0"))
    entry_date: Optional[datetime] = None
    # Yield
    current_apy: Decimal = Field(default=Decimal("0"))
    daily_yield_tao: Decimal = Field(default=Decimal("0"))
    # P&L
    cost_basis_tao: Decimal = Field(default=Decimal("0"))
    realized_pnl_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_tao: Decimal = Field(default=Decimal("0"))
    unrealized_pnl_pct: Decimal = Field(default=Decimal("0"))
    # Slippage
    exit_slippage_50pct: Decimal = Field(default=Decimal("0"))
    exit_slippage_100pct: Decimal = Field(default=Decimal("0"))
    # Status & recommendation
    validator_hotkey: Optional[str] = None
    recommended_action: Optional[str] = None
    action_reason: Optional[str] = None
    # Subnet context
    flow_regime: Optional[str] = None
    emission_share: Optional[Decimal] = None

    class Config:
        from_attributes = True


class ClosedPositionSummary(BaseModel):
    """Summary of a closed (fully exited) position."""
    netuid: int
    subnet_name: str
    total_staked_tao: Decimal = Field(default=Decimal("0"))
    total_unstaked_tao: Decimal = Field(default=Decimal("0"))
    realized_pnl_tao: Decimal = Field(default=Decimal("0"))
    first_entry: Optional[datetime] = None
    last_trade: Optional[datetime] = None


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


class MarketPulse(BaseModel):
    """Aggregated market data for held positions."""
    portfolio_24h_change_pct: Optional[Decimal] = None
    portfolio_7d_change_pct: Optional[Decimal] = None
    avg_sentiment_index: Optional[Decimal] = None
    avg_sentiment_label: Optional[str] = None
    total_volume_24h_tao: Optional[Decimal] = None
    net_buy_pressure_pct: Optional[Decimal] = None
    top_mover_netuid: Optional[int] = None
    top_mover_name: Optional[str] = None
    top_mover_change_24h: Optional[Decimal] = None
    taostats_available: bool = False


class DashboardResponse(BaseModel):
    """Complete dashboard response."""
    portfolio: PortfolioSummary
    wallets: List[str] = Field(default_factory=list, description="List of all active wallet addresses")
    top_positions: List[PositionSummary] = Field(default_factory=list)
    closed_positions: List[ClosedPositionSummary] = Field(default_factory=list)
    free_tao_balance: Decimal = Field(default=Decimal("0"))
    action_items: List[ActionItem] = Field(default_factory=list)
    alerts: AlertSummary
    market_pulse: Optional[MarketPulse] = None
    pending_recommendations: int = 0
    urgent_recommendations: int = 0
    last_sync: Optional[datetime] = None
    data_stale: bool = False
    generated_at: datetime


# ---------------------------------------------------------------------------
# Phase 1 – Portfolio Overview (dual-currency, rolling returns, projections)
# ---------------------------------------------------------------------------

class RollingReturn(BaseModel):
    """Rolling return for a specific look-back period."""
    period: str  # "1d", "7d", "30d", "90d", "inception"
    return_pct: Optional[Decimal] = None
    return_tao: Optional[Decimal] = None
    nav_start: Optional[Decimal] = None
    nav_end: Optional[Decimal] = None
    data_points: int = 0


class TaoPriceContext(BaseModel):
    """TAO spot price with recent changes."""
    price_usd: Decimal = Field(default=Decimal("0"))
    change_24h_pct: Optional[Decimal] = None
    change_7d_pct: Optional[Decimal] = None


class DualCurrencyValue(BaseModel):
    """A value expressed in both TAO and USD."""
    tao: Decimal = Field(default=Decimal("0"))
    usd: Decimal = Field(default=Decimal("0"))


class ConversionExposure(BaseModel):
    """FX / Conversion exposure metrics.

    Tracks the full USD P&L journey from stake time to present,
    decomposed into:
    - Alpha/TAO effect: P&L from alpha price changes relative to TAO
    - TAO/USD effect: P&L from TAO price changes relative to USD

    For Root (SN0) positions: alpha_tao_effect = 0 (no conversion, still TAO).
    """
    # Cost basis (at stake time)
    usd_cost_basis: Decimal = Field(default=Decimal("0"))  # What you put in (USD)
    tao_cost_basis: Decimal = Field(default=Decimal("0"))  # What you put in (TAO)

    # Current value
    current_usd_value: Decimal = Field(default=Decimal("0"))  # What you have now (USD)
    current_tao_value: Decimal = Field(default=Decimal("0"))  # What you have now (TAO)

    # Total P&L
    total_pnl_usd: Decimal = Field(default=Decimal("0"))
    total_pnl_pct: Decimal = Field(default=Decimal("0"))

    # Decomposition
    alpha_tao_effect_usd: Decimal = Field(default=Decimal("0"))  # P&L from α/τ movement
    tao_usd_effect: Decimal = Field(default=Decimal("0"))  # P&L from τ/$ movement

    # Entry reference
    weighted_avg_entry_tao_price_usd: Decimal = Field(default=Decimal("0"))

    # Data quality indicators
    has_complete_usd_history: bool = False
    positions_with_usd_data: int = 0
    positions_with_cost_basis: int = 0  # Positions with valid cost basis for FX calc
    positions_excluded_from_fx: List[int] = Field(default_factory=list)  # Netuids excluded
    total_positions: int = 0


class OverviewPnL(BaseModel):
    """P&L summary in both TAO and USD."""
    unrealized: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    realized: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    total: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    cost_basis: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    total_pnl_pct: Decimal = Field(default=Decimal("0"))


class OverviewYield(BaseModel):
    """Yield / income metrics in both currencies."""
    daily: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    weekly: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    monthly: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    annualized: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    portfolio_apy: Decimal = Field(default=Decimal("0"))
    # Cumulative and period-specific actual yield from PositionYieldHistory
    cumulative_tao: Decimal = Field(default=Decimal("0"))
    yield_1d_tao: Decimal = Field(default=Decimal("0"))
    yield_7d_tao: Decimal = Field(default=Decimal("0"))
    yield_30d_tao: Decimal = Field(default=Decimal("0"))
    # Yield decomposition: total = unrealized (open positions) + realized (closed)
    total_yield: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    unrealized_yield: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    realized_yield: DualCurrencyValue = Field(default_factory=DualCurrencyValue)


class CompoundingProjection(BaseModel):
    """Forward yield projection using current APY with compounding."""
    current_nav_tao: Decimal = Field(default=Decimal("0"))
    current_apy: Decimal = Field(default=Decimal("0"))
    # Simple (linear) projections
    projected_30d_tao: Decimal = Field(default=Decimal("0"))
    projected_90d_tao: Decimal = Field(default=Decimal("0"))
    projected_365d_tao: Decimal = Field(default=Decimal("0"))
    # Continuously compounded projections
    compounded_30d_tao: Decimal = Field(default=Decimal("0"))
    compounded_90d_tao: Decimal = Field(default=Decimal("0"))
    compounded_365d_tao: Decimal = Field(default=Decimal("0"))
    # Growth factor: portfolio value after 12m compounding
    projected_nav_365d_tao: Decimal = Field(default=Decimal("0"))


class PortfolioOverviewResponse(BaseModel):
    """Enhanced portfolio overview – Phase 1 endpoint."""

    # Current NAV in both variants and currencies
    nav_mid: DualCurrencyValue = Field(default_factory=DualCurrencyValue)
    nav_exec: DualCurrencyValue = Field(default_factory=DualCurrencyValue)

    # TAO spot price context
    tao_price: TaoPriceContext = Field(default_factory=TaoPriceContext)

    # Rolling returns – computed from NAVHistory
    returns_mid: List[RollingReturn] = Field(default_factory=list)
    returns_exec: List[RollingReturn] = Field(default_factory=list)

    # P&L (dual currency)
    pnl: OverviewPnL = Field(default_factory=OverviewPnL)

    # Yield / Income (dual currency)
    yield_income: OverviewYield = Field(default_factory=OverviewYield)

    # Compounding projection
    compounding: CompoundingProjection = Field(default_factory=CompoundingProjection)

    # High-water mark
    nav_ath_tao: Decimal = Field(default=Decimal("0"))
    drawdown_from_ath_pct: Decimal = Field(default=Decimal("0"))

    # Portfolio context
    active_positions: int = 0
    eligible_subnets: int = 0
    overall_regime: str = "neutral"

    # FX / Conversion Exposure
    conversion_exposure: ConversionExposure = Field(default_factory=ConversionExposure)

    as_of: datetime


# ---------------------------------------------------------------------------
# Phase 2 – Performance Attribution & Income Analysis
# ---------------------------------------------------------------------------

class WaterfallStep(BaseModel):
    """Single step in a return decomposition waterfall."""
    label: str
    value_tao: Decimal = Field(default=Decimal("0"))
    is_total: bool = False


class PositionContribution(BaseModel):
    """One position's contribution to portfolio return."""
    netuid: int
    subnet_name: str
    start_value_tao: Decimal = Field(default=Decimal("0"))
    return_tao: Decimal = Field(default=Decimal("0"))
    return_pct: Decimal = Field(default=Decimal("0"))
    yield_tao: Decimal = Field(default=Decimal("0"))
    price_effect_tao: Decimal = Field(default=Decimal("0"))
    weight_pct: Decimal = Field(default=Decimal("0"))
    contribution_pct: Decimal = Field(default=Decimal("0"))


class IncomeStatement(BaseModel):
    """Period income statement."""
    yield_income_tao: Decimal = Field(default=Decimal("0"))
    realized_gains_tao: Decimal = Field(default=Decimal("0"))
    fees_tao: Decimal = Field(default=Decimal("0"))
    net_income_tao: Decimal = Field(default=Decimal("0"))


class AttributionResponse(BaseModel):
    """Performance attribution response – Phase 2 endpoint."""
    period_days: int
    start: datetime
    end: datetime

    # Portfolio NAV at start and end of period
    nav_start_tao: Decimal = Field(default=Decimal("0"))
    nav_end_tao: Decimal = Field(default=Decimal("0"))

    # Total return (flow-adjusted)
    total_return_tao: Decimal = Field(default=Decimal("0"))
    total_return_pct: Decimal = Field(default=Decimal("0"))

    # Decomposition
    yield_income_tao: Decimal = Field(default=Decimal("0"))
    yield_income_pct: Decimal = Field(default=Decimal("0"))
    price_effect_tao: Decimal = Field(default=Decimal("0"))
    price_effect_pct: Decimal = Field(default=Decimal("0"))
    fees_tao: Decimal = Field(default=Decimal("0"))
    fees_pct: Decimal = Field(default=Decimal("0"))
    net_flows_tao: Decimal = Field(default=Decimal("0"))

    # Waterfall chart data
    waterfall: List[WaterfallStep] = Field(default_factory=list)

    # Position-level contribution
    position_contributions: List[PositionContribution] = Field(default_factory=list)

    # Income statement
    income_statement: IncomeStatement = Field(default_factory=IncomeStatement)


# ---------------------------------------------------------------------------
# Phase 3 – TAO Price Sensitivity & Scenario Analysis
# ---------------------------------------------------------------------------

class SensitivityPoint(BaseModel):
    """Portfolio value at a specific TAO price shock."""
    shock_pct: int
    tao_price_usd: Decimal = Field(default=Decimal("0"))
    nav_tao: Decimal = Field(default=Decimal("0"))
    nav_usd: Decimal = Field(default=Decimal("0"))
    usd_change: Decimal = Field(default=Decimal("0"))
    usd_change_pct: Decimal = Field(default=Decimal("0"))


class StressScenario(BaseModel):
    """Result of a pre-built stress scenario."""
    id: str
    name: str
    description: str
    tao_price_change_pct: int
    alpha_impact_pct: int
    new_tao_price_usd: Decimal = Field(default=Decimal("0"))
    nav_tao: Decimal = Field(default=Decimal("0"))
    nav_usd: Decimal = Field(default=Decimal("0"))
    tao_impact: Decimal = Field(default=Decimal("0"))
    usd_impact: Decimal = Field(default=Decimal("0"))
    usd_impact_pct: Decimal = Field(default=Decimal("0"))


class AllocationExposure(BaseModel):
    """Portfolio allocation for risk exposure."""
    root_tao: Decimal = Field(default=Decimal("0"))
    root_pct: Decimal = Field(default=Decimal("0"))
    dtao_tao: Decimal = Field(default=Decimal("0"))
    dtao_pct: Decimal = Field(default=Decimal("0"))
    unstaked_tao: Decimal = Field(default=Decimal("0"))


class RiskExposure(BaseModel):
    """Portfolio risk exposure summary."""
    tao_beta: Decimal = Field(default=Decimal("1.0"))
    dtao_weight_pct: Decimal = Field(default=Decimal("0"))
    root_weight_pct: Decimal = Field(default=Decimal("0"))
    total_exit_slippage_pct: Decimal = Field(default=Decimal("0"))
    total_exit_slippage_tao: Decimal = Field(default=Decimal("0"))
    note: str = ""


class ScenarioResponse(BaseModel):
    """TAO price sensitivity and scenario analysis – Phase 3 endpoint."""
    current_tao_price_usd: Decimal = Field(default=Decimal("0"))
    nav_tao: Decimal = Field(default=Decimal("0"))
    nav_usd: Decimal = Field(default=Decimal("0"))
    allocation: AllocationExposure = Field(default_factory=AllocationExposure)
    sensitivity: List[SensitivityPoint] = Field(default_factory=list)
    scenarios: List[StressScenario] = Field(default_factory=list)
    risk_exposure: RiskExposure = Field(default_factory=RiskExposure)


# ---------------------------------------------------------------------------
# Phase 4 – Risk-Adjusted Returns & Benchmarking
# ---------------------------------------------------------------------------

class DailyReturnPoint(BaseModel):
    """Single day's return for chart data."""
    date: str
    return_pct: Decimal = Field(default=Decimal("0"))
    nav_tao: Decimal = Field(default=Decimal("0"))


class BenchmarkComparison(BaseModel):
    """Single benchmark comparison."""
    id: str
    name: str
    description: str
    annualized_return_pct: Decimal = Field(default=Decimal("0"))
    annualized_volatility_pct: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    alpha_pct: Decimal = Field(default=Decimal("0"))


class RiskMetricsResponse(BaseModel):
    """Risk-adjusted return metrics – Phase 4 endpoint."""
    period_days: int = 0
    start: str = ""
    end: str = ""

    # Core return metrics
    annualized_return_pct: Decimal = Field(default=Decimal("0"))
    annualized_volatility_pct: Decimal = Field(default=Decimal("0"))
    downside_deviation_pct: Decimal = Field(default=Decimal("0"))

    # Risk-adjusted ratios
    sharpe_ratio: Decimal = Field(default=Decimal("0"))
    sortino_ratio: Decimal = Field(default=Decimal("0"))
    calmar_ratio: Decimal = Field(default=Decimal("0"))

    # Drawdown
    max_drawdown_pct: Decimal = Field(default=Decimal("0"))
    max_drawdown_tao: Decimal = Field(default=Decimal("0"))

    # Risk-free rate
    risk_free_rate_pct: Decimal = Field(default=Decimal("0"))
    risk_free_source: str = "Root (SN0) Validator APY"

    # Win/loss stats
    win_rate_pct: Decimal = Field(default=Decimal("0"))
    best_day_pct: Decimal = Field(default=Decimal("0"))
    worst_day_pct: Decimal = Field(default=Decimal("0"))

    # Benchmarks
    benchmarks: List[BenchmarkComparison] = Field(default_factory=list)

    # Daily return series (for chart)
    daily_returns: List[DailyReturnPoint] = Field(default_factory=list)
