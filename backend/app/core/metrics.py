"""Centralized metrics tracking for observability.

Tracks API calls, cache performance, sync status, and errors
for the Trust Pack dashboard.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import structlog

logger = structlog.get_logger()


@dataclass
class APICallMetrics:
    """Metrics for a single API endpoint."""
    endpoint: str
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    rate_limit_count: int = 0  # 429s
    server_error_count: int = 0  # 5xx
    total_latency_ms: float = 0.0
    retry_count: int = 0
    last_call_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None

    @property
    def avg_latency_ms(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count

    @property
    def success_rate(self) -> float:
        if self.call_count == 0:
            return 1.0
        return self.success_count / self.call_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "rate_limit_count": self.rate_limit_count,
            "server_error_count": self.server_error_count,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "retry_count": self.retry_count,
            "success_rate": round(self.success_rate, 4),
            "last_call_at": self.last_call_at.isoformat() if self.last_call_at else None,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
        }


@dataclass
class CacheMetrics:
    """Metrics for cache performance."""
    namespace: str
    hit_count: int = 0
    miss_count: int = 0
    set_count: int = 0
    delete_count: int = 0
    error_count: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        if total == 0:
            return 0.0
        return self.hit_count / total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "set_count": self.set_count,
            "delete_count": self.delete_count,
            "error_count": self.error_count,
            "hit_rate": round(self.hit_rate, 4),
        }


@dataclass
class DatasetSyncStatus:
    """Sync status for a single dataset."""
    dataset_name: str
    last_success_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    record_count: int = 0
    is_stale: bool = False
    has_drift: bool = False
    staleness_threshold_minutes: int = 30

    @property
    def age_minutes(self) -> Optional[float]:
        if self.last_success_at is None:
            return None
        delta = datetime.now(timezone.utc) - self.last_success_at
        return delta.total_seconds() / 60

    def check_staleness(self) -> bool:
        if self.last_success_at is None:
            self.is_stale = True
            return True
        age = self.age_minutes or 0
        self.is_stale = age > self.staleness_threshold_minutes
        return self.is_stale

    def to_dict(self) -> Dict[str, Any]:
        self.check_staleness()
        return {
            "dataset_name": self.dataset_name,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "record_count": self.record_count,
            "age_minutes": round(self.age_minutes, 2) if self.age_minutes else None,
            "is_stale": self.is_stale,
            "has_drift": self.has_drift,
            "staleness_threshold_minutes": self.staleness_threshold_minutes,
        }


class MetricsCollector:
    """Singleton metrics collector for the application."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._api_metrics: Dict[str, APICallMetrics] = {}
        self._cache_metrics: Dict[str, CacheMetrics] = {}
        self._dataset_status: Dict[str, DatasetSyncStatus] = {}
        self._started_at = datetime.now(timezone.utc)

        # Rolling window for recent errors (last 24h)
        self._recent_errors: List[Dict[str, Any]] = []
        self._error_retention_hours = 24

    # ==================== API Metrics ====================

    async def record_api_call(
        self,
        endpoint: str,
        latency_ms: float,
        success: bool,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        retries: int = 0,
        request_id: Optional[str] = None,
    ) -> None:
        """Record an API call result."""
        async with self._lock:
            if endpoint not in self._api_metrics:
                self._api_metrics[endpoint] = APICallMetrics(endpoint=endpoint)

            m = self._api_metrics[endpoint]
            m.call_count += 1
            m.total_latency_ms += latency_ms
            m.retry_count += retries
            m.last_call_at = datetime.now(timezone.utc)

            if success:
                m.success_count += 1
            else:
                m.error_count += 1
                m.last_error = error_message
                m.last_error_at = datetime.now(timezone.utc)

                if status_code == 429:
                    m.rate_limit_count += 1
                elif status_code and status_code >= 500:
                    m.server_error_count += 1

                # Add to recent errors
                self._recent_errors.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "error": error_message,
                    "request_id": request_id,
                })

        # Log structured
        log_data = {
            "endpoint": endpoint,
            "latency_ms": round(latency_ms, 2),
            "success": success,
            "status_code": status_code,
            "retries": retries,
        }
        if request_id:
            log_data["request_id"] = request_id
        if error_message:
            log_data["error"] = error_message[:200]

        if success:
            logger.debug("API call completed", **log_data)
        else:
            logger.warning("API call failed", **log_data)

    def get_api_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get all API metrics."""
        return {
            endpoint: m.to_dict()
            for endpoint, m in self._api_metrics.items()
        }

    def get_api_summary(self) -> Dict[str, Any]:
        """Get aggregated API metrics summary."""
        total_calls = sum(m.call_count for m in self._api_metrics.values())
        total_errors = sum(m.error_count for m in self._api_metrics.values())
        total_429s = sum(m.rate_limit_count for m in self._api_metrics.values())
        total_5xx = sum(m.server_error_count for m in self._api_metrics.values())

        return {
            "total_calls": total_calls,
            "total_errors": total_errors,
            "total_rate_limits": total_429s,
            "total_server_errors": total_5xx,
            "error_rate": round(total_errors / total_calls, 4) if total_calls > 0 else 0,
            "rate_limit_rate": round(total_429s / total_calls, 4) if total_calls > 0 else 0,
            "endpoints_tracked": len(self._api_metrics),
        }

    # ==================== Cache Metrics ====================

    async def record_cache_hit(self, namespace: str = "default") -> None:
        async with self._lock:
            if namespace not in self._cache_metrics:
                self._cache_metrics[namespace] = CacheMetrics(namespace=namespace)
            self._cache_metrics[namespace].hit_count += 1

    async def record_cache_miss(self, namespace: str = "default") -> None:
        async with self._lock:
            if namespace not in self._cache_metrics:
                self._cache_metrics[namespace] = CacheMetrics(namespace=namespace)
            self._cache_metrics[namespace].miss_count += 1

    async def record_cache_set(self, namespace: str = "default") -> None:
        async with self._lock:
            if namespace not in self._cache_metrics:
                self._cache_metrics[namespace] = CacheMetrics(namespace=namespace)
            self._cache_metrics[namespace].set_count += 1

    async def record_cache_error(self, namespace: str = "default") -> None:
        async with self._lock:
            if namespace not in self._cache_metrics:
                self._cache_metrics[namespace] = CacheMetrics(namespace=namespace)
            self._cache_metrics[namespace].error_count += 1

    def get_cache_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get all cache metrics."""
        return {
            ns: m.to_dict()
            for ns, m in self._cache_metrics.items()
        }

    def get_cache_summary(self) -> Dict[str, Any]:
        """Get aggregated cache metrics summary."""
        total_hits = sum(m.hit_count for m in self._cache_metrics.values())
        total_misses = sum(m.miss_count for m in self._cache_metrics.values())
        total = total_hits + total_misses

        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "overall_hit_rate": round(total_hits / total, 4) if total > 0 else 0,
            "namespaces_tracked": len(self._cache_metrics),
        }

    # ==================== Dataset Sync Status ====================

    async def record_sync_success(
        self,
        dataset_name: str,
        record_count: int,
        staleness_threshold_minutes: int = 30,
    ) -> None:
        """Record a successful sync for a dataset."""
        async with self._lock:
            if dataset_name not in self._dataset_status:
                self._dataset_status[dataset_name] = DatasetSyncStatus(
                    dataset_name=dataset_name,
                    staleness_threshold_minutes=staleness_threshold_minutes,
                )

            ds = self._dataset_status[dataset_name]
            ds.last_success_at = datetime.now(timezone.utc)
            ds.last_attempt_at = datetime.now(timezone.utc)
            ds.record_count = record_count
            ds.has_drift = False  # Reset on success

        logger.info(
            "Dataset sync success",
            dataset=dataset_name,
            record_count=record_count,
        )

    async def record_sync_failure(
        self,
        dataset_name: str,
        error_message: str,
        staleness_threshold_minutes: int = 30,
    ) -> None:
        """Record a failed sync for a dataset."""
        async with self._lock:
            if dataset_name not in self._dataset_status:
                self._dataset_status[dataset_name] = DatasetSyncStatus(
                    dataset_name=dataset_name,
                    staleness_threshold_minutes=staleness_threshold_minutes,
                )

            ds = self._dataset_status[dataset_name]
            ds.last_attempt_at = datetime.now(timezone.utc)
            ds.last_error = error_message
            ds.last_error_at = datetime.now(timezone.utc)

        logger.error(
            "Dataset sync failure",
            dataset=dataset_name,
            error=error_message,
        )

    async def record_drift_detected(
        self,
        dataset_name: str,
        drift_details: str,
    ) -> None:
        """Record that drift was detected in a dataset."""
        async with self._lock:
            if dataset_name in self._dataset_status:
                self._dataset_status[dataset_name].has_drift = True

        logger.warning(
            "Dataset drift detected",
            dataset=dataset_name,
            details=drift_details,
        )

    def get_dataset_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all tracked datasets."""
        return {
            name: ds.to_dict()
            for name, ds in self._dataset_status.items()
        }

    # ==================== Trust Pack ====================

    def get_trust_pack(self) -> Dict[str, Any]:
        """Get the complete Trust Pack for observability."""
        # Prune old errors
        self._prune_old_errors()

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": (datetime.now(timezone.utc) - self._started_at).total_seconds(),
            "api_health": self.get_api_summary(),
            "api_endpoints": self.get_api_metrics(),
            "cache_health": self.get_cache_summary(),
            "cache_namespaces": self.get_cache_metrics(),
            "datasets": self.get_dataset_status(),
            "recent_errors": self._recent_errors[-50:],  # Last 50 errors
            "overall_health": self._compute_overall_health(),
        }

    def _compute_overall_health(self) -> Dict[str, Any]:
        """Compute overall system health status."""
        api_summary = self.get_api_summary()
        cache_summary = self.get_cache_summary()

        # Check for issues
        issues = []

        # High error rate
        if api_summary["error_rate"] > 0.1:
            issues.append("High API error rate (>10%)")

        # High rate limit rate
        if api_summary["rate_limit_rate"] > 0.05:
            issues.append("High rate limit rate (>5%)")

        # Low cache hit rate
        if cache_summary["overall_hit_rate"] < 0.5 and cache_summary["total_hits"] + cache_summary["total_misses"] > 100:
            issues.append("Low cache hit rate (<50%)")

        # Stale datasets
        stale_datasets = [
            name for name, ds in self._dataset_status.items()
            if ds.check_staleness()
        ]
        if stale_datasets:
            issues.append(f"Stale datasets: {', '.join(stale_datasets)}")

        # Drift detected
        drift_datasets = [
            name for name, ds in self._dataset_status.items()
            if ds.has_drift
        ]
        if drift_datasets:
            issues.append(f"Drift detected: {', '.join(drift_datasets)}")

        status = "healthy"
        if len(issues) >= 3:
            status = "critical"
        elif len(issues) >= 1:
            status = "degraded"

        return {
            "status": status,
            "issues": issues,
            "issue_count": len(issues),
        }

    def _prune_old_errors(self) -> None:
        """Remove errors older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._error_retention_hours)
        self._recent_errors = [
            e for e in self._recent_errors
            if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) > cutoff
        ]

    async def reset(self) -> None:
        """Reset all metrics (for testing)."""
        async with self._lock:
            self._api_metrics.clear()
            self._cache_metrics.clear()
            self._dataset_status.clear()
            self._recent_errors.clear()
            self._started_at = datetime.now(timezone.utc)


# Lazy singleton
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get or create the metrics collector singleton."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
