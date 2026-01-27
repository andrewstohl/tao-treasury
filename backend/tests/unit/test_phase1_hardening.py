"""Tests for Phase 0+1: Client Hardening and Observability.

Tests cover:
- Retry-After header parsing
- Exponential backoff calculation with jitter
- Timestamp parsing in response models
- Partial failure protection logic
- Metrics collection
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
import httpx


class TestRetryAfterParsing:
    """Test Retry-After header parsing in TaoStatsClient."""

    def test_parse_retry_after_integer(self):
        """Parse Retry-After as integer seconds."""
        from app.services.data.taostats_client import TaoStatsClient

        client = TaoStatsClient()
        response = MagicMock(spec=httpx.Response)
        response.headers = {"Retry-After": "120"}

        result = client._parse_retry_after(response)
        assert result == 120

    def test_parse_retry_after_missing(self):
        """Return None when Retry-After header is missing."""
        from app.services.data.taostats_client import TaoStatsClient

        client = TaoStatsClient()
        response = MagicMock(spec=httpx.Response)
        response.headers = {}

        result = client._parse_retry_after(response)
        assert result is None

    def test_parse_retry_after_invalid(self):
        """Return None for unparseable Retry-After values."""
        from app.services.data.taostats_client import TaoStatsClient

        client = TaoStatsClient()
        response = MagicMock(spec=httpx.Response)
        response.headers = {"Retry-After": "invalid-value"}

        result = client._parse_retry_after(response)
        assert result is None

    def test_parse_retry_after_http_date(self):
        """Parse Retry-After as HTTP date format."""
        from app.services.data.taostats_client import TaoStatsClient

        client = TaoStatsClient()
        response = MagicMock(spec=httpx.Response)
        # Use a future date
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        response.headers = {"Retry-After": http_date}

        result = client._parse_retry_after(response)
        # Should be approximately 60 seconds (allow some tolerance)
        assert result is not None
        assert 50 <= result <= 70


class TestExponentialBackoff:
    """Test exponential backoff calculation."""

    def test_backoff_increases_exponentially(self):
        """Verify backoff increases with attempt number."""
        from app.services.data.taostats_client import TaoStatsClient

        client = TaoStatsClient()

        # Get base backoff values (without jitter randomness)
        with patch('random.uniform', return_value=0):
            backoff_0 = client._calculate_backoff(0)
            backoff_1 = client._calculate_backoff(1)
            backoff_2 = client._calculate_backoff(2)

        # Each should be roughly double the previous (base * 2^attempt)
        assert backoff_1 > backoff_0
        assert backoff_2 > backoff_1

    def test_backoff_respects_max(self):
        """Verify backoff doesn't exceed max setting."""
        from app.services.data.taostats_client import TaoStatsClient
        from app.core.config import get_settings

        client = TaoStatsClient()
        settings = get_settings()

        with patch('random.uniform', return_value=0):
            # Very high attempt number should still be capped
            backoff = client._calculate_backoff(100)

        assert backoff <= settings.api_max_backoff_seconds

    def test_backoff_includes_jitter(self):
        """Verify jitter is added to backoff."""
        from app.services.data.taostats_client import TaoStatsClient

        client = TaoStatsClient()

        # Call multiple times - should get different results due to jitter
        backoffs = [client._calculate_backoff(1) for _ in range(10)]

        # Not all values should be identical (jitter adds randomness)
        unique_values = set(backoffs)
        assert len(unique_values) > 1


