"""TaoStats API client with rate limiting, caching, and observability.

API Reference: https://docs.taostats.io/reference/welcome-to-the-taostats-api
Base URL: https://api.taostats.io
Auth: Authorization header with API key

Phase 1 Hardening:
- Retry-After header handling (respect server feedback)
- Exponential backoff with jitter for transient failures
- Configurable timeouts
- Response validation with Pydantic models
- Structured logging with metrics integration
"""

import asyncio
import random
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.redis import cache

logger = structlog.get_logger()

# Type var for generic response validation
T = TypeVar("T", bound=BaseModel)


class TaoStatsError(Exception):
    """TaoStats API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class TaoStatsRateLimitError(TaoStatsError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class TaoStatsValidationError(TaoStatsError):
    """Response validation failed."""
    pass


class TaoStatsClient:
    """Async client for TaoStats API with rate limiting, caching, and observability.

    Implements the actual TaoStats API endpoints as documented at:
    https://docs.taostats.io/reference/

    Phase 1 Hardening Features:
    - Retry-After header handling (respects server feedback on rate limits)
    - Exponential backoff with jitter for transient failures
    - Configurable timeouts from settings
    - Optional response validation with Pydantic models
    - Metrics integration for observability
    """

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.taostats_base_url
        self.api_key = settings.taostats_api_key
        self.rate_limit = settings.taostats_rate_limit_per_minute
        self._request_times: List[datetime] = []
        self._lock = asyncio.Lock()
        self._retry_after_until: Optional[datetime] = None  # Global rate limit state

    def _headers(self) -> Dict[str, str]:
        """Get request headers with authorization."""
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting (both local and server-signaled)."""
        settings = get_settings()

        # Check if we're in a server-signaled rate limit period
        if self._retry_after_until and settings.enable_retry_after:
            now = datetime.utcnow()
            if now < self._retry_after_until:
                wait_time = (self._retry_after_until - now).total_seconds()
                logger.warning(
                    "Waiting for Retry-After period",
                    wait_seconds=wait_time,
                    until=self._retry_after_until.isoformat(),
                )
                await asyncio.sleep(wait_time)
                self._retry_after_until = None

        # Local rate limiting
        async with self._lock:
            now = datetime.utcnow()
            # Remove requests older than 1 minute
            self._request_times = [
                t for t in self._request_times
                if (now - t).total_seconds() < 60
            ]

            if len(self._request_times) >= self.rate_limit:
                oldest = self._request_times[0]
                wait_time = 60 - (now - oldest).total_seconds()
                if wait_time > 0:
                    logger.warning("Local rate limit reached, waiting", wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)

            self._request_times.append(now)

    def _parse_retry_after(self, response: httpx.Response) -> Optional[int]:
        """Parse Retry-After header from response.

        Handles both delta-seconds and HTTP-date formats.
        Returns seconds to wait, or None if not present/parseable.
        """
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None

        # Try as integer (delta-seconds)
        try:
            return int(retry_after)
        except ValueError:
            pass

        # Try as HTTP-date (RFC 7231)
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(retry_after)
            delta = (dt - datetime.now(dt.tzinfo)).total_seconds()
            return max(0, int(delta))
        except (ValueError, TypeError):
            pass

        return None

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate backoff delay with jitter.

        Uses exponential backoff: base * multiplier^attempt + random jitter
        """
        settings = get_settings()
        base = settings.api_initial_backoff_seconds
        multiplier = settings.api_backoff_multiplier
        max_backoff = settings.api_max_backoff_seconds

        delay = base * (multiplier ** attempt)
        delay = min(delay, max_backoff)

        # Add jitter (0-25% of delay)
        jitter = random.uniform(0, 0.25 * delay)
        return delay + jitter

    def _record_api_call(
        self,
        endpoint: str,
        success: bool,
        latency_ms: float,
        status_code: Optional[int] = None,
    ) -> None:
        """Record API call metrics (fire-and-forget async)."""
        try:
            settings = get_settings()
            if settings.enable_api_metrics:
                from app.core.metrics import get_metrics

                async def _record():
                    try:
                        await get_metrics().record_api_call(
                            endpoint=endpoint,
                            success=success,
                            latency_ms=latency_ms,
                            status_code=status_code,
                        )
                    except Exception:
                        pass

                # Schedule as task if we're in an event loop
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_record())
                except RuntimeError:
                    pass  # No event loop, skip metrics
        except Exception:
            pass  # Don't fail API calls due to metrics

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None,
        cache_ttl: Optional[timedelta] = None,
        response_model: Optional[Type[T]] = None,
    ) -> Any:
        """Make an API request with rate limiting, retries, and caching.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            cache_key: Optional cache key for caching response
            cache_ttl: Optional TTL for cached response
            response_model: Optional Pydantic model for response validation

        Returns:
            Parsed JSON response (optionally validated)

        Raises:
            TaoStatsError: On API errors
            TaoStatsRateLimitError: On rate limit (after retries exhausted)
            TaoStatsValidationError: On response validation failure
        """
        settings = get_settings()

        # Check cache first
        if cache_key:
            cached = await cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit", key=cache_key, endpoint=endpoint)
                return cached

        await self._check_rate_limit()

        url = f"{self.base_url}{endpoint}"
        last_error: Optional[Exception] = None
        start_time = time.monotonic()

        # Configure timeout
        timeout = httpx.Timeout(
            connect=settings.api_connect_timeout_seconds,
            read=settings.api_read_timeout_seconds,
            write=10.0,
            pool=5.0,
        )

        for attempt in range(settings.api_max_retries + 1):
            try:
                logger.debug(
                    "API request",
                    method=method,
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    params=params,
                )

                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=self._headers(),
                        params=params,
                    )

                    latency_ms = (time.monotonic() - start_time) * 1000

                    # Handle rate limiting with Retry-After
                    if response.status_code == 429:
                        retry_after = self._parse_retry_after(response)

                        if retry_after and settings.enable_retry_after:
                            # Cap the wait time
                            retry_after = min(retry_after, settings.retry_after_max_wait_seconds)
                            self._retry_after_until = datetime.utcnow() + timedelta(seconds=retry_after)

                            logger.warning(
                                "Rate limit exceeded, Retry-After received",
                                retry_after_seconds=retry_after,
                                endpoint=endpoint,
                            )

                            self._record_api_call(endpoint, False, latency_ms, 429)

                            # If we have retries left, wait and retry
                            if attempt < settings.api_max_retries:
                                await asyncio.sleep(retry_after)
                                start_time = time.monotonic()  # Reset for next attempt
                                continue

                        raise TaoStatsRateLimitError(
                            "Rate limit exceeded",
                            retry_after=retry_after,
                        )

                    # Handle other errors
                    if response.status_code != 200:
                        self._record_api_call(endpoint, False, latency_ms, response.status_code)
                        error_body = response.text[:500]
                        logger.error(
                            "API error",
                            status=response.status_code,
                            endpoint=endpoint,
                            body=error_body,
                        )
                        raise TaoStatsError(
                            f"API error {response.status_code}: {error_body}",
                            status_code=response.status_code,
                        )

                    # Success
                    data = response.json()
                    self._record_api_call(endpoint, True, latency_ms, 200)

                    # Validate response if model provided and validation enabled
                    if response_model and settings.enable_response_validation:
                        try:
                            # For list responses, validate the data array
                            if "data" in data and isinstance(data["data"], list):
                                validated_items = []
                                for item in data["data"]:
                                    validated_items.append(response_model.model_validate(item))
                                # Keep original structure but could use validated data
                            else:
                                response_model.model_validate(data)
                        except ValidationError as e:
                            logger.warning(
                                "Response validation warning",
                                endpoint=endpoint,
                                errors=str(e),
                            )
                            # Don't fail on validation - just log warning
                            # This allows graceful degradation if API changes

                    # Cache the result
                    if cache_key and cache_ttl:
                        await cache.set(cache_key, data, cache_ttl)
                        logger.debug("Cached response", key=cache_key, ttl_seconds=cache_ttl.total_seconds())

                    return data

            except (httpx.HTTPError, httpx.TimeoutException) as e:
                latency_ms = (time.monotonic() - start_time) * 1000
                self._record_api_call(endpoint, False, latency_ms, None)
                last_error = e

                if attempt < settings.api_max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        "Transient error, retrying",
                        endpoint=endpoint,
                        attempt=attempt + 1,
                        backoff_seconds=backoff,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff)
                    start_time = time.monotonic()  # Reset for next attempt
                else:
                    logger.error(
                        "Request failed after retries",
                        endpoint=endpoint,
                        attempts=settings.api_max_retries + 1,
                        error=str(e),
                    )

        # All retries exhausted
        raise TaoStatsError(
            f"Request failed after {settings.api_max_retries + 1} attempts: {last_error}",
        )

    # ==================== Account/Wallet Endpoints ====================

    async def get_account(
        self,
        address: str,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get account information including balances.

        Endpoint: GET /api/account/latest/v1
        """
        return await self._request(
            "GET",
            "/api/account/latest/v1",
            params={"address": address, "network": network},
            cache_key=f"account:{address}",
            cache_ttl=timedelta(minutes=2),
        )

    async def get_account_history(
        self,
        address: str,
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get historical account data.

        Endpoint: GET /api/account/history/v1
        """
        params = {"address": address, "network": network, "limit": limit}
        if timestamp_start:
            params["timestamp_start"] = timestamp_start
        if timestamp_end:
            params["timestamp_end"] = timestamp_end

        return await self._request(
            "GET",
            "/api/account/history/v1",
            params=params,
            cache_key=f"account_history:{address}:{timestamp_start}:{timestamp_end}",
            cache_ttl=timedelta(minutes=30),
        )

    # ==================== Stake Balance Endpoints ====================

    async def get_stake_balance(
        self,
        coldkey: Optional[str] = None,
        limit: int = 200,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get current stake balances for all subnets.

        Endpoint: GET /api/dtao/stake_balance/latest/v1

        Note: Use 'coldkey' parameter to get all dTAO positions.
        The 'address' parameter only returns Root (SN0) stakes.
        """
        params = {"network": network, "limit": limit}
        if coldkey:
            params["coldkey"] = coldkey

        cache_key = f"stake_balance:{coldkey or 'all'}"
        return await self._request(
            "GET",
            "/api/dtao/stake_balance/latest/v1",
            params=params,
            cache_key=cache_key,
            cache_ttl=timedelta(minutes=2),
        )

    async def get_stake_balance_history(
        self,
        address: str,
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get historical stake balances (daily at midnight UTC).

        Endpoint: GET /api/dtao/stake_balance/history/v1
        """
        params = {"address": address, "network": network, "limit": limit}
        if timestamp_start:
            params["timestamp_start"] = timestamp_start
        if timestamp_end:
            params["timestamp_end"] = timestamp_end

        return await self._request(
            "GET",
            "/api/dtao/stake_balance/history/v1",
            params=params,
            cache_key=f"stake_history:{address}:{timestamp_start}:{timestamp_end}",
            cache_ttl=timedelta(minutes=30),
        )

    # ==================== Subnet Endpoints ====================

    async def get_subnets(
        self,
        limit: int = 200,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get all subnets with current metrics.

        Endpoint: GET /api/subnet/latest/v1
        """
        return await self._request(
            "GET",
            "/api/subnet/latest/v1",
            params={"network": network, "limit": limit},
            cache_key="subnets:all",
            cache_ttl=timedelta(minutes=5),
        )

    # ==================== dTAO Pool Endpoints ====================

    async def get_pools(
        self,
        limit: int = 200,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get current pool liquidity for all subnets.

        Endpoint: GET /api/dtao/pool/latest/v1
        """
        return await self._request(
            "GET",
            "/api/dtao/pool/latest/v1",
            params={"network": network, "limit": limit},
            cache_key="pools:all",
            cache_ttl=timedelta(minutes=2),
        )

    async def get_pools_full(
        self,
        limit: int = 200,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get full dTAO pool data including sparklines, sentiment, volumes.

        Same endpoint as get_pools() but with a separate cache key so
        the enriched endpoint caching doesn't conflict with sync caching.

        Endpoint: GET /api/dtao/pool/latest/v1
        """
        return await self._request(
            "GET",
            "/api/dtao/pool/latest/v1",
            params={"network": network, "limit": limit},
            cache_key="pools:full",
            cache_ttl=timedelta(minutes=2),
        )

    async def get_subnet_identity(
        self,
        limit: int = 200,
        network: str = "finney",
    ) -> Dict[str, Any]:
        """Get subnet identity metadata (description, summary, tags, links, logo).

        Endpoint: GET /api/subnet/identity/v1
        """
        return await self._request(
            "GET",
            "/api/subnet/identity/v1",
            params={"network": network, "limit": limit},
            cache_key="subnet_identity:all",
            cache_ttl=timedelta(minutes=30),
        )

    async def get_dev_activity(
        self,
        limit: int = 200,
        network: str = "finney",
    ) -> Dict[str, Any]:
        """Get subnet developer activity metrics.

        Endpoint: GET /api/dev_activity/latest/v1
        """
        return await self._request(
            "GET",
            "/api/dev_activity/latest/v1",
            params={"network": network, "limit": limit},
            cache_key="dev_activity:all",
            cache_ttl=timedelta(minutes=30),
        )

    async def get_pool_history(
        self,
        netuid: Optional[int] = None,
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get historical pool data.

        Endpoint: GET /api/dtao/pool/history/v1
        """
        params = {"network": network, "limit": limit}
        if netuid is not None:
            params["netuid"] = netuid
        if timestamp_start:
            params["timestamp_start"] = timestamp_start
        if timestamp_end:
            params["timestamp_end"] = timestamp_end

        cache_suffix = f"{netuid or 'all'}:{timestamp_start}:{timestamp_end}"
        return await self._request(
            "GET",
            "/api/dtao/pool/history/v1",
            params=params,
            cache_key=f"pool_history:{cache_suffix}",
            cache_ttl=timedelta(minutes=30),
        )

    # ==================== TradingView Chart Endpoints ====================

    async def get_tradingview_ohlc(
        self,
        netuid: int,
        resolution: str = "60",
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get OHLC candlestick data for a subnet via TradingView UDF endpoint.

        Endpoint: GET /api/dtao/tradingview/udf/history

        This endpoint returns proper OHLC (Open, High, Low, Close) data suitable
        for candlestick charts, following the TradingView UDF format.

        Args:
            netuid: Subnet ID
            resolution: Candle timeframe. Common values:
                - "1", "5", "15", "30", "60" (minutes)
                - "D" (daily), "W" (weekly)
            timestamp_start: Unix timestamp for start of data range
            timestamp_end: Unix timestamp for end of data range
            network: Network name (default "finney")

        Returns:
            TradingView UDF format response with:
            - t: array of timestamps
            - o: array of open prices
            - h: array of high prices
            - l: array of low prices
            - c: array of close prices
            - v: array of volumes (optional)
            - s: status ("ok" or "no_data")
        """
        import time as time_module

        # Default to last 30 days if not specified
        if timestamp_end is None:
            timestamp_end = int(time_module.time())
        if timestamp_start is None:
            timestamp_start = timestamp_end - (30 * 24 * 60 * 60)  # 30 days ago

        params = {
            "symbol": f"SUB-{netuid}",
            "resolution": resolution,
            "from": timestamp_start,
            "to": timestamp_end,
        }

        # Short cache since this is chart data that updates
        cache_key = f"tradingview_ohlc:{netuid}:{resolution}:{timestamp_start}:{timestamp_end}"
        return await self._request(
            "GET",
            "/api/dtao/tradingview/udf/history",
            params=params,
            cache_key=cache_key,
            cache_ttl=timedelta(minutes=5),
        )

    # ==================== Slippage Endpoints ====================

    async def get_slippage(
        self,
        netuid: int,
        amount: Decimal,
        action: str = "unstake",  # stake or unstake
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Estimate slippage for an alpha/TAO transaction.

        Endpoint: GET /api/dtao/slippage/v1

        Args:
            netuid: Subnet ID
            amount: Amount in TAO
            action: 'stake' (buy alpha) or 'unstake' (sell alpha)

        Note: The API requires:
            - input_tokens in rao (1 TAO = 1e9 rao)
            - direction: 'AlphaToTao' (unstake/sell) or 'TaoToAlpha' (stake/buy)
        """
        # Convert TAO to rao for the API
        input_tokens = int(amount * Decimal("1000000000"))

        # Map action to API direction (API expects lowercase snake_case)
        direction = "alpha_to_tao" if action == "unstake" else "tao_to_alpha"

        params = {
            "netuid": netuid,
            "input_tokens": str(input_tokens),
            "direction": direction,
            "network": network,
        }
        # Short cache for slippage - it changes frequently
        return await self._request(
            "GET",
            "/api/dtao/slippage/v1",
            params=params,
            cache_key=f"slippage:{netuid}:{action}:{amount}",
            cache_ttl=timedelta(minutes=1),
        )

    # ==================== Validator Endpoints ====================

    async def get_validators(
        self,
        netuid: Optional[int] = None,
        limit: int = 200,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get validator data.

        Endpoint: GET /api/dtao/validator/latest/v1
        """
        params = {"network": network, "limit": limit}
        if netuid is not None:
            params["netuid"] = netuid

        return await self._request(
            "GET",
            "/api/dtao/validator/latest/v1",
            params=params,
            cache_key=f"validators:{netuid or 'all'}",
            cache_ttl=timedelta(minutes=10),
        )

    async def get_validator_yield(
        self,
        netuid: Optional[int] = None,
        limit: int = 200,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get validator yield data.

        Endpoint: GET /api/dtao/validator/yield/latest/v1
        """
        params = {"network": network, "limit": limit}
        if netuid is not None:
            params["netuid"] = netuid

        return await self._request(
            "GET",
            "/api/dtao/validator/yield/latest/v1",
            params=params,
            cache_key=f"validator_yield:{netuid or 'all'}",
            cache_ttl=timedelta(minutes=10),
        )

    # ==================== Price Endpoints ====================

    async def get_tao_price(self, network: str = "finney") -> Dict[str, Any]:
        """Get current TAO price in USD.

        Endpoint: GET /api/price/latest/v1
        """
        return await self._request(
            "GET",
            "/api/price/latest/v1",
            params={"asset": "tao", "network": network},
            cache_key="price:tao",
            cache_ttl=timedelta(minutes=1),
        )

    async def get_price_history(
        self,
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get historical TAO prices.

        Endpoint: GET /api/price/history/v1
        """
        params = {"asset": "tao", "network": network, "limit": limit}
        if timestamp_start:
            params["timestamp_start"] = timestamp_start
        if timestamp_end:
            params["timestamp_end"] = timestamp_end

        return await self._request(
            "GET",
            "/api/price/history/v1",
            params=params,
            cache_key=f"price_history:{timestamp_start}:{timestamp_end}",
            cache_ttl=timedelta(minutes=5),
        )

    # ==================== dTAO Trade Endpoints ====================

    async def get_trades(
        self,
        coldkey: str,
        page: int = 1,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get dTAO trades (stake/unstake) for a wallet.

        Endpoint: GET /api/dtao/trade/v1

        Returns trades with:
        - from_name/to_name: TAO or subnet name (e.g., SN19)
        - from_amount/to_amount: amounts in rao
        - tao_value: TAO value of the trade
        - usd_value: USD value at time of trade
        """
        params = {
            "coldkey": coldkey,
            "network": network,
            "limit": limit,
            "page": page,
        }

        # Don't cache trade data - we want fresh data
        return await self._request(
            "GET",
            "/api/dtao/trade/v1",
            params=params,
            cache_key=None,
            cache_ttl=None,
        )

    async def get_all_trades(
        self,
        coldkey: str,
        max_pages: int = 100,
        network: str = "finney"
    ) -> List[Dict[str, Any]]:
        """Fetch all dTAO trades for a wallet across multiple pages.

        Args:
            coldkey: Wallet address
            max_pages: Maximum pages to fetch (safety limit)
            network: Network name

        Returns:
            List of all trades
        """
        all_trades = []
        page = 1

        while page <= max_pages:
            response = await self.get_trades(
                coldkey=coldkey,
                page=page,
                limit=50,
                network=network,
            )

            data = response.get("data", [])
            if not data:
                break

            all_trades.extend(data)

            # Check pagination
            pagination = response.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)

            if page >= total_pages:
                break

            page += 1

            # Rate limit protection
            await asyncio.sleep(1.0)  # Respect rate limit: 60 req/min = 1 req/sec

        logger.info("Fetched all trades", count=len(all_trades), pages=page)
        return all_trades

    # ==================== Extrinsic/Transaction Endpoints ====================

    async def get_extrinsics(
        self,
        address: str,
        page: int = 1,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get extrinsics (transactions) for an address.

        Endpoint: GET /api/extrinsic/v1

        Returns all types of transactions including:
        - SubtensorModule.add_stake_limit (buying alpha)
        - SubtensorModule.remove_stake_limit (selling alpha)
        - SubtensorModule.unstake_all
        - Balances.transfer_keep_alive
        """
        params = {
            "address": address,
            "network": network,
            "limit": limit,
            "page": page,
        }

        # Don't cache transaction data - we want fresh data
        return await self._request(
            "GET",
            "/api/extrinsic/v1",
            params=params,
            cache_key=None,  # No caching for transactions
            cache_ttl=None,
        )

    async def get_all_extrinsics(
        self,
        address: str,
        max_pages: int = 100,
        network: str = "finney"
    ) -> List[Dict[str, Any]]:
        """Fetch all extrinsics for an address across multiple pages.

        Args:
            address: Wallet address
            max_pages: Maximum pages to fetch (safety limit)
            network: Network name

        Returns:
            List of all extrinsics
        """
        all_extrinsics = []
        page = 1

        while page <= max_pages:
            response = await self.get_extrinsics(
                address=address,
                page=page,
                limit=50,
                network=network,
            )

            data = response.get("data", [])
            if not data:
                break

            all_extrinsics.extend(data)

            # Check pagination
            pagination = response.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)

            if page >= total_pages:
                break

            page += 1

            # Rate limit protection
            await asyncio.sleep(1.0)  # Respect rate limit: 60 req/min = 1 req/sec

        logger.info("Fetched all extrinsics", count=len(all_extrinsics), pages=page)
        return all_extrinsics

    # ==================== Delegation/Staking Events ====================

    async def get_delegation_events(
        self,
        coldkey: str,
        page: int = 1,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get staking/delegation events for a wallet.

        Endpoint: GET /api/delegation/v1

        Returns events including:
        - Stake additions (add_stake, add_stake_limit)
        - Stake removals (remove_stake, unstake_all)
        - Timestamps and amounts
        """
        params = {
            "coldkey": coldkey,
            "network": network,
            "limit": limit,
            "page": page,
        }

        return await self._request(
            "GET",
            "/api/delegation/v1",
            params=params,
            cache_key=None,
            cache_ttl=None,
        )

    async def get_all_delegation_events(
        self,
        coldkey: str,
        max_pages: int = 100,
        network: str = "finney"
    ) -> List[Dict[str, Any]]:
        """Fetch all delegation events for a wallet across multiple pages.

        Args:
            coldkey: Wallet address
            max_pages: Maximum pages to fetch (safety limit)
            network: Network name

        Returns:
            List of all delegation events
        """
        all_events = []
        page = 1

        while page <= max_pages:
            response = await self.get_delegation_events(
                coldkey=coldkey,
                page=page,
                limit=50,
                network=network,
            )

            data = response.get("data", [])
            if not data:
                break

            all_events.extend(data)

            # Check pagination
            pagination = response.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)

            if page >= total_pages:
                break

            page += 1
            await asyncio.sleep(1.0)  # Respect rate limit: 60 req/min = 1 req/sec

        logger.info("Fetched all delegation events", count=len(all_events), pages=page)
        return all_events

    # ==================== Emissions Endpoints ====================

    async def get_hotkey_emissions(
        self,
        hotkey: str,
        netuid: Optional[int] = None,
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get emissions data for a hotkey.

        Endpoint: GET /api/hotkey/emission/v1

        Returns emission data including:
        - Daily emissions in rao
        - Subnet breakdown
        - Timestamp of emission
        """
        params = {
            "hotkey": hotkey,
            "network": network,
            "limit": limit,
        }
        if netuid is not None:
            params["netuid"] = netuid
        if timestamp_start:
            params["timestamp_start"] = timestamp_start
        if timestamp_end:
            params["timestamp_end"] = timestamp_end

        return await self._request(
            "GET",
            "/api/hotkey/emission/v1",
            params=params,
            cache_key=f"emissions:{hotkey}:{netuid}:{timestamp_start}:{timestamp_end}",
            cache_ttl=timedelta(minutes=30),
        )

    async def get_stake_balance_history(
        self,
        coldkey: str,
        hotkey: Optional[str] = None,
        netuid: Optional[int] = None,
        timestamp_start: Optional[int] = None,
        timestamp_end: Optional[int] = None,
        limit: int = 50,
        network: str = "finney"
    ) -> Dict[str, Any]:
        """Get historical stake balance for a wallet (daily snapshots).

        Endpoint: GET /api/dtao/stake_balance/history/v1

        Note: The API requires a hotkey parameter for stake balance history.

        Returns daily stake balance snapshots with:
        - balance: Alpha balance at that time
        - balance_as_tao: TAO value at that time
        - timestamp: Daily snapshot time (midnight UTC)
        """
        params = {
            "coldkey": coldkey,
            "network": network,
            "limit": limit,
        }
        if hotkey:
            params["hotkey"] = hotkey
        if netuid is not None:
            params["netuid"] = netuid
        if timestamp_start:
            params["timestamp_start"] = timestamp_start
        if timestamp_end:
            params["timestamp_end"] = timestamp_end

        return await self._request(
            "GET",
            "/api/dtao/stake_balance/history/v1",
            params=params,
            cache_key=f"stake_balance_history:{coldkey}:{netuid}:{timestamp_start}:{timestamp_end}",
            cache_ttl=timedelta(minutes=30),
        )

    # ==================== Accounting/Tax Endpoints ====================

    async def get_accounting_tax(
        self,
        coldkey: str,
        token: str = "TAO",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        page: int = 1,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """Get accounting/tax data for a wallet (paid tier).

        Endpoint: GET /api/accounting/tax/v1

        Returns complete transaction history including token_swap,
        transfer_in, transfer_out, daily_income records.

        Args:
            coldkey: Wallet address
            token: Token name (default "TAO")
            date_start: Start date (YYYY-MM-DD)
            date_end: End date (YYYY-MM-DD), max 12 month span
            page: Page number
            limit: Records per page (up to 500)
        """
        params = {
            "coldkey": coldkey,
            "token": token,
            "limit": limit,
            "page": page,
        }
        if date_start:
            params["date_start"] = date_start
        if date_end:
            params["date_end"] = date_end

        return await self._request(
            "GET",
            "/api/accounting/tax/v1",
            params=params,
            cache_key=None,  # Don't cache accounting data
            cache_ttl=None,
        )

    async def get_all_accounting_tax(
        self,
        coldkey: str,
        token: str = "TAO",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        max_pages: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch all accounting/tax records across multiple pages.

        Args:
            coldkey: Wallet address
            token: Token name
            date_start: Start date (YYYY-MM-DD)
            date_end: End date (YYYY-MM-DD)
            max_pages: Maximum pages to fetch

        Returns:
            List of all accounting records
        """
        all_records: List[Dict[str, Any]] = []
        page = 1

        while page <= max_pages:
            response = await self.get_accounting_tax(
                coldkey=coldkey,
                token=token,
                date_start=date_start,
                date_end=date_end,
                page=page,
                limit=500,
            )

            data = response.get("data", [])
            if not data:
                break

            all_records.extend(data)

            pagination = response.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)

            if page >= total_pages:
                break

            page += 1
            await asyncio.sleep(1.0)  # Respect rate limit: 60 req/min = 1 req/sec

        logger.info("Fetched all accounting/tax records", count=len(all_records), pages=page)
        return all_records

    # ==================== Utility Methods ====================

    async def health_check(self) -> bool:
        """Check if API is accessible using cached state.

        Does NOT make a live API call - instead checks if we've had
        successful API calls recently. This prevents health checks
        from consuming rate limit quota.
        """
        # Check if we're currently rate limited
        if self._retry_after_until:
            now = datetime.utcnow()
            if now < self._retry_after_until:
                logger.debug("Health check: rate limited", until=self._retry_after_until.isoformat())
                return False

        # Check if we've had recent successful requests (within last 5 minutes)
        if self._request_times:
            latest_request = max(self._request_times)
            age_seconds = (datetime.utcnow() - latest_request).total_seconds()
            if age_seconds < 300:  # Had successful request in last 5 min
                return True

        # No recent activity - check cache for any recent data
        try:
            cached = await cache.get("tao_price:finney")
            if cached is not None:
                return True
        except Exception:
            pass

        # No cached data and no recent requests - assume unhealthy
        # but don't make a new API call
        logger.debug("Health check: no recent activity or cached data")
        return False


# Lazy singleton client instance
_taostats_client: Optional[TaoStatsClient] = None


def get_taostats_client() -> TaoStatsClient:
    """Get or create the TaoStats client singleton.

    Client is created on first access, not at import time.
    """
    global _taostats_client
    if _taostats_client is None:
        _taostats_client = TaoStatsClient()
    return _taostats_client


# Backwards compatibility alias - will be resolved lazily
class _LazyClient:
    """Lazy proxy for backwards compatibility with taostats_client usage."""

    def __getattr__(self, name):
        return getattr(get_taostats_client(), name)


taostats_client = _LazyClient()
