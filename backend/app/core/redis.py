"""Redis connection and caching utilities.

Redis client is created lazily to avoid import-time side effects.
Cache operations are instrumented for metrics collection.
"""

import json
import logging
from datetime import timedelta
from typing import Any, Optional

import redis.asyncio as redis


logger = logging.getLogger(__name__)

# Redis client - initialized lazily
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get Redis client instance.

    Client is created on first access, not at import time.
    """
    global _redis_client
    if _redis_client is None:
        from app.core.config import get_settings
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


class Cache:
    """Cache utility class for Redis operations.

    All operations are instrumented for metrics collection when
    enable_cache_metrics is True in settings.
    """

    def __init__(self, prefix: str = "tao_treasury"):
        self.prefix = prefix

    def _key(self, key: str) -> str:
        """Generate prefixed cache key."""
        return f"{self.prefix}:{key}"

    def _record_hit(self, key: str) -> None:
        """Record a cache hit in metrics."""
        try:
            from app.core.config import get_settings
            if get_settings().enable_cache_metrics:
                from app.core.metrics import get_metrics
                get_metrics().record_cache_hit(key)
        except Exception:
            pass  # Don't fail cache ops due to metrics

    def _record_miss(self, key: str) -> None:
        """Record a cache miss in metrics."""
        try:
            from app.core.config import get_settings
            if get_settings().enable_cache_metrics:
                from app.core.metrics import get_metrics
                get_metrics().record_cache_miss(key)
        except Exception:
            pass  # Don't fail cache ops due to metrics

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        client = await get_redis()
        value = await client.get(self._key(key))
        if value is not None:
            self._record_hit(key)
            return json.loads(value)
        self._record_miss(key)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> None:
        """Set value in cache with optional TTL."""
        client = await get_redis()
        serialized = json.dumps(value, default=str)
        if ttl:
            await client.setex(self._key(key), ttl, serialized)
        else:
            await client.set(self._key(key), serialized)

    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        client = await get_redis()
        await client.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        client = await get_redis()
        result = await client.exists(self._key(key)) > 0
        if result:
            self._record_hit(key)
        else:
            self._record_miss(key)
        return result

    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key in seconds."""
        client = await get_redis()
        return await client.ttl(self._key(key))

    async def set_hash(self, key: str, mapping: dict, ttl: Optional[timedelta] = None) -> None:
        """Set hash values in cache."""
        client = await get_redis()
        await client.hset(self._key(key), mapping={k: json.dumps(v, default=str) for k, v in mapping.items()})
        if ttl:
            await client.expire(self._key(key), ttl)

    async def get_hash(self, key: str) -> Optional[dict]:
        """Get all hash values from cache."""
        client = await get_redis()
        data = await client.hgetall(self._key(key))
        if data:
            self._record_hit(key)
            return {k: json.loads(v) for k, v in data.items()}
        self._record_miss(key)
        return None

    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: Optional[timedelta] = None
    ) -> Any:
        """Get from cache or compute and cache value.

        Args:
            key: Cache key
            factory: Async callable that produces the value if not cached
            ttl: Optional TTL for cached value

        Returns:
            Cached or freshly computed value
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Compute fresh value
        value = await factory()
        await self.set(key, value, ttl)
        return value


# Default cache instance
cache = Cache()
