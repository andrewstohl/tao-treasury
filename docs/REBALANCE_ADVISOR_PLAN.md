# Rebalance Advisor Page - Implementation Plan

**Date:** February 2026
**Location:** Replaces existing "Rebalance" page under Analyze tab
**Status:** IN PROGRESS

---

## Executive Summary

Build a Rebalance Advisor page that:
1. Compares current portfolio to optimal target portfolio
2. Calculates required trades with exact TAO amounts
3. Provides sensitivity analysis (current vs target performance)
4. Tracks rebalance history (60 days)

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Settings Storage | localStorage (for now) |
| Rebalance Schedule | Every 3 days |
| Threshold | Both individual position (3%) AND total portfolio drift (5%) |
| Execution | Manual only (no auto-execute) |
| History Depth | 60 days |
| Capital Mode | Redeploy existing only |

---

## Implementation Phases

### Phase 1: Settings Upgrade
Add rebalance configuration section to Settings page:
- Rebalance schedule (3/7/14 days)
- Position threshold (min delta % to trigger trade)
- Portfolio threshold (min total drift % to trigger rebalance)
- Strategy (equal_weight / fai_weighted)
- Top percentile
- Viability weights (link to existing)

**Files to modify:**
- `/frontend/src/pages/Settings.tsx` - Add rebalance config section
- `/frontend/src/services/settingsStore.ts` - NEW: localStorage persistence

### Phase 2: Rebalance Core
Replace Recommendations page with new 3-column layout:
- Current portfolio (from dashboard API)
- Target portfolio (computed using viability scoring)
- Required trades (deltas with TAO amounts)

**Files to modify:**
- `/frontend/src/pages/Recommendations.tsx` - Complete rewrite → `Rebalance.tsx`
- `/frontend/src/components/rebalance/` - NEW: Component directory
  - `PortfolioComparison.tsx` - Top summary stats
  - `CurrentPortfolio.tsx` - Left column
  - `TargetPortfolio.tsx` - Center column
  - `TradeList.tsx` - Right column
- `/backend/app/api/v1/rebalance.py` - NEW: Rebalance endpoints
- `/backend/app/services/rebalance_engine.py` - NEW: Compute target + trades

### Phase 3: Sensitivity + History
Add projection/comparison and historical tracking:
- Projected performance comparison (current path vs rebalanced)
- Rebalance history log (stored in localStorage, 60 days)

**Files to modify:**
- `/frontend/src/components/rebalance/SensitivityAnalysis.tsx` - NEW
- `/frontend/src/components/rebalance/RebalanceHistory.tsx` - NEW
- `/frontend/src/services/rebalanceHistory.ts` - NEW: History storage

---

## Phase 1 Details: Settings Upgrade

### Rebalance Config Schema (localStorage)

```typescript
interface RebalanceConfig {
  // Schedule
  rebalanceIntervalDays: number  // 3, 7, or 14
  lastRebalanceDate: string | null  // ISO date

  // Thresholds
  positionThresholdPct: number  // e.g., 3 = don't trade if delta < 3%
  portfolioThresholdPct: number  // e.g., 5 = don't rebalance if total drift < 5%

  // Strategy (mirrors backtest config)
  strategy: 'equal_weight' | 'fai_weighted'
  topPercentile: number  // 30-70
  maxPositionPct: number  // 10-25

  // Viability (these link to backend config OR can be overridden)
  useBackendViabilityConfig: boolean  // true = use Settings page values
  // If false, use these:
  minAgeDays: number
  minReserveTao: number
  maxOutflow7dPct: number
  maxDrawdownPct: number
  faiWeight: number
  reserveWeight: number
  emissionWeight: number
  stabilityWeight: number
}
```

### Settings Page UI Addition

Add a new collapsible section below the existing viability config:

