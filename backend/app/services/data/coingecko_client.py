"""CoinGecko API client for TAO price data.

Uses the CoinGecko simple/price endpoint to fetch current TAO (Bittensor)
price with 24h and 7d change percentages. Serves as the primary price source
with TaoStats as fallback.

API docs: https://docs.coingecko.com/reference/simple-price
"""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import httpx
import structlog

from app.core.config import get_settings
from app.core.redis import cache

logger = structlog.get_logger()

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
BITTENSOR_ID = "bittensor"
CACHE_KEY = "coingecko:tao_price"
CACHE_TTL_SECONDS = 60  # 1 minute


@dataclass
class TaoPrice:
    """TAO price result from CoinGecko."""
    price_usd: Decimal
    change_24h_pct: Optional[Decimal] = None
    change_7d_pct: Optional[Decimal] = None


async def fetch_tao_price() -> Optional[TaoPrice]:
    """Fetch current TAO price from CoinGecko.

    Returns TaoPrice on success, None on failure.
    Uses Redis cache with 60-second TTL to avoid hitting rate limits.
    """
    settings = get_settings()
    api_key = settings.coingecko_api_key
    if not api_key:
        logger.debug("CoinGecko API key not configured, skipping")
        return None

    # Check cache first
    cached = await cache.get(CACHE_KEY)
    if cached is not None:
        try:
            return TaoPrice(
                price_usd=Decimal(str(cached["price_usd"])),
                change_24h_pct=Decimal(str(cached["change_24h_pct"])) if cached.get("change_24h_pct") is not None else None,
                change_7d_pct=Decimal(str(cached["change_7d_pct"])) if cached.get("change_7d_pct") is not None else None,
            )
        except (KeyError, ValueError, TypeError):
            pass  # Cache corrupt, refetch

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                f"{COINGECKO_BASE_URL}/simple/price",
                params={
                    "ids": BITTENSOR_ID,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_7d_change": "true",
                },
                headers={
                    "x-cg-demo-api-key": api_key,
                    "Accept": "application/json",
                },
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code != 200:
                logger.warning(
                    "CoinGecko API error",
                    status=response.status_code,
                    body=response.text[:200],
                    latency_ms=round(latency_ms, 1),
                )
                return None

            data = response.json()
            bt = data.get(BITTENSOR_ID, {})
            price_usd = bt.get("usd")

            if price_usd is None or price_usd <= 0:
                logger.warning("CoinGecko returned no/zero price", data=data)
                return None

            result = TaoPrice(
                price_usd=Decimal(str(price_usd)),
                change_24h_pct=Decimal(str(round(bt["usd_24h_change"], 2))) if bt.get("usd_24h_change") is not None else None,
                change_7d_pct=Decimal(str(round(bt["usd_7d_change"], 2))) if bt.get("usd_7d_change") is not None else None,
            )

            # Cache the result
            from datetime import timedelta
            await cache.set(
                CACHE_KEY,
                {
                    "price_usd": str(result.price_usd),
                    "change_24h_pct": str(result.change_24h_pct) if result.change_24h_pct is not None else None,
                    "change_7d_pct": str(result.change_7d_pct) if result.change_7d_pct is not None else None,
                },
                timedelta(seconds=CACHE_TTL_SECONDS),
            )

            logger.info(
                "CoinGecko TAO price fetched",
                price_usd=float(result.price_usd),
                change_24h=float(result.change_24h_pct) if result.change_24h_pct else None,
                latency_ms=round(latency_ms, 1),
            )
            return result

    except (httpx.HTTPError, httpx.TimeoutException) as e:
        logger.warning("CoinGecko request failed", error=str(e))
        return None
    except Exception as e:
        logger.warning("CoinGecko unexpected error", error=str(e))
        return None
