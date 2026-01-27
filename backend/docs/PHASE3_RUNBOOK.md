# Phase 3: Decision Support Pack - Runbook

## Overview

Phase 3 implements the Decision Support Pack - a framework for actionable, explainable, and safe trading signals. These signals provide recommendations for portfolio management without automatic execution.

## Key Principles

1. **Recommendations only** - No automatic trade execution
2. **Explainability** - Every signal includes evidence and reasoning
3. **Safety first** - Guardrails prevent high-confidence recommendations when data quality is poor
4. **Trust gating** - Data quality issues block high-confidence outputs

## Signals Implemented

### 1. Data Trust Gate Signal
**ID:** `data_trust_gate`

The most critical signal - it gates all other signals. If data is stale or has drift, it blocks high-confidence recommendations from other signals.

**Checks:**
- Data staleness (via `data_sync_service.is_data_stale()`)
- Reconciliation drift (via reconciliation service)
- Sync metrics for failures

**Status Outcomes:**
- `OK` - All data trust checks passed
- `DEGRADED` - Some concerns but not critical
- `BLOCKED` - Data issues prevent reliable recommendations

### 2. Earnings Leaderboard Signal
**ID:** `earnings_leaderboard`

Uses the earnings identity to rank subnets by performance:

```
earnings = end_value - start_value - net_flows
```

**Outputs:**
- Top performers (7d and 30d windows)
- Under performers
- Consistent underperformers (in both windows)

**Guardrails:**
- `negative_earnings_detected` - Losses in period
- `consistent_underperformers` - Same subnets underperforming in both windows

### 3. Slippage Capacity Signal
**ID:** `slippage_capacity`

Analyzes slippage capacity for each subnet to determine max safe trade sizes.

**Outputs:**
- Max safe stake size per netuid
- Max safe unstake size per netuid
- Current position exit slippage
- Low capacity warnings

**Guardrails:**
- `low_capacity_detected` - Subnet has <5 TAO safe capacity
- `high_exit_slippage` - Current position would incur high slippage to exit
- `slippage_data_stale` - Slippage surfaces are outdated

### 4. Concentration Risk Signal
**ID:** `concentration_risk`

Detects portfolio concentration exceeding thresholds.

**Thresholds:**
- Single position: 25% max (warning at 20%)
- Top 3 positions: 60% max
- HHI: 2500 high, 1500 moderate

**Outputs:**
- Concentration analysis with HHI
- Position churn metrics (7d/30d)
- Diversification recommendations

**Guardrails:**
- `concentration_critical` - Single position exceeds 25%
- `concentration_warning` - Single position exceeds 20%
- `hhi_high` - Portfolio highly concentrated
- `high_churn` - High position turnover

## API Endpoints

### GET /api/v1/signals/catalog
Returns definitions for all registered signals.

### POST /api/v1/signals/run
Run signals on-demand. Optional `signal_id` query param to run single signal.

### POST /api/v1/signals/run-and-store
Run all signals and persist results to database. Returns `run_id`.

### GET /api/v1/signals/latest
Get most recent stored signal run.

### GET /api/v1/signals/history/{signal_id}
Get historical runs for a specific signal. Optional `days` param (default 7).

### GET /api/v1/signals/{signal_id}
Get definition for a specific signal.

## Configuration

```env
# Phase 3: Decision Support Signals
ENABLE_SIGNAL_ENDPOINTS=true
SLIPPAGE_THRESHOLD_PCT=1.0
SLIPPAGE_STALE_MINUTES=10
```

## Signal Output Schema

All signals return outputs conforming to:

```python
{
    "status": "ok" | "degraded" | "blocked",
    "summary": "Human-readable summary",
    "recommended_action": "What to do",
    "evidence": { ... },  # Supporting data
    "guardrails_triggered": ["guardrail_id", ...],
    "confidence": "high" | "medium" | "low",
    "confidence_reason": "Why this confidence level"
}
```

## Database

Signal runs are stored in `signal_runs` table:

| Column | Type | Description |
|--------|------|-------------|
| id | BIGINT | Primary key |
| run_id | VARCHAR(64) | Batch run identifier |
| created_at | TIMESTAMP | Run timestamp |
| signal_id | VARCHAR(64) | Signal identifier |
| signal_name | VARCHAR(128) | Human-readable name |
| status | VARCHAR(32) | ok/degraded/blocked |
| confidence | VARCHAR(32) | high/medium/low |
| confidence_reason | TEXT | Explanation |
| summary | TEXT | Human-readable summary |
| recommended_action | TEXT | What to do |
| evidence | JSONB | Supporting data |
| guardrails_triggered | JSONB | List of triggered guardrails |
| full_output | JSONB | Complete output payload |
| inputs_hash | VARCHAR(64) | Optional input versioning |
| error_message | TEXT | Error if failed |

## Running Migrations

```bash
cd backend
alembic upgrade head
```

## Testing

```bash
cd backend
pytest tests/unit/test_phase3_signals.py -v
```

## Integration with Trust Pack

The Data Trust Gate signal integrates with Trust Pack to verify:
1. Data freshness from sync service
2. Reconciliation drift status
3. Sync metrics for failures

If Trust Pack shows issues, the trust gate will be DEGRADED or BLOCKED, which cascades to lower confidence on all other signals.

## Devil's Advocate Guardrails

The guardrail system implements "Devil's Advocate" rules:

1. **Block on staleness** - Stale data prevents high confidence
2. **Block on drift** - Reconciliation drift prevents high confidence
3. **Block on missing inputs** - Required data must be present
4. **Validate sample size** - Insufficient data reduces confidence
5. **Check slippage capacity** - Large trades in illiquid markets are flagged
6. **Check concentration** - Over-concentration is flagged

## Extending with New Signals

To add a new signal:

1. Create implementation in `app/services/signals/implementations/`
2. Extend `BaseSignal` class
3. Implement `get_definition()` and `run()` methods
4. Register in `_register_all_signals()` in `registry.py`
5. Add tests in `tests/unit/test_phase3_signals.py`

Example:

```python
from app.services.signals.base import (
    BaseSignal,
    SignalDefinition,
    SignalOutput,
    SignalStatus,
    SignalConfidence,
)

class MyNewSignal(BaseSignal):
    def get_definition(self) -> SignalDefinition:
        return SignalDefinition(
            id="my_new_signal",
            name="My New Signal",
            description="What it does",
            actionability="How to use it",
            actionability_score=5,
            edge_hypothesis="Why it works",
            correctness_risks=["Risk 1", "Risk 2"],
            required_datasets=["dataset1"],
            ongoing_cost="Low",
            latency_sensitivity="Medium",
            failure_behavior="Falls back to LOW confidence",
        )

    async def run(self) -> SignalOutput:
        # Implementation
        return SignalOutput(
            status=SignalStatus.OK,
            summary="Analysis complete",
            recommended_action="Take action X",
            evidence={"metric": 123},
            guardrails_triggered=[],
            confidence=SignalConfidence.HIGH,
            confidence_reason="All checks passed",
        )
```

## Hard Constraints

1. **No auto-execution** - Signals only recommend, never execute
2. **No entertainment features** - No Fear & Greed, no generic charts
3. **Proper failure handling** - Stale/drift data = LOW confidence
4. **Trust gating** - Data Trust Gate runs first and gates others
