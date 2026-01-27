# Phase 0 + Phase 1 Runbook

This document covers the observability and client hardening features implemented in Phase 0 and Phase 1.

## Overview

### Phase 0: Observability (Trust Pack)
- Centralized metrics collection for API calls, cache, and sync status
- `/api/v1/trust-pack` endpoint for observability dashboard
- Per-dataset staleness tracking

### Phase 1: Client Hardening
- Retry-After header handling (respects TaoStats rate limit signals)
- Exponential backoff with jitter for transient failures
- Configurable timeouts
- Partial failure protection (never overwrite good data with empty responses)
- Response validation with Pydantic models

---

## Trust Pack Endpoint

### Accessing the Trust Pack

```bash
curl http://localhost:8050/api/v1/trust-pack | jq
```

### Trust Pack Structure

```json
{
  "generated_at": "2024-01-15T12:00:00Z",
  "uptime_seconds": 3600,
  "api_health": {
    "total_calls": 150,
    "total_errors": 3,
    "total_rate_limits": 1,
    "error_rate": 0.02,
    "rate_limit_rate": 0.0067
  },
  "api_endpoints": {
    "/api/dtao/pool/latest/v1": {
      "call_count": 50,
      "success_rate": 0.98,
      "avg_latency_ms": 245.5,
      "rate_limit_count": 0
    }
  },
  "cache_health": {
    "total_hits": 120,
    "total_misses": 30,
    "overall_hit_rate": 0.8
  },
  "datasets": {
    "subnets": {
      "last_success_at": "2024-01-15T11:55:00Z",
      "record_count": 64,
      "age_minutes": 5.0,
      "is_stale": false,
      "has_drift": false
    }
  },
  "feature_flags": {
    "enable_retry_after": true,
    "enable_partial_failure_protection": true
  },
  "overall_health": {
    "status": "healthy",
    "issues": []
  }
}
```

### Health Status Interpretation

| Status | Meaning |
|--------|---------|
| `healthy` | No issues detected |
| `degraded` | 1-2 issues (e.g., stale dataset, high error rate) |
| `critical` | 3+ issues requiring immediate attention |

### Common Issues Flagged

1. **High API error rate (>10%)** - API returning errors frequently
2. **High rate limit rate (>5%)** - Hitting TaoStats rate limits too often
3. **Low cache hit rate (<50%)** - Cache not being utilized effectively
4. **Stale datasets** - Data hasn't been synced within threshold
5. **Drift detected** - Reconciliation found data inconsistencies

---

## Feature Flags

### Viewing Current Flag States

Check the Trust Pack endpoint or inspect settings:

```python
from app.core.config import get_settings
settings = get_settings()

print(f"Retry-After enabled: {settings.enable_retry_after}")
print(f"Partial failure protection: {settings.enable_partial_failure_protection}")
print(f"Response validation: {settings.enable_response_validation}")
print(f"Client-side slippage: {settings.enable_client_side_slippage}")
```

### Flag Descriptions

| Flag | Default | Purpose |
|------|---------|---------|
| `enable_retry_after` | True | Respect Retry-After headers from API |
| `enable_partial_failure_protection` | True | Don't overwrite good data with empty responses |
| `enable_response_validation` | True | Validate API responses with Pydantic |
| `enable_client_side_slippage` | False | Use local slippage calculation (Phase 1.5) |
| `enable_reconciliation` | False | Enable periodic data reconciliation (Phase 1.5) |
| `enable_cache_metrics` | True | Track cache hit/miss rates |
| `enable_api_metrics` | True | Track API call latency and errors |
| `enable_sync_metrics` | True | Track sync job success/failure |

### Toggling Flags

Set via environment variables:

```bash
export ENABLE_RETRY_AFTER=true
export ENABLE_PARTIAL_FAILURE_PROTECTION=true
export ENABLE_CLIENT_SIDE_SLIPPAGE=false
```

Or in `.env` file:

```
ENABLE_RETRY_AFTER=true
ENABLE_PARTIAL_FAILURE_PROTECTION=true
```

---

## Retry-After Handling

### How It Works

1. When TaoStats returns 429 (rate limited), we check for `Retry-After` header
2. If present, we wait the specified time before retrying
3. Wait time is capped at `retry_after_max_wait_seconds` (default: 300s)
4. If no header present, we use exponential backoff

### Monitoring Rate Limits

```bash
# Check rate limit hits in Trust Pack
curl http://localhost:8050/api/v1/trust-pack | jq '.api_health.total_rate_limits'

# Check per-endpoint rate limits
curl http://localhost:8050/api/v1/trust-pack | jq '.api_endpoints | to_entries[] | select(.value.rate_limit_count > 0)'
```

### Tuning Parameters

```bash
# Max wait from Retry-After header (seconds)
export RETRY_AFTER_MAX_WAIT_SECONDS=300

# Backoff parameters
export API_INITIAL_BACKOFF_SECONDS=1.0
export API_MAX_BACKOFF_SECONDS=60.0
export API_BACKOFF_MULTIPLIER=2.0
export API_MAX_RETRIES=3
```

---

## Partial Failure Protection

### Purpose

Prevents sync jobs from overwriting valid cached/stored data when the API returns empty or insufficient results. This protects against:

- API outages returning empty data
- Rate limiting causing partial responses
- Network issues causing timeouts

### How It Works

1. After API call, check if response has minimum required records
2. If `len(data) < min_records_for_valid_sync`, skip the update
3. Log a warning and record sync failure in metrics
4. Existing data remains unchanged

### Configuration

