"""Subnet schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class SubnetResponse(BaseModel):
    """Subnet response with full details."""
    id: int
    netuid: int
    name: str
    description: Optional[str] = None

    # Ownership
    owner_address: Optional[str] = None
    owner_take: Decimal = Field(default=Decimal("0"))

    # Fee & burn parameters
    fee_rate: Decimal = Field(default=Decimal("0"))
    incentive_burn: Decimal = Field(default=Decimal("0"))

    # Age
    registered_at: Optional[datetime] = None
    age_days: int = 0

    # Metrics
    emission_share: Decimal = Field(default=Decimal("0"))
    total_stake_tao: Decimal = Field(default=Decimal("0"))

    # Pool metrics
    pool_tao_reserve: Decimal = Field(default=Decimal("0"))
    pool_alpha_reserve: Decimal = Field(default=Decimal("0"))
    alpha_price_tao: Decimal = Field(default=Decimal("0"))

    # Ranking and market cap
    rank: Optional[int] = None
    market_cap_tao: Decimal = Field(default=Decimal("0"))

    # Holders
    holder_count: int = 0

    # Taoflow
    taoflow_1d: Decimal = Field(default=Decimal("0"))
    taoflow_3d: Decimal = Field(default=Decimal("0"))
    taoflow_7d: Decimal = Field(default=Decimal("0"))
    taoflow_14d: Decimal = Field(default=Decimal("0"))

    # Regime
    flow_regime: str = "neutral"
    flow_regime_since: Optional[datetime] = None

    # Validator
    validator_apy: Decimal = Field(default=Decimal("0"))

    # Eligibility
    is_eligible: bool = False
    ineligibility_reasons: Optional[str] = None
    category: Optional[str] = None

    # Viability scoring
    viability_score: Optional[Decimal] = None
    viability_tier: Optional[str] = None
    viability_factors: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubnetListResponse(BaseModel):
    """Response for subnet list endpoint."""
    subnets: List[SubnetResponse]
    total: int
    eligible_count: int


# ==================== Enriched Endpoint Schemas ====================


class SparklinePoint(BaseModel):
    """Single point in a sparkline series."""
    timestamp: str
    price: float


class VolatilePoolData(BaseModel):
    """Volatile market data passed through from TaoStats (not stored in DB)."""
    price_change_1h: Optional[float] = None
    price_change_24h: Optional[float] = None
    price_change_7d: Optional[float] = None
    price_change_30d: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    market_cap_change_24h: Optional[float] = None
    tao_volume_24h: Optional[float] = None
    tao_buy_volume_24h: Optional[float] = None
    tao_sell_volume_24h: Optional[float] = None
    buys_24h: Optional[int] = None
    sells_24h: Optional[int] = None
    buyers_24h: Optional[int] = None
    sellers_24h: Optional[int] = None
    fear_greed_index: Optional[float] = None
    fear_greed_sentiment: Optional[str] = None
    sparkline_7d: Optional[List[SparklinePoint]] = None
    alpha_in_pool: Optional[float] = None
    alpha_staked: Optional[float] = None
    total_alpha: Optional[float] = None
    root_prop: Optional[float] = None
    startup_mode: Optional[bool] = None


class SubnetIdentity(BaseModel):
    """Subnet identity metadata passed through from TaoStats (not stored in DB)."""
    tagline: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    github_repo: Optional[str] = None
    subnet_url: Optional[str] = None
    logo_url: Optional[str] = None
    discord: Optional[str] = None
    twitter: Optional[str] = None
    subnet_contact: Optional[str] = None


class DevActivity(BaseModel):
    """Developer activity metrics passed through from TaoStats (not stored in DB)."""
    repo_url: Optional[str] = None
    commits_1d: Optional[int] = None
    commits_7d: Optional[int] = None
    commits_30d: Optional[int] = None
    prs_opened_7d: Optional[int] = None
    prs_merged_7d: Optional[int] = None
    issues_opened_30d: Optional[int] = None
    issues_closed_30d: Optional[int] = None
    reviews_30d: Optional[int] = None
    unique_contributors_7d: Optional[int] = None
    unique_contributors_30d: Optional[int] = None
    last_event_at: Optional[str] = None
    days_since_last_event: Optional[int] = None


class EnrichedSubnetResponse(BaseModel):
    """Subnet response enriched with volatile market data."""
    # All stable DB fields
    netuid: int
    name: str
    description: Optional[str] = None

    # Ownership
    owner_address: Optional[str] = None
    owner_take: Decimal = Field(default=Decimal("0"))

    # Fee & burn parameters
    fee_rate: Decimal = Field(default=Decimal("0"))
    incentive_burn: Decimal = Field(default=Decimal("0"))

    # Age
    registered_at: Optional[datetime] = None
    age_days: int = 0

    # Metrics
    emission_share: Decimal = Field(default=Decimal("0"))
    total_stake_tao: Decimal = Field(default=Decimal("0"))

    # Pool metrics
    pool_tao_reserve: Decimal = Field(default=Decimal("0"))
    pool_alpha_reserve: Decimal = Field(default=Decimal("0"))
    alpha_price_tao: Decimal = Field(default=Decimal("0"))

    # Ranking and market cap
    rank: Optional[int] = None
    market_cap_tao: Decimal = Field(default=Decimal("0"))

    # Holders
    holder_count: int = 0

    # Taoflow
    taoflow_1d: Decimal = Field(default=Decimal("0"))
    taoflow_3d: Decimal = Field(default=Decimal("0"))
    taoflow_7d: Decimal = Field(default=Decimal("0"))
    taoflow_14d: Decimal = Field(default=Decimal("0"))

    # Regime
    flow_regime: str = "neutral"
    flow_regime_since: Optional[datetime] = None

    # Validator
    validator_apy: Decimal = Field(default=Decimal("0"))

    # Eligibility
    is_eligible: bool = False
    ineligibility_reasons: Optional[str] = None
    category: Optional[str] = None

    # Viability scoring
    viability_score: Optional[Decimal] = None
    viability_tier: Optional[str] = None
    viability_factors: Optional[str] = None

    # Volatile data (null when TaoStats unavailable)
    volatile: Optional[VolatilePoolData] = None

    # Identity metadata (null when TaoStats unavailable)
    identity: Optional[SubnetIdentity] = None

    # Dev activity (null when TaoStats unavailable)
    dev_activity: Optional[DevActivity] = None

    class Config:
        from_attributes = True


class EnrichedSubnetListResponse(BaseModel):
    """Response for enriched subnet list endpoint."""
    subnets: List[EnrichedSubnetResponse]
    total: int
    eligible_count: int
    taostats_available: bool = True
    cache_age_seconds: Optional[int] = None
