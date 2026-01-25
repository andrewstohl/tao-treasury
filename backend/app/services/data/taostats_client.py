"""TaoStats API client with rate limiting and caching.

API Reference: https://docs.taostats.io/reference/welcome-to-the-taostats-api
Base URL: https://api.taostats.io
Auth: Authorization header with API key
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.redis import cache

settings = get_settings()
logger = structlog.get_logger()


class TaoStatsError(Exception):
    """TaoStats API error."""
    pass


class TaoStatsRateLimitError(TaoStatsError):
    """Rate limit exceeded."""
    pass


class TaoStatsClient:
    """Async client for TaoStats API with rate limiting and caching.

    Implements the actual TaoStats API endpoints as documented at:
    https://docs.taostats.io/reference/
    """

    def __init__(self):
        self.base_url = settings.taostats_base_url
        self.api_key = settings.taostats_api_key
        self.rate_limit = settings.taostats_rate_limit_per_minute
        self._request_times: List[datetime] = []
        self._lock = asyncio.Lock()

    def _headers(self) -> Dict[str, str]:
        """Get request headers with authorization."""
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
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
                    logger.warning("Rate limit reached, waiting", wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)

            self._request_times.append(now)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, TaoStatsRateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None,
        cache_ttl: Optional[timedelta] = None,
    ) -> Any:
        """Make an API request with rate limiting and caching."""
        # Check cache first
        if cache_key:
            cached = await cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit", key=cache_key)
                return cached

        await self._check_rate_limit()

        url = f"{self.base_url}{endpoint}"
        logger.debug("API request", method=method, url=url, params=params)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
            )

            if response.status_code == 429:
                logger.warning("Rate limit exceeded from API")
                raise TaoStatsRateLimitError("Rate limit exceeded")

            if response.status_code != 200:
                logger.error("API error", status=response.status_code, body=response.text[:500])
                raise TaoStatsError(
                    f"API error {response.status_code}: {response.text[:500]}"
                )

            data = response.json()

            # Cache the result
            if cache_key and cache_ttl:
                await cache.set(cache_key, data, cache_ttl)
                logger.debug("Cached response", key=cache_key, ttl=cache_ttl)

            return data

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
            await asyncio.sleep(0.1)

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
            await asyncio.sleep(0.1)

        logger.info("Fetched all extrinsics", count=len(all_extrinsics), pages=page)
        return all_extrinsics

    # ==================== Utility Methods ====================

    async def health_check(self) -> bool:
        """Check if API is accessible."""
        try:
            await self.get_tao_price()
            return True
        except Exception as e:
            logger.error("TaoStats health check failed", error=str(e))
            return False


# Singleton client instance
taostats_client = TaoStatsClient()