class TestTimestampParsing:
    """Test timestamp parsing in response models."""

    def test_parse_iso8601_with_z(self):
        """Parse ISO8601 timestamp with Z suffix."""
        from app.services.data.response_models import parse_taostats_timestamp

        result = parse_taostats_timestamp("2024-01-15T12:00:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 12

    def test_parse_iso8601_with_milliseconds(self):
        """Parse ISO8601 timestamp with milliseconds."""
        from app.services.data.response_models import parse_taostats_timestamp

        result = parse_taostats_timestamp("2024-01-15T12:00:00.123Z")
        assert result is not None
        assert result.year == 2024

    def test_parse_iso8601_with_timezone(self):
        """Parse ISO8601 timestamp with timezone offset."""
        from app.services.data.response_models import parse_taostats_timestamp

        result = parse_taostats_timestamp("2024-01-15T12:00:00+00:00")
        assert result is not None
        assert result.year == 2024

    def test_parse_unix_timestamp_int(self):
        """Parse Unix timestamp as integer."""
        from app.services.data.response_models import parse_taostats_timestamp

        # 2024-01-15 12:00:00 UTC
        unix_ts = 1705320000
        result = parse_taostats_timestamp(unix_ts)
        assert result is not None
        assert result.year == 2024

    def test_parse_unix_timestamp_string(self):
        """Parse Unix timestamp as string."""
        from app.services.data.response_models import parse_taostats_timestamp

        result = parse_taostats_timestamp("1705320000")
        assert result is not None
        assert result.year == 2024

    def test_parse_none_returns_none(self):
        """Return None for None input."""
        from app.services.data.response_models import parse_taostats_timestamp

        result = parse_taostats_timestamp(None)
        assert result is None

    def test_parse_empty_string_returns_none(self):
        """Return None for empty string."""
        from app.services.data.response_models import parse_taostats_timestamp

        result = parse_taostats_timestamp("")
        assert result is None

    def test_parse_datetime_passthrough(self):
        """Pass through datetime objects unchanged."""
        from app.services.data.response_models import parse_taostats_timestamp

        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = parse_taostats_timestamp(dt)
        assert result == dt

    def test_parse_invalid_raises(self):
        """Raise ValueError for unparseable input."""
        from app.services.data.response_models import parse_taostats_timestamp

        with pytest.raises(ValueError):
            parse_taostats_timestamp("not-a-timestamp")


class TestResponseModels:
    """Test Pydantic response model validation."""

    def test_subnet_pool_data_validation(self):
        """Validate SubnetPoolData model."""
        from app.services.data.response_models import SubnetPoolData

        data = {
            "netuid": 1,
            "name": "Test Subnet",
            "price": "1.5",
            "market_cap": "1000000000000",
            "timestamp": "2024-01-15T12:00:00Z",
        }

        pool = SubnetPoolData.model_validate(data)
        assert pool.netuid == 1
        assert pool.name == "Test Subnet"
        assert pool.price == "1.5"
        assert pool.price_decimal == Decimal("1.5")

    def test_stake_balance_data_validation(self):
        """Validate StakeBalanceData model."""
        from app.services.data.response_models import StakeBalanceData

        data = {
            "netuid": 1,
            "balance": "5000000000",  # 5 TAO in rao
            "balance_as_tao": "5500000000",  # 5.5 TAO value
            "hotkey": {"ss58": "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"},
        }

        stake = StakeBalanceData.model_validate(data)
        assert stake.netuid == 1
        assert stake.alpha_balance == Decimal("5")  # Converted from rao
        assert stake.tao_value == Decimal("5.5")
        assert stake.hotkey_address == "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"


class TestMetricsCollection:
    """Test metrics collection functionality."""

    def test_metrics_singleton(self):
        """Verify metrics collector is a singleton."""
        from app.core.metrics import get_metrics

        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    @pytest.mark.asyncio
    async def test_record_api_call(self):
        """Test recording API call metrics."""
        from app.core.metrics import get_metrics

        metrics = get_metrics()
        await metrics.record_api_call(
            endpoint="/api/test",
            success=True,
            latency_ms=150.5,
            status_code=200,
        )

        trust_pack = metrics.get_trust_pack()
        assert "api_endpoints" in trust_pack
        assert "/api/test" in trust_pack["api_endpoints"]

    @pytest.mark.asyncio
    async def test_record_cache_hit_miss(self):
        """Test recording cache hit/miss metrics."""
        from app.core.metrics import get_metrics

        metrics = get_metrics()
        await metrics.record_cache_hit("test_key")
        await metrics.record_cache_miss("test_key")

        trust_pack = metrics.get_trust_pack()
        assert "cache_health" in trust_pack
        assert trust_pack["cache_health"]["total_hits"] >= 1
        assert trust_pack["cache_health"]["total_misses"] >= 1

    @pytest.mark.asyncio
    async def test_record_sync_success(self):
        """Test recording sync success metrics."""
        from app.core.metrics import get_metrics

        metrics = get_metrics()
        await metrics.record_sync_success(
            dataset_name="subnets",
            record_count=50,
        )

        trust_pack = metrics.get_trust_pack()
        assert "datasets" in trust_pack
        assert "subnets" in trust_pack["datasets"]
        assert trust_pack["datasets"]["subnets"]["last_success_at"] is not None

    @pytest.mark.asyncio
    async def test_record_sync_failure(self):
        """Test recording sync failure metrics."""
        from app.core.metrics import get_metrics

        metrics = get_metrics()
        await metrics.record_sync_failure(
            dataset_name="test_dataset",
            error_message="Test error",
        )

        trust_pack = metrics.get_trust_pack()
        assert "datasets" in trust_pack
        assert "test_dataset" in trust_pack["datasets"]
        assert trust_pack["datasets"]["test_dataset"]["last_error"] == "Test error"


class TestPartialFailureProtection:
    """Test partial failure protection logic."""

    def test_protection_flag_exists(self):
        """Verify partial failure protection setting exists."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, 'enable_partial_failure_protection')
        assert hasattr(settings, 'min_records_for_valid_sync')

    def test_min_records_default(self):
        """Verify min records default is reasonable."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.min_records_for_valid_sync >= 1


class TestTaoStatsErrorClasses:
    """Test custom exception classes."""

    def test_taostats_error_with_status(self):
        """Test TaoStatsError includes status code."""
        from app.services.data.taostats_client import TaoStatsError

        error = TaoStatsError("Test error", status_code=500)
        assert error.status_code == 500
        assert "Test error" in str(error)

    def test_rate_limit_error_with_retry_after(self):
        """Test TaoStatsRateLimitError includes retry_after."""
        from app.services.data.taostats_client import TaoStatsRateLimitError

        error = TaoStatsRateLimitError("Rate limited", retry_after=60)
        assert error.retry_after == 60
        assert error.status_code == 429