```bash
# Enable/disable protection
export ENABLE_PARTIAL_FAILURE_PROTECTION=true

# Minimum records required for valid sync
export MIN_RECORDS_FOR_VALID_SYNC=1
```

### Monitoring

Check for partial failure events:

```bash
# Look for sync failures in logs
grep "Subnet sync returned insufficient data" /var/log/tao-treasury/*.log

# Check dataset sync status in Trust Pack
curl http://localhost:8050/api/v1/trust-pack | jq '.datasets'
```

---

## Staleness Monitoring

### Thresholds

| Level | Default | Meaning |
|-------|---------|---------|
| Warning | 15 min | Dataset may be stale |
| Critical | 60 min | Dataset is critically stale |

### Checking Staleness

```bash
# Via Trust Pack
curl http://localhost:8050/api/v1/trust-pack | jq '.datasets | to_entries[] | select(.value.is_stale == true)'

# Via health endpoint
curl http://localhost:8050/api/v1/health | jq '.data_stale'
```

### Tuning Thresholds

```bash
export SYNC_STALENESS_WARNING_MINUTES=15
export SYNC_STALENESS_CRITICAL_MINUTES=60
export STALE_DATA_THRESHOLD_MINUTES=30
```

---

## Timeout Configuration

### HTTP Timeouts

```bash
# Connection timeout (seconds)
export API_CONNECT_TIMEOUT_SECONDS=10.0

# Read timeout (seconds)
export API_READ_TIMEOUT_SECONDS=30.0
```

### When to Adjust

- **Increase connect timeout**: If experiencing connection issues with TaoStats
- **Increase read timeout**: If complex queries are timing out
- **Decrease timeouts**: If you want faster failure detection

---

## Troubleshooting

### High Error Rate

1. Check Trust Pack for specific endpoint errors:
   ```bash
   curl http://localhost:8050/api/v1/trust-pack | jq '.api_endpoints | to_entries[] | select(.value.error_rate > 0.1)'
   ```

2. Check recent errors:
   ```bash
   curl http://localhost:8050/api/v1/trust-pack | jq '.recent_errors[-5:]'
   ```

3. Verify API key is valid:
   ```bash
   curl -H "Authorization: $TAOSTATS_API_KEY" https://api.taostats.io/api/price/latest/v1?asset=tao
   ```

### Rate Limiting Issues

1. Check rate limit count:
   ```bash
   curl http://localhost:8050/api/v1/trust-pack | jq '.api_health.total_rate_limits'
   ```

2. Reduce sync frequency in settings:
   ```bash
   export POOLS_REFRESH_MINUTES=15  # Was 10
   export WALLET_REFRESH_MINUTES=10  # Was 5
   ```

3. Verify local rate limiting is working:
   - Client-side limit: `taostats_rate_limit_per_minute` (default: 60)

### Stale Data

1. Check when last successful sync occurred:
   ```bash
   curl http://localhost:8050/api/v1/trust-pack | jq '.datasets.subnets.last_success_at'
   ```

2. Trigger manual sync:
   ```bash
   curl -X POST http://localhost:8050/api/v1/tasks/sync
   ```

3. Check for sync errors in logs

### Cache Issues

1. Check cache hit rate:
   ```bash
   curl http://localhost:8050/api/v1/trust-pack | jq '.cache_health'
   ```

2. If hit rate is low, verify Redis is running:
   ```bash
   redis-cli ping
   ```

3. Check cache TTLs are appropriate for your use case

---

## Metrics Reset (Testing)

For testing purposes, you can reset metrics:

```python
import asyncio
from app.core.metrics import get_metrics

async def reset():
    await get_metrics().reset()

asyncio.run(reset())
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      TAO Treasury Backend                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   API Layer  │    │ Data Sync    │    │   Analysis   │      │
│  │  (FastAPI)   │    │  Service     │    │   Services   │      │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘      │
│         │                   │                                    │
│         │    ┌──────────────┴──────────────┐                    │
│         │    │                              │                    │
│         ▼    ▼                              ▼                    │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              TaoStats Client (Hardened)               │      │
│  │  • Retry-After handling                               │      │
│  │  • Exponential backoff + jitter                       │      │
│  │  • Configurable timeouts                              │      │
│  │  • Response validation                                │      │
│  │  • Metrics recording                                  │      │
│  └──────────────────────────┬───────────────────────────┘      │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌────────────┐      ┌────────────┐      ┌────────────┐        │
│  │   Redis    │      │ PostgreSQL │      │  Metrics   │        │
│  │   Cache    │      │     DB     │      │ Collector  │        │
│  └────────────┘      └────────────┘      └─────┬──────┘        │
│                                                 │                │
│                                                 ▼                │
│                                         ┌────────────┐          │
│                                         │ Trust Pack │          │
│                                         │  Endpoint  │          │
│                                         └────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Files Changed in Phase 0 + Phase 1

| File | Change Type | Purpose |
|------|-------------|---------|
| `app/core/metrics.py` | NEW | Centralized metrics collection |
| `app/core/config.py` | MODIFIED | Added feature flags and timeouts |
| `app/core/redis.py` | MODIFIED | Added cache metrics instrumentation |
| `app/services/data/response_models.py` | NEW | Pydantic response validation models |
| `app/services/data/taostats_client.py` | MODIFIED | Retry-After, backoff, validation |
| `app/services/data/data_sync.py` | MODIFIED | Partial failure protection |
| `app/api/v1/health.py` | MODIFIED | Added Trust Pack endpoint |
| `tests/unit/test_phase1_hardening.py` | NEW | Tests for Phase 0+1 features |
