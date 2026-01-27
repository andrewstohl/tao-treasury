"""Pydantic response models for TaoStats API validation.

These models validate API responses and provide typed access to data.
They don't need to capture every field - just the ones we use.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
import re


# ==================== Timestamp Parsing ====================

def parse_taostats_timestamp(value: Any) -> Optional[datetime]:
    """Parse TaoStats timestamp which may come in multiple formats.

    Handles:
    - ISO8601 with Z suffix: "2024-01-15T12:00:00Z"
    - ISO8601 with milliseconds: "2024-01-15T12:00:00.123Z"
    - ISO8601 with timezone offset: "2024-01-15T12:00:00+00:00"
    - Unix timestamp as int or string
    - None/empty values
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        # Unix timestamp - use timezone-aware then strip for consistency
        return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)

    if isinstance(value, str):
        # Try multiple formats
        value = value.strip()

        # Handle Z suffix
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        # Try ISO format with timezone
        try:
            dt = datetime.fromisoformat(value)
            # Convert to naive UTC for consistency
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            pass

        # Try common formats without timezone
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        # Try as numeric string (unix timestamp)
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError):
            pass

    raise ValueError(f"Cannot parse timestamp: {value!r}")


# ==================== Base Models ====================

class TaoStatsAddress(BaseModel):
    """Address object from TaoStats API."""
    ss58: str
    hex: Optional[str] = None

    @classmethod
    def from_raw(cls, value: Any) -> "TaoStatsAddress":
        """Handle both string and object formats."""
        if isinstance(value, str):
            return cls(ss58=value)
        if isinstance(value, dict):
            return cls(**value)
        raise ValueError(f"Invalid address format: {value!r}")


class TaoStatsPagination(BaseModel):
    """Pagination info from TaoStats API."""
    current_page: int = 1
    total_pages: int = 1
    total_items: int = 0
    items_per_page: int = 50
    next_page: Optional[int] = None
    prev_page: Optional[int] = None


class TaoStatsResponse(BaseModel):
    """Base response wrapper from TaoStats API."""
    data: List[Any] = Field(default_factory=list)
    pagination: Optional[TaoStatsPagination] = None

    @field_validator("data", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> List[Any]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]


# ==================== Subnet Models ====================

class SubnetPoolData(BaseModel):
    """Pool data from /api/dtao/pool/latest/v1."""
    netuid: int
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None
    name: Optional[str] = None
    symbol: Optional[str] = None

    # Core pool metrics (in rao)
    market_cap: Optional[str] = None
    liquidity: Optional[str] = None
    total_tao: Optional[str] = None
    total_alpha: Optional[str] = None
    alpha_in_pool: Optional[str] = None
    alpha_staked: Optional[str] = None
    price: Optional[str] = None  # TAO per Alpha

    # Price changes
    price_change_1_hour: Optional[str] = None
    price_change_1_day: Optional[str] = None
    price_change_1_week: Optional[str] = None
    price_change_1_month: Optional[str] = None

    # Volume (24h)
    tao_volume_24_hr: Optional[str] = None
    alpha_volume_24_hr: Optional[str] = None

    # Trading activity
    buys_24_hr: Optional[int] = None
    sells_24_hr: Optional[int] = None
    buyers_24_hr: Optional[int] = None
    sellers_24_hr: Optional[int] = None

    # Sentiment
    fear_and_greed_index: Optional[str] = None
    fear_and_greed_sentiment: Optional[str] = None

    # State flags
    startup_mode: bool = False
    root_prop: Optional[str] = None
    rank: Optional[int] = None

    # Mini chart data
    seven_day_prices: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def price_decimal(self) -> Decimal:
        """Get price as Decimal."""
        if self.price:
            return Decimal(self.price)
        return Decimal("0")

    @property
    def liquidity_tao(self) -> Decimal:
        """Get liquidity in TAO (from rao)."""
        if self.liquidity:
            return Decimal(self.liquidity) / Decimal("1e9")
        return Decimal("0")