```
┌─ REBALANCE SETTINGS ───────────────────────────────────────────────────────┐
│                                                                            │
│  Schedule                                                                  │
│  ○ Every 3 days (Recommended)    ○ Every 7 days    ○ Every 14 days        │
│                                                                            │
│  Thresholds                                                                │
│  Position:  [====|====] 3%    Don't trade if position delta < 3%          │
│  Portfolio: [====|====] 5%    Don't rebalance if total drift < 5%         │
│                                                                            │
│  Allocation Strategy                                                       │
│  ○ Equal Weight (Recommended)    ○ FAI-Weighted                           │
│                                                                            │
│  Selection                                                                 │
│  Top Percentile: [====|====] 50%    Max Position: [====|====] 12.5%       │
│                                                                            │
│  Viability Config                                                          │
│  ☑ Use viability settings from above                                      │
│    (Inherits hard failure thresholds and scoring weights)                 │
│                                                                            │
│  [Save Rebalance Settings]                                                 │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 2 Details: Rebalance Core

### Backend Endpoint

```
GET /api/v1/rebalance/compute-target
```

Request query params:
- Uses config from frontend (or defaults)

Response:
```json
{
  "current_portfolio": {
    "total_value_tao": 1247.3,
    "positions": [
      { "netuid": 19, "name": "τao.bot", "value_tao": 227.0, "weight_pct": 18.2, "viability_score": 71, "is_viable": true },
      ...
    ]
  },
  "target_portfolio": {
    "total_value_tao": 1247.3,
    "positions": [
      { "netuid": 19, "name": "τao.bot", "target_weight_pct": 12.5, "viability_score": 71 },
      ...
    ]
  },
  "trades": [
    { "netuid": 52, "name": "Dojo", "action": "SELL_ALL", "amount_tao": 88.6, "reason": "Failed viability" },
    { "netuid": 19, "name": "τao.bot", "action": "REDUCE", "amount_tao": 71.1, "from_pct": 18.2, "to_pct": 12.5 },
    { "netuid": 42, "name": "Masa", "action": "BUY", "amount_tao": 156.0, "from_pct": 0, "to_pct": 12.5 },
    ...
  ],
  "summary": {
    "total_sells_tao": 275.7,
    "total_buys_tao": 275.7,
    "net_tao": 0.0,
    "num_trades": 8,
    "positions_exited": 2,
    "positions_entered": 2,
    "rebalance_needed": true,
    "reason": "2 positions failed viability, total drift 14.2%"
  },
  "comparison": {
    "current_avg_score": 54.9,
    "target_avg_score": 65.3,
    "current_max_weight": 22.1,
    "target_max_weight": 12.5,
    "failed_positions_current": 2,
    "failed_positions_target": 0
  }
}
```

### Frontend 3-Column Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  REBALANCE ADVISOR                             [Refresh]  [Settings ⚙]    │
│  Schedule: Every 3 days    Next: Feb 8 (2 days)    Threshold: 3%/5%       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─ COMPARISON SUMMARY ───────────────────────────────────────────────┐   │
│  │  Metric          Current    Target     Improvement                  │   │
│  │  Avg Score       54.9       65.3       +10.4                       │   │
│  │  Failed Pos.     2          0          Eliminated                   │   │
│  │  Concentration   22.1%      12.5%      More diversified            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─ CURRENT ──────────┐  ┌─ TARGET ───────────┐  ┌─ TRADES ───────────┐  │
│  │ SN19 τao.bot 18.2% │  │ SN19 τao.bot 12.5% │  │ SELLS              │  │
│  │ Score: 71  ✓       │  │ Score: 71  ✓       │  │ SN52 SELL ALL 88τ  │  │
│  │                    │  │                    │  │ SN3  SELL ALL 83τ  │  │
│  │ SN52 Dojo   7.1%   │  │ SN42 Masa    12.5% │  │ SN19 REDUCE 71τ    │  │
│  │ Score: 31  ✕       │  │ Score: 78  ★ NEW   │  │                    │  │
│  │ 7d outflow: -62%   │  │                    │  │ BUYS               │  │
│  │                    │  │                    │  │ SN42 BUY 156τ      │  │
│  │ Total: 1247.3 TAO  │  │ Total: 1247.3 TAO  │  │ SN21 BUY 156τ      │  │
│  └────────────────────┘  └────────────────────┘  │                    │  │
│                                                  │ Net: 0.0 TAO       │  │
│                                                  │ [Copy] [Execute]   │  │
│                                                  └────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 3 Details: Sensitivity + History

### Sensitivity Analysis

Show projected performance if user rebalances vs stays put:
- Use recent backtest data to estimate forward performance
- Compare current holdings' historical returns vs target holdings

### Rebalance History (localStorage)

```typescript
interface RebalanceRecord {
  id: string  // UUID
  date: string  // ISO date
  trades: Trade[]
  portfolioValueBefore: number
  portfolioValueAfter: number
  targetScoreAvg: number
  actualReturn7d?: number  // Filled in later
  completed: boolean
}
```

---

## Files to Create/Modify

### Frontend
- `/frontend/src/services/settingsStore.ts` - NEW: localStorage for rebalance config
- `/frontend/src/services/rebalanceHistory.ts` - NEW: History storage
- `/frontend/src/pages/Settings.tsx` - ADD: Rebalance config section
- `/frontend/src/pages/Rebalance.tsx` - REPLACE: Recommendations.tsx
- `/frontend/src/components/rebalance/` - NEW: Component directory

### Backend
- `/backend/app/api/v1/rebalance.py` - NEW: Rebalance router
- `/backend/app/services/rebalance_engine.py` - NEW: Compute target + trades
- `/backend/app/main.py` - ADD: Include rebalance router

---

## Implementation Order

1. **Phase 1A**: Create `settingsStore.ts` for localStorage
2. **Phase 1B**: Add rebalance config section to Settings page
3. **Phase 2A**: Create backend `/api/v1/rebalance/compute-target` endpoint
4. **Phase 2B**: Create Rebalance page with 3-column layout
5. **Phase 3A**: Add sensitivity analysis component
6. **Phase 3B**: Add rebalance history tracking

---

*Plan created February 2026 for TAO Treasury rebalance advisor*
