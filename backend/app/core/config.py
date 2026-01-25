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
        description="Max slippage for 50% position exit (5%)"
    )
    max_exit_slippage_100pct: Decimal = Field(
        default=Decimal("0.10"),
        description="Max slippage for 100% position exit (10%)"
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

    # Scheduler Intervals
    wallet_refresh_minutes: int = Field(default=5)
    pools_refresh_minutes: int = Field(default=10)
    flow_refresh_minutes: int = Field(default=30)
    validator_refresh_minutes: int = Field(default=60)
    slippage_refresh_hours: int = Field(default=24)
    stale_data_threshold_minutes: int = Field(default=30)


    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
