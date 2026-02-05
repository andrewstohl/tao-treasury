"""Application configuration loaded from environment variables."""

from decimal import Decimal
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys and Wallet
    taostats_api_key: str = Field(..., description="TaoStats API key")
    wallet_address: str = Field(..., description="Coldkey wallet address to track")
    coingecko_api_key: Optional[str] = Field(default=None, description="CoinGecko API key")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://tao_user:tao_password@localhost:5435/tao_treasury",
        description="PostgreSQL connection URL"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    # Environment
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # Server
    backend_port: int = Field(default=8050)
    frontend_port: int = Field(default=3050)

    # TaoStats API
    taostats_base_url: str = Field(
        default="https://api.taostats.io",
        description="TaoStats API base URL"
    )
    taostats_rate_limit_per_minute: int = Field(default=60)

    # Risk Parameters (TAO-denominated)
    soft_drawdown_limit: Decimal = Field(
        default=Decimal("0.15"),
        description="Soft portfolio drawdown limit (15%)"
    )
    hard_drawdown_limit: Decimal = Field(
        default=Decimal("0.20"),
        description="Hard portfolio drawdown limit (20%) - triggers forced risk-off"
    )

    # Slippage Caps (per spec: 5% for 50% exit, 10% for full exit)
    max_exit_slippage_50pct: Decimal = Field(
        default=Decimal("0.05"),
        description="Max slippage for 50% position exit (5%) - blocks new buys"
    )
    max_exit_slippage_100pct: Decimal = Field(
        default=Decimal("0.10"),
        description="Max slippage for 100% position exit (10%) - forces trim"
    )
    exitability_warning_threshold: Decimal = Field(
        default=Decimal("0.075"),
        description="Warning tier for 100% exit slippage (7.5%) - flags for monitoring"
    )

    # Feature Flags
    enable_exitability_gate: bool = Field(
        default=False,
        description="Enable hard exitability gate (blocks buys at 5%, forces trims at 10%)"
    )

    # Position Constraints
    max_position_concentration: Decimal = Field(
        default=Decimal("0.15"),
        description="Max single position as % of portfolio (15% hard cap)"
    )
    default_position_concentration: Decimal = Field(
        default=Decimal("0.10"),
        description="Default target position size (10-12%)"
    )
    min_position_pct: Decimal = Field(
        default=Decimal("0.03"),
        description="Minimum meaningful position size as % of portfolio (3%)"
    )
    min_position_tao: Decimal = Field(
        default=Decimal("50"),
        description="Minimum meaningful position size in TAO (absolute floor)"
    )
    min_positions: int = Field(
        default=8,
        description="Minimum number of positions in sleeve"
    )
    max_positions: int = Field(
        default=15,
        description="Maximum number of positions in sleeve"
    )

    # Category Caps
    max_category_concentration_sleeve: Decimal = Field(
        default=Decimal("0.30"),
        description="Max allocation to any category within sleeve (30%)"
    )
    max_category_concentration_portfolio: Decimal = Field(
        default=Decimal("0.35"),
        description="Max allocation to any category of total portfolio (35%)"
    )

    # Portfolio Allocation Targets
    root_allocation_min: Decimal = Field(default=Decimal("0.55"))
    root_allocation_max: Decimal = Field(default=Decimal("0.75"))
    dtao_allocation_min: Decimal = Field(default=Decimal("0.20"))
    dtao_allocation_max: Decimal = Field(default=Decimal("0.40"))
    unstaked_buffer_min: Decimal = Field(default=Decimal("0.05"))
    unstaked_buffer_max: Decimal = Field(default=Decimal("0.10"))

    # Turnover Caps
    max_daily_turnover: Decimal = Field(
        default=Decimal("0.10"),
        description="Max daily turnover as % of NAV (10%)"
    )
    max_weekly_turnover: Decimal = Field(
        default=Decimal("0.40"),
        description="Max weekly turnover as % of NAV (40%)"
    )

    # Universe Filters
    min_liquidity_tao: Decimal = Field(
        default=Decimal("1000"),
        description="Minimum pool liquidity in TAO"
    )
    min_holder_count: int = Field(default=50)
    min_subnet_age_days: int = Field(default=30)
    max_owner_take: Decimal = Field(
        default=Decimal("0.20"),
        description="Maximum owner take rate (20%)"
    )
    min_emission_share: Decimal = Field(
        default=Decimal("0.001"),
        description="Minimum emission share (0.1%)"
    )

    # ==================== Viability Scoring System ====================
    enable_viability_scoring: bool = Field(
        default=True,
        description="Enable viability scoring system for subnet filtering"
    )

    # Hard failure thresholds
    viability_min_tao_reserve: Decimal = Field(
        default=Decimal("500"),
        description="Minimum TAO reserve for viability"
    )
    viability_min_emission_share: Decimal = Field(
        default=Decimal("0.002"),
        description="Minimum emission share for viability (0.2%)"
    )
    viability_min_age_days: int = Field(
        default=60,
        description="Minimum subnet age in days for viability"
    )
    viability_min_holders: int = Field(
        default=20,
        description="Minimum holder count for viability"
    )
    viability_max_drawdown_30d: Decimal = Field(
        default=Decimal("0.40"),
        description="Maximum 30d drawdown for viability (40%)"
    )
    viability_max_negative_flow_ratio: Decimal = Field(
        default=Decimal("0.30"),
        description="Maximum 7d negative flow as fraction of TAO reserve (30%)"
    )

    # Scored metric weights (must sum to 1.0)
    viability_weight_tao_reserve: Decimal = Field(default=Decimal("0.25"))
    viability_weight_net_flow_7d: Decimal = Field(default=Decimal("0.25"))
    viability_weight_emission_share: Decimal = Field(default=Decimal("0.15"))
    viability_weight_price_trend_7d: Decimal = Field(default=Decimal("0.15"))
    viability_weight_subnet_age: Decimal = Field(default=Decimal("0.10"))
    viability_weight_max_drawdown_30d: Decimal = Field(default=Decimal("0.10"))

    # Tier boundaries
    viability_tier_1_min: int = Field(default=75, description="Min score for Tier 1 (Prime)")
    viability_tier_2_min: int = Field(default=55, description="Min score for Tier 2 (Eligible)")
    viability_tier_3_min: int = Field(default=40, description="Min score for Tier 3 (Watchlist)")

    # Age cap for diminishing returns
    viability_age_cap_days: int = Field(
        default=365,
        description="Cap age metric at this many days"
    )

    # Taoflow Regime Thresholds
    flow_persistence_days: int = Field(
        default=3,
        description="Days of persistent flow direction to confirm regime"
    )
    risk_off_flow_threshold: Decimal = Field(
        default=Decimal("-0.05"),
        description="Net flow threshold for Risk-Off regime"
    )
    quarantine_flow_threshold: Decimal = Field(
        default=Decimal("-0.15"),
        description="Net flow threshold for Quarantine regime"
    )

    # Regime Persistence (anti-whipsaw)
    enable_regime_persistence: bool = Field(
        default=False,
        description="Enable regime persistence requirement (anti-whipsaw)"
    )
    regime_persistence_risk_on: int = Field(
        default=2,
        description="Consecutive days required to transition TO Risk-On"
    )
    regime_persistence_risk_off: int = Field(
        default=2,
        description="Consecutive days required to transition TO Risk-Off"
    )
    regime_persistence_quarantine: int = Field(
        default=3,
        description="Consecutive days required to transition TO Quarantine"
    )
    regime_persistence_dead: int = Field(
        default=2,
        description="Consecutive days required to transition TO Dead"
    )

    # Emissions Collapse Detection (Phase 1B)
    enable_emissions_collapse_detection: bool = Field(
        default=False,
        description="Enable emissions collapse detection as regime gate"
    )
    emissions_collapse_warning_threshold: Decimal = Field(
        default=Decimal("0.30"),
        description="7d emissions drop threshold for warning (30% drop -> Risk-Off)"
    )
    emissions_collapse_severe_threshold: Decimal = Field(
        default=Decimal("0.50"),
        description="7d emissions drop threshold for severe action (50% drop -> Quarantine)"
    )
    emissions_near_zero_threshold: Decimal = Field(
        default=Decimal("0.0001"),
        description="Emissions share threshold for near-zero detection (0.01% -> Dead)"
    )
    emissions_lookback_days: int = Field(
        default=7,
        description="Days to look back for emissions delta calculation"
    )

    # TAO Macro Regime Detection (Phase 2A)
    enable_macro_regime_detection: bool = Field(
        default=False,
        description="Enable TAO macro regime detection for portfolio-level strategy"
    )
    macro_bull_flow_threshold: Decimal = Field(
        default=Decimal("0.03"),
        description="Aggregate 7d flow threshold for BULL regime (3% net inflow)"
    )
    macro_bear_flow_threshold: Decimal = Field(
        default=Decimal("-0.03"),
        description="Aggregate 7d flow threshold for BEAR regime (-3% net outflow)"
    )
    macro_accumulation_drawdown_min: Decimal = Field(
        default=Decimal("0.10"),
        description="Min drawdown for ACCUMULATION zone (10% - bottoming)"
    )
    macro_accumulation_drawdown_max: Decimal = Field(
        default=Decimal("0.25"),
        description="Max drawdown for ACCUMULATION zone (25% - not capitulation)"
    )
    macro_capitulation_drawdown: Decimal = Field(
        default=Decimal("0.25"),
        description="Drawdown threshold for CAPITULATION regime (25%+ from ATH)"
    )
    macro_capitulation_flow_threshold: Decimal = Field(
        default=Decimal("-0.10"),
        description="Aggregate flow threshold for CAPITULATION (-10% severe outflow)"
    )
    macro_regime_lookback_days: int = Field(
        default=7,
        description="Days to look back for macro regime flow aggregation"
    )

    # Scheduler Intervals
    wallet_refresh_minutes: int = Field(default=5)
    pools_refresh_minutes: int = Field(default=10)
    flow_refresh_minutes: int = Field(default=30)
    validator_refresh_minutes: int = Field(default=60)
    slippage_refresh_hours: int = Field(default=24)
    stale_data_threshold_minutes: int = Field(default=30)

    # ==================== Phase 0: Observability ====================
    enable_cache_metrics: bool = Field(
        default=True,
        description="Track cache hit/miss rates in metrics"
    )
    enable_api_metrics: bool = Field(
        default=True,
        description="Track API call latency and error rates"
    )
    enable_sync_metrics: bool = Field(
        default=True,
        description="Track sync job success/failure and staleness"
    )
    metrics_retention_hours: int = Field(
        default=24,
        description="Hours to retain detailed metrics history"
    )

    # ==================== Phase 1: Client Hardening ====================
    # Retry-After handling
    enable_retry_after: bool = Field(
        default=True,
        description="Respect Retry-After headers from TaoStats API"
    )
    retry_after_max_wait_seconds: int = Field(
        default=300,
        description="Max seconds to wait when Retry-After is received (5 min cap)"
    )

    # Backoff configuration
    api_initial_backoff_seconds: float = Field(
        default=1.0,
        description="Initial backoff delay for transient failures"
    )
    api_max_backoff_seconds: float = Field(
        default=60.0,
        description="Maximum backoff delay"
    )
    api_backoff_multiplier: float = Field(
        default=2.0,
        description="Exponential backoff multiplier"
    )
    api_max_retries: int = Field(
        default=3,
        description="Max retry attempts for transient failures"
    )

    # Timeouts
    api_connect_timeout_seconds: float = Field(
        default=10.0,
        description="HTTP connection timeout"
    )
    api_read_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP read timeout"
    )

    # Response validation
    enable_response_validation: bool = Field(
        default=True,
        description="Validate API responses with Pydantic models"
    )

    # ==================== Phase 1.5: Advanced Features (Behind Flags) ====================
    enable_client_side_slippage: bool = Field(
        default=False,
        description="Use client-side slippage calculation instead of API"
    )
    enable_reconciliation: bool = Field(
        default=False,
        description="Enable periodic data reconciliation checks"
    )
    reconciliation_interval_hours: int = Field(
        default=6,
        description="Hours between reconciliation runs"
    )
    reconciliation_drift_threshold_pct: float = Field(
        default=5.0,
        description="Percentage drift threshold to flag as anomaly"
    )

    # ==================== Sync Reliability ====================
    enable_partial_failure_protection: bool = Field(
        default=True,
        description="Never overwrite good data with empty API responses"
    )
    min_records_for_valid_sync: int = Field(
        default=1,
        description="Minimum records required to consider sync valid"
    )
    sync_staleness_warning_minutes: int = Field(
        default=15,
        description="Minutes without sync before warning"
    )
    sync_staleness_critical_minutes: int = Field(
        default=60,
        description="Minutes without sync before critical alert"
    )

    # ==================== Phase 2: Earnings & Reconciliation ====================
    enable_earnings_endpoints: bool = Field(
        default=True,
        description="Enable earnings attribution endpoints"
    )
    enable_reconciliation_endpoints: bool = Field(
        default=True,
        description="Enable reconciliation endpoints"
    )
    enable_reconciliation_in_trust_pack: bool = Field(
        default=True,
        description="Include reconciliation status in Trust Pack"
    )
    enable_earnings_timeseries_by_netuid: bool = Field(
        default=False,
        description="Include per-netuid breakdown in timeseries (can be heavy)"
    )

    # Reconciliation tolerances
    reconciliation_absolute_tolerance_tao: Decimal = Field(
        default=Decimal("0.0001"),
        description="Absolute tolerance for reconciliation checks in TAO"
    )
    reconciliation_relative_tolerance_pct: Decimal = Field(
        default=Decimal("0.1"),
        description="Relative tolerance for reconciliation checks as percentage"
    )

    # ==================== Phase 3: Decision Support Signals ====================
    enable_signal_endpoints: bool = Field(
        default=True,
        description="Enable signal endpoints for decision support"
    )
    slippage_threshold_pct: Decimal = Field(
        default=Decimal("1.0"),
        description="Slippage percentage threshold for capacity signal (1%)"
    )
    slippage_stale_minutes: int = Field(
        default=10,
        description="Minutes before slippage data is considered stale"
    )

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