class SubnetData(BaseModel):
    """Subnet data from /api/subnet/latest/v1."""
    netuid: int
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None

    # Ownership
    owner: Optional[Any] = None  # Can be string or object

    # Registration
    registration_block_number: Optional[int] = None
    registration_timestamp: Optional[datetime] = None
    registration_cost: Optional[str] = None

    # Network size
    max_neurons: Optional[int] = None
    active_keys: Optional[int] = None
    validators: Optional[int] = None
    active_validators: Optional[int] = None
    active_miners: Optional[int] = None

    # Emissions
    emission: Optional[str] = None

    # Hyperparameters
    tempo: Optional[int] = None
    immunity_period: Optional[int] = None
    min_allowed_weights: Optional[int] = None
    max_weights_limit: Optional[int] = None

    # Alpha/dTAO specific
    liquid_alpha_enabled: bool = False
    startup_mode: bool = False

    @field_validator("timestamp", "registration_timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def owner_address(self) -> Optional[str]:
        """Get owner address as string."""
        if self.owner is None:
            return None
        if isinstance(self.owner, str):
            return self.owner
        if isinstance(self.owner, dict):
            return self.owner.get("ss58")
        return None


# ==================== Stake/Position Models ====================

class StakeBalanceData(BaseModel):
    """Stake balance from /api/dtao/stake_balance/latest/v1."""
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None

    hotkey: Optional[Any] = None
    hotkey_name: Optional[str] = None
    coldkey: Optional[Any] = None
    netuid: int

    balance: Optional[str] = None  # Alpha balance in rao
    balance_as_tao: Optional[str] = None  # TAO value in rao

    subnet_rank: Optional[int] = None
    subnet_total_holders: Optional[int] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def hotkey_address(self) -> Optional[str]:
        if self.hotkey is None:
            return None
        if isinstance(self.hotkey, str):
            return self.hotkey
        if isinstance(self.hotkey, dict):
            return self.hotkey.get("ss58")
        return None

    @property
    def coldkey_address(self) -> Optional[str]:
        if self.coldkey is None:
            return None
        if isinstance(self.coldkey, str):
            return self.coldkey
        if isinstance(self.coldkey, dict):
            return self.coldkey.get("ss58")
        return None

    @property
    def alpha_balance(self) -> Decimal:
        """Get alpha balance as Decimal (from rao)."""
        if self.balance:
            return Decimal(self.balance) / Decimal("1e9")
        return Decimal("0")

    @property
    def tao_value(self) -> Decimal:
        """Get TAO value as Decimal (from rao)."""
        if self.balance_as_tao:
            return Decimal(self.balance_as_tao) / Decimal("1e9")
        return Decimal("0")


# ==================== Delegation/Trade Models ====================

class DelegationEventData(BaseModel):
    """Delegation event from /api/delegation/v1."""
    id: Optional[str] = None
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None

    action: str  # "DELEGATE" or "UNDELEGATE"
    netuid: int

    nominator: Optional[Any] = None  # Coldkey of staker
    delegate: Optional[Any] = None  # Hotkey of validator

    amount: Optional[str] = None  # TAO in rao
    alpha: Optional[str] = None  # Alpha in rao
    usd: Optional[str] = None

    alpha_price_in_tao: Optional[str] = None
    alpha_price_in_usd: Optional[str] = None

    extrinsic_id: Optional[str] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def amount_tao(self) -> Decimal:
        """Get amount in TAO."""
        if self.amount:
            return Decimal(self.amount) / Decimal("1e9")
        return Decimal("0")

    @property
    def alpha_amount(self) -> Decimal:
        """Get alpha amount."""
        if self.alpha:
            return Decimal(self.alpha) / Decimal("1e9")
        return Decimal("0")


class TradeData(BaseModel):
    """Trade data from /api/dtao/trade/v1."""
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None
    extrinsic_id: Optional[str] = None

    from_name: Optional[str] = None  # "TAO" or "SN##"
    to_name: Optional[str] = None
    from_amount: Optional[str] = None  # rao
    to_amount: Optional[str] = None  # rao

    tao_value: Optional[str] = None  # rao
    usd_value: Optional[str] = None

    coldkey: Optional[Any] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def is_stake(self) -> bool:
        """True if this is a stake (TAO -> Alpha)."""
        return self.from_name == "TAO"

    @property
    def netuid(self) -> Optional[int]:
        """Extract netuid from subnet name."""
        name = self.to_name if self.is_stake else self.from_name
        if name and name.startswith("SN"):
            try:
                return int(name[2:])
            except ValueError:
                pass
        return None


# ==================== Slippage Models ====================

class SlippageData(BaseModel):
    """Slippage calculation from /api/dtao/slippage/v1."""
    netuid: int
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None

    alpha_price: Optional[str] = None  # Price in TAO
    output_tokens: Optional[str] = None  # Output tokens in rao
    expected_output_tokens: Optional[str] = None  # Expected in rao
    diff: Optional[str] = None  # Difference in rao
    slippage: Optional[str] = None  # Slippage as decimal

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def slippage_pct(self) -> Decimal:
        """Get slippage as percentage."""
        if self.slippage:
            return Decimal(self.slippage) * 100
        return Decimal("0")


# ==================== Validator Models ====================

class ValidatorData(BaseModel):
    """Validator data from /api/dtao/validator/latest/v1."""
    hotkey: Optional[Any] = None
    coldkey: Optional[Any] = None
    name: Optional[str] = None

    netuid: Optional[int] = None
    stake: Optional[str] = None  # rao

    # Performance
    vtrust: Optional[str] = None
    trust: Optional[str] = None
    consensus: Optional[str] = None
    incentive: Optional[str] = None
    dividends: Optional[str] = None
    emission: Optional[str] = None

    # Rankings
    rank: Optional[int] = None

    @property
    def hotkey_address(self) -> Optional[str]:
        if self.hotkey is None:
            return None
        if isinstance(self.hotkey, str):
            return self.hotkey
        if isinstance(self.hotkey, dict):
            return self.hotkey.get("ss58")
        return None

    @property
    def stake_tao(self) -> Decimal:
        """Get stake in TAO."""
        if self.stake:
            return Decimal(self.stake) / Decimal("1e9")
        return Decimal("0")


class ValidatorYieldData(BaseModel):
    """Validator yield from /api/dtao/validator/yield/latest/v1."""
    hotkey: Optional[Any] = None
    netuid: Optional[int] = None

    apy: Optional[str] = None
    epoch_participation: Optional[str] = None

    @property
    def hotkey_address(self) -> Optional[str]:
        if self.hotkey is None:
            return None
        if isinstance(self.hotkey, str):
            return self.hotkey
        if isinstance(self.hotkey, dict):
            return self.hotkey.get("ss58")
        return None

    @property
    def apy_pct(self) -> Decimal:
        """Get APY as percentage."""
        if self.apy:
            try:
                return Decimal(self.apy)
            except:
                return Decimal("0")
        return Decimal("0")


# ==================== Price Models ====================

class TaoPriceData(BaseModel):
    """TAO price from /api/price/latest/v1."""
    asset: str = "tao"
    price: Optional[str] = None
    timestamp: Optional[datetime] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def price_usd(self) -> Decimal:
        """Get price as Decimal."""
        if self.price:
            return Decimal(self.price)
        return Decimal("0")


# ==================== Account Models ====================

class AccountData(BaseModel):
    """Account data from /api/account/latest/v1."""
    address: Optional[str] = None
    block_number: Optional[int] = None
    timestamp: Optional[datetime] = None

    balance_free: Optional[str] = None  # rao
    balance_staked: Optional[str] = None  # rao
    balance_total: Optional[str] = None  # rao

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> Optional[datetime]:
        return parse_taostats_timestamp(v)

    @property
    def free_tao(self) -> Decimal:
        if self.balance_free:
            return Decimal(self.balance_free) / Decimal("1e9")
        return Decimal("0")

    @property
    def staked_tao(self) -> Decimal:
        if self.balance_staked:
            return Decimal(self.balance_staked) / Decimal("1e9")
        return Decimal("0")

    @property
    def total_tao(self) -> Decimal:
        if self.balance_total:
            return Decimal(self.balance_total) / Decimal("1e9")
        return Decimal("0")


# ==================== Response Validators ====================

def validate_response(
    response_data: Dict[str, Any],
    expected_type: str = "list",
) -> bool:
    """Validate a TaoStats API response structure.

    Args:
        response_data: The raw response dict
        expected_type: "list" for paginated data, "single" for single object

    Returns:
        True if valid, raises ValueError if not
    """
    if not isinstance(response_data, dict):
        raise ValueError(f"Expected dict response, got {type(response_data)}")

    if "data" not in response_data:
        raise ValueError("Response missing 'data' field")

    data = response_data["data"]

    if expected_type == "list":
        if not isinstance(data, list):
            raise ValueError(f"Expected list data, got {type(data)}")

    return True
