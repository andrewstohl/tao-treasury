# Interactive Backtesting Page - Implementation Plan

**Date:** February 2026
**Location:** New page under "Analyze" tab
**Status:** COMPLETED

---

## Executive Summary

This plan outlines the phased development of an interactive backtesting page that allows users to:
1. Test viability scoring configurations against historical data
2. Compare FAI-weighted vs equal-weight allocation strategies
3. Adjust parameters (weights, thresholds, top N subnets) interactively
4. Run optimization to find best parameter combinations
5. Visualize results with charts and detailed metrics

The existing backtesting code in Settings.tsx will be migrated and significantly enhanced.

---

## Phase 1: Foundation & Migration (3-4 days)

### Objective
Create the new Backtest page structure and migrate existing functionality.

### Tasks

#### 1.1 Create New Page Structure
- **Create** `/frontend/src/pages/Backtest.tsx`
- **Add route** to `App.tsx`: `<Route path="/backtest" element={<Backtest />} />`
- **Add menu item** to Layout.tsx analyzeItems:
  ```typescript
  { path: '/backtest', label: 'Backtest', icon: FlaskConical }
  ```

#### 1.2 Create Component Architecture
```
/frontend/src/components/backtest/
├── BacktestPage.tsx           # Main page container
├── ConfigurationPanel.tsx     # Parameter inputs (left side)
├── ResultsPanel.tsx           # Results display (right side)
├── EquityCurveChart.tsx       # Performance chart
├── MetricsSummary.tsx         # Key metrics cards
├── HoldingsTable.tsx          # Period-by-period holdings
└── index.ts                   # Barrel exports
```

#### 1.3 Migrate Existing Code
- Extract `BacktestSection` from Settings.tsx → `ConfigurationPanel.tsx`
- Extract `PortfolioSimSection` from Settings.tsx → `ResultsPanel.tsx`
- Update Settings.tsx to remove backtesting sections
- Add link in Settings to new Backtest page

#### 1.4 Backend API Validation
Verify existing endpoints work correctly:
- `GET /api/v1/backtest/run` - Run viability backtest
- `GET /api/v1/backtest/simulate` - Run portfolio simulation
- `POST /api/v1/backtest/backfill` - Trigger historical data fetch
- `GET /api/v1/backtest/backfill/status` - Check backfill progress

### Deliverables
- New Backtest page accessible from Analyze menu
- Existing functionality preserved
- Clean Settings page without backtesting sections

---

## Phase 2: Configuration Interface (2-3 days)

### Objective
Build the interactive configuration panel for adjusting all backtest parameters.

### Tasks

#### 2.1 Date Range Selector
```typescript
interface DateConfig {
  startDate: string;        // Default: 2025-11-05 (post-AMM change)
  endDate: string;          // Default: today
  minAllowedDate: string;   // Hard limit: 2025-11-05
}
```
- Date picker with validation (no dates before Nov 5, 2025)
- Quick presets: "Last 30D", "Last 90D", "Since AMM Change"

#### 2.2 Viability Hard Failures Config
```typescript
interface HardFailureConfig {
  minAge: number;           // Default: 60 days
  minReserve: number;       // Default: 500 TAO
  maxOutflow7d: number;     // Default: -50%
  maxDrawdown: number;      // Default: 50%
}
```
- Slider or number inputs for each threshold
- Toggle to enable/disable individual gates

#### 2.3 Viability Scoring Weights
```typescript
interface ScoringWeights {
  faiWeight: number;        // Default: 35%
  reserveWeight: number;    // Default: 25%
  emissionWeight: number;   // Default: 25%
  stabilityWeight: number;  // Default: 15%
}
// Must sum to 100%
```
- Linked sliders (adjusting one affects others)
- Visual weight bar showing proportions
- Lock individual weights toggle

#### 2.4 Strategy Selection
```typescript
interface StrategyConfig {
  type: 'equal_weight' | 'fai_weighted';
  rebalanceFrequency: 1 | 3 | 7;  // days
  topPercentile: number;          // Default: 50 (top 50%)
  maxPositionSize: number;        // Default: 10%
}
```
- Radio buttons for strategy type
- Dropdown for rebalance frequency
- Slider for top percentile (10-100%)

#### 2.5 FAI Configuration (when FAI strategy selected)
```typescript
interface FAIConfig {
  quintileMultipliers: {
    q1: number;  // Default: 0.2
    q2: number;  // Default: 0.5
    q3: number;  // Default: 1.0
    q4: number;  // Default: 1.5
    q5: number;  // Default: 2.5
  };
  useLifecycle: boolean;      // Default: true
  lifecyclePhases: {
    rampUp: [1, 7];           // Days 1-7: building
    peak: [7, 14];            // Days 7-14: max allocation
    rampDown: [14, 21];       // Days 14-21: reducing
    exit: 21;                 // 21+: exit zone
  };
}
```

### UI Design
```
┌─────────────────────────────────────────────────────────────────┐
│ BACKTEST CONFIGURATION                                          │
├─────────────────────────────────────────────────────────────────┤
│ Date Range                                                      │
│ [Nov 5, 2025] ──────────────────────── [Feb 6, 2026]           │
│ Quick: [Last 30D] [Last 90D] [All Data]                         │
├─────────────────────────────────────────────────────────────────┤
│ Viability Hard Failures                                         │
│ ☑ Min Age:        [60] days                                    │
│ ☑ Min Reserve:    [500] TAO                                    │
│ ☑ Max 7D Outflow: [-50]%                                       │
│ ☑ Max Drawdown:   [50]%                                        │
├─────────────────────────────────────────────────────────────────┤
│ Viability Scoring Weights                [Total: 100%]          │
│ FAI:       ████████████░░░░░░░░ 35%      [🔒]                   │
│ Reserve:   ████████░░░░░░░░░░░░ 25%      [🔓]                   │
│ Emission:  ████████░░░░░░░░░░░░ 25%      [🔓]                   │
│ Stability: █████░░░░░░░░░░░░░░░ 15%      [🔓]                   │
├─────────────────────────────────────────────────────────────────┤
│ Strategy                                                        │
│ ○ Equal Weight (Recommended)    ● FAI-Weighted                  │
│                                                                  │
│ Rebalance: [Weekly ▼]   Top Subnets: [50%] ─────────            │
├─────────────────────────────────────────────────────────────────┤
│ FAI Settings (when FAI selected)                                │
│ Quintile Multipliers: Q1[0.2] Q2[0.5] Q3[1.0] Q4[1.5] Q5[2.5]  │
│ ☑ Use Days-in-Signal Lifecycle                                  │
├─────────────────────────────────────────────────────────────────┤
│              [Run Backtest]    [Save Config]                    │
└─────────────────────────────────────────────────────────────────┘
```

### Deliverables
- Fully interactive configuration panel
- Real-time validation (weights sum to 100%, dates valid)
- Saved configurations (localStorage)

---

## Phase 3: Enhanced Results Display (2-3 days)

### Objective
Create comprehensive, visually rich results display.

### Tasks

#### 3.1 Summary Metrics Cards
```typescript
interface BacktestMetrics {
  totalReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  winRate: number;
  avgSubnets: number;
  totalTrades: number;
  bestPeriod: { date: string; return: number };
  worstPeriod: { date: string; return: number };
}
```
- Large metric cards with icons
- Color-coded (green positive, red negative)
- Comparison to baseline if running comparison

#### 3.2 Equity Curve Chart
- Interactive line chart (Recharts)
- Toggle between strategies (if comparing)
- Drawdown overlay option
- Zoom/pan capabilities
- Hover tooltips with period details

#### 3.3 Period-by-Period Table
```typescript
interface PeriodRow {
  date: string;
  portfolioValue: number;
  periodReturn: number;
  cumulativeReturn: number;
  holdings: SubnetHolding[];
  rebalanced: boolean;
}
```
- Expandable rows to show holdings
- Sortable columns
- Export to CSV

#### 3.4 Strategy Comparison View
When comparing FAI vs Equal Weight:
- Side-by-side metrics
- Overlaid equity curves
- Difference chart (FAI return - EW return)
- Statistical significance indicator

### UI Design
```
┌─────────────────────────────────────────────────────────────────┐
│ BACKTEST RESULTS                          [Export CSV] [Share]  │
├─────────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ │ +32.5%   │ │  7.78    │ │  -1.3%   │ │  62.1%   │ │   52     │
│ │ Return   │ │ Sharpe   │ │ Max DD   │ │ Win Rate │ │ Subnets  │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
├─────────────────────────────────────────────────────────────────┤
│ Equity Curve                              [1M] [3M] [All] [DD]  │
│ ┌───────────────────────────────────────────────────────────────┐
│ │                                               _____──────────│
│ │                               _____──────────/                │
│ │               _____──────────/                                │
│ │ ─────────────/                                                │
│ │ $100                                                     $132 │
│ └───────────────────────────────────────────────────────────────┘
│  Nov 5          Dec 1          Jan 1          Feb 1       Feb 6 │
├─────────────────────────────────────────────────────────────────┤
│ Period Details                         [Expand All] [Filter ▼]  │
│ ┌─────────┬──────────┬──────────┬──────────────┬───────────────┐
│ │ Date    │ Value    │ Return   │ Cum. Return  │ Holdings      │
│ ├─────────┼──────────┼──────────┼──────────────┼───────────────┤
│ │ Feb 6   │ $132.50  │ +1.2%    │ +32.5%       │ [▼ 52 subnets]│
│ │ Jan 30  │ $130.94  │ +0.8%    │ +30.9%       │ [▼ 51 subnets]│
│ │ ...     │ ...      │ ...      │ ...          │ ...           │
│ └─────────┴──────────┴──────────┴──────────────┴───────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### Deliverables
- Rich results visualization
- Interactive charts
- Detailed period data with expandable holdings
- Export functionality

---

## Phase 4: Backend Enhancements (3-4 days)

### Objective
Extend backend to support new configuration options and optimization.

### Tasks

#### 4.1 Enhanced Backtest Endpoint
Update `/api/v1/backtest/simulate` to accept full configuration:

```python
@router.post("/api/v1/backtest/simulate-v2")
async def simulate_portfolio_v2(config: BacktestConfigV2):
    """
    Enhanced portfolio simulation with full configuration.
    """
    pass

class BacktestConfigV2(BaseModel):
    # Date range
    start_date: date
    end_date: date = date.today()

    # Hard failures
    min_age_days: int = 60
    min_reserve_tao: float = 500
    max_outflow_7d_pct: float = -50
    max_drawdown_pct: float = 50

    # Scoring weights
    fai_weight: float = 0.35
    reserve_weight: float = 0.25
    emission_weight: float = 0.25
    stability_weight: float = 0.15

    # Strategy
    strategy: Literal["equal_weight", "fai_weighted"] = "equal_weight"
    rebalance_days: int = 7
    top_percentile: float = 50
    max_position_pct: float = 10

    # FAI config (if strategy == "fai_weighted")
    quintile_multipliers: Dict[str, float] = None
    use_lifecycle: bool = True
```

#### 4.2 Proper Age Calculation
**CRITICAL:** Use registration_date from subnet metadata:

```python
async def fetch_subnet_registration_dates() -> Dict[int, date]:
    """Fetch actual subnet registration dates from TaoStats API."""
    result = await taostats_request("/subnet/latest/v1", {"limit": 200})
    metadata = {}
    for s in result["data"]:
        netuid = s.get("netuid")
        reg_ts = s.get("registration_timestamp", "")
        if reg_ts:
            reg_date = datetime.fromisoformat(reg_ts.replace("Z", "+00:00")).date()
            metadata[netuid] = reg_date
    return metadata

def compute_subnet_age(registration_date: date, target_date: date) -> int:
    """Compute age in days from actual registration date."""
    if not registration_date:
        return 0
    return (target_date - registration_date).days
```

#### 4.3 Comparison Mode
Support running both strategies in one request:

```python
@router.post("/api/v1/backtest/compare")
async def compare_strategies(config: CompareConfigV2):
    """
    Run both equal weight and FAI-weighted, return comparison.
    """
    equal_result = await run_backtest(config, strategy="equal_weight")
    fai_result = await run_backtest(config, strategy="fai_weighted")

    return {
        "equal_weight": equal_result,
        "fai_weighted": fai_result,
        "comparison": {
            "return_difference": fai_result.total_return - equal_result.total_return,
            "sharpe_difference": fai_result.sharpe - equal_result.sharpe,
            "winner": "equal_weight" if equal_result.sharpe > fai_result.sharpe else "fai_weighted"
        }
    }
```

#### 4.4 Add TypeScript Types
Update `/frontend/src/types/index.ts`:

```typescript
export interface BacktestConfigV2 {
  startDate: string;
  endDate: string;
  minAgeDays: number;
  minReserveTao: number;
  maxOutflow7dPct: number;
  maxDrawdownPct: number;
  faiWeight: number;
  reserveWeight: number;
  emissionWeight: number;
  stabilityWeight: number;
  strategy: 'equal_weight' | 'fai_weighted';
  rebalanceDays: number;
  topPercentile: number;
  maxPositionPct: number;
  quintileMultipliers?: Record<string, number>;
  useLifecycle?: boolean;
}

export interface BacktestResultV2 {
  config: BacktestConfigV2;
  metrics: {
    totalReturn: number;
    sharpeRatio: number;
    maxDrawdown: number;
    winRate: number;
    avgSubnets: number;
    totalPeriods: number;
  };
  equityCurve: Array<{
    date: string;
    value: number;
    periodReturn: number;
    cumulativeReturn: number;
  }>;
  periods: Array<{
    date: string;
    value: number;
    holdings: Array<{
      netuid: number;
      name: string;
      weight: number;
      return: number;
    }>;
  }>;
}
```

### Deliverables
- New v2 API endpoints with full configuration
- Proper age calculation using registration dates
- Strategy comparison endpoint
- Updated TypeScript types

---

## Phase 5: Optimization Mode (3-4 days)

### Objective
Allow users to run parameter sweeps to find optimal configurations.

### Tasks

#### 5.1 Optimization Configuration UI
```typescript
interface OptimizationConfig {
  // Which parameters to optimize
  optimizeWeights: boolean;
  optimizeThresholds: boolean;
  optimizeMultipliers: boolean;

  // Ranges for each parameter
  faiWeightRange: [number, number, number];  // [min, max, step]
  reserveWeightRange: [number, number, number];
  minAgeRange: [number, number, number];
  // ... etc

  // Optimization target
  optimizeFor: 'sharpe' | 'return' | 'drawdown' | 'win_rate';

  // Constraints
  maxIterations: number;
  constraintWeightsSum100: boolean;
}
```

#### 5.2 Backend Grid Search
```python
@router.post("/api/v1/backtest/optimize")
async def optimize_parameters(config: OptimizationConfig):
    """
    Run grid search over parameter space.
    Returns top N configurations.
    """
    results = []

    # Generate parameter combinations
    for fai_w in np.arange(config.fai_weight_min, config.fai_weight_max, config.fai_weight_step):
        for reserve_w in np.arange(...):
            # ... nested loops for each parameter

            if fai_w + reserve_w + emission_w + stability_w != 1.0:
                continue  # Skip invalid combinations

            result = await run_backtest(...)
            results.append({
                "config": {...},
                "metrics": result.metrics
            })

    # Sort by optimization target
    results.sort(key=lambda x: x["metrics"][config.optimize_for], reverse=True)

    return {
        "total_combinations_tested": len(results),
        "top_configurations": results[:10],
        "optimization_target": config.optimize_for
    }
```

#### 5.3 Progress Tracking
- WebSocket or polling for long-running optimizations
- Progress bar showing combinations tested
- Early stopping if user cancels

#### 5.4 Results Visualization
- Heatmap showing parameter sensitivity
- Table of top 10 configurations
- One-click apply best configuration

### UI Design
```
┌─────────────────────────────────────────────────────────────────┐
│ OPTIMIZATION MODE                                               │
├─────────────────────────────────────────────────────────────────┤
│ Select Parameters to Optimize:                                  │
│ ☑ Viability Weights    ☐ Hard Failure Thresholds               │
│ ☐ FAI Multipliers      ☐ Rebalance Frequency                   │
├─────────────────────────────────────────────────────────────────┤
│ Parameter Ranges:                                               │
│ FAI Weight:     [20%] ─────────────── [50%]   Step: [5%]       │
│ Reserve Weight: [15%] ─────────────── [35%]   Step: [5%]       │
│ Min Age:        [30d] ─────────────── [90d]   Step: [15d]      │
├─────────────────────────────────────────────────────────────────┤
│ Optimize For: ◉ Sharpe Ratio  ○ Total Return  ○ Min Drawdown   │
├─────────────────────────────────────────────────────────────────┤
│             [Run Optimization]   Est. combinations: 648         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ OPTIMIZATION RESULTS                                            │
├─────────────────────────────────────────────────────────────────┤
│ ████████████████████████░░░░░░  78% Complete (506/648)         │
├─────────────────────────────────────────────────────────────────┤
│ Top Configurations by Sharpe Ratio:                             │
│ ┌────┬──────────────────────────────────────┬────────┬─────────┐
│ │ #  │ Configuration                        │ Sharpe │ Return  │
│ ├────┼──────────────────────────────────────┼────────┼─────────┤
│ │ 1  │ FAI:30 RSV:30 EM:25 ST:15, Age:60   │ 8.12   │ +34.2%  │
│ │ 2  │ FAI:25 RSV:25 EM:30 ST:20, Age:75   │ 7.95   │ +31.8%  │
│ │ 3  │ FAI:35 RSV:25 EM:25 ST:15, Age:60   │ 7.78   │ +32.5%  │
│ └────┴──────────────────────────────────────┴────────┴─────────┘
│                                           [Apply #1] [Details]  │
└─────────────────────────────────────────────────────────────────┘
```

### Deliverables
- Optimization configuration UI
- Backend grid search with progress tracking
- Results visualization with apply functionality

---

## Phase 6: Polish & Documentation (2 days)

### Objective
Final polish, testing, and documentation.

### Tasks

#### 6.1 UI Polish
- Loading states and animations
- Error handling and user feedback
- Responsive design for smaller screens
- Keyboard shortcuts (Ctrl+Enter to run)

#### 6.2 Help & Documentation
- Inline tooltips explaining each parameter
- "What is Sharpe Ratio?" info modals
- Link to FLOW_MOMENTUM_RESEARCH.md findings

#### 6.3 Preset Configurations
- "Research Optimal" (settings from validated backtest)
- "Conservative" (equal weight, weekly rebalance)
- "Aggressive" (FAI-weighted, daily rebalance)
- "Custom" (full configuration)

#### 6.4 Testing
- Unit tests for calculation functions
- Integration tests for API endpoints
- E2E tests for critical user flows

### Deliverables
- Polished, production-ready UI
- Comprehensive documentation
- Preset configurations
- Test coverage

---

## Timeline Summary

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Foundation | 3-4 days | None |
| Phase 2: Configuration UI | 2-3 days | Phase 1 |
| Phase 3: Results Display | 2-3 days | Phase 1 |
| Phase 4: Backend Enhancements | 3-4 days | Phase 1 |
| Phase 5: Optimization Mode | 3-4 days | Phases 2-4 |
| Phase 6: Polish | 2 days | All phases |

**Total Estimated Time:** 15-20 days

**Note:** Phases 2, 3, and 4 can run in parallel after Phase 1 is complete.

---

## Technical Considerations

### Critical Implementation Details

1. **Age Calculation:** MUST use `/subnet/latest/v1` for registration dates
2. **Date Validation:** No dates before November 5, 2025 (AMM change)
3. **Weight Normalization:** Viability weights must sum to 100%
4. **API Rate Limits:** Implement caching for TaoStats API calls
5. **Large Datasets:** Use pagination for period details table

### Performance Optimizations

1. **Memoization:** Cache calculation results for unchanged parameters
2. **Web Workers:** Run heavy calculations off main thread
3. **Virtual Scrolling:** For large period tables (react-window)
4. **Debouncing:** Debounce parameter changes before API calls

### State Management

```typescript
// Zustand or React Context for backtest state
interface BacktestState {
  config: BacktestConfigV2;
  results: BacktestResultV2 | null;
  isRunning: boolean;
  progress: number;
  error: string | null;

  setConfig: (config: Partial<BacktestConfigV2>) => void;
  runBacktest: () => Promise<void>;
  resetResults: () => void;
}
```

---

## File Changes Summary

### New Files
- `/frontend/src/pages/Backtest.tsx`
- `/frontend/src/components/backtest/ConfigurationPanel.tsx`
- `/frontend/src/components/backtest/ResultsPanel.tsx`
- `/frontend/src/components/backtest/EquityCurveChart.tsx`
- `/frontend/src/components/backtest/MetricsSummary.tsx`
- `/frontend/src/components/backtest/HoldingsTable.tsx`
- `/frontend/src/components/backtest/OptimizationPanel.tsx`
- `/frontend/src/components/backtest/index.ts`
- `/backend/app/routers/backtest_v2.py`

### Modified Files
- `/frontend/src/App.tsx` - Add route
- `/frontend/src/components/common/Layout.tsx` - Add menu item
- `/frontend/src/pages/Settings.tsx` - Remove backtesting sections
- `/frontend/src/services/api.ts` - Add new endpoints
- `/frontend/src/types/index.ts` - Add new types
- `/backend/app/main.py` - Include new router

---

## Implementation Checklist (COMPLETED)

All phases have been implemented:

- [x] Phase 1: Foundation - Page structure, routes, menu items
- [x] Phase 2: Configuration UI - Full parameter configuration with presets
- [x] Phase 3: Results Display - Metrics summary, equity curve, period details
- [x] Phase 4: Backend Enhancements - New `/simulate-v2` endpoint with full viability config
- [x] Phase 5: Optimization Mode - Grid search with progress tracking
- [x] Phase 6: Polish - Tooltips, help text, collapsible sections

---

## Completion Summary

**Date Completed:** February 2026

### Key Files Created/Modified:

#### Frontend
- `/frontend/src/pages/Backtest.tsx` - Main backtest page
- `/frontend/src/components/backtest/ConfigurationPanel.tsx` - Full configuration UI
- `/frontend/src/components/backtest/ResultsPanel.tsx` - Results visualization
- `/frontend/src/components/backtest/EquityCurveChart.tsx` - Interactive equity chart
- `/frontend/src/components/backtest/MetricsSummary.tsx` - Metrics cards with tooltips
- `/frontend/src/components/backtest/OptimizationPanel.tsx` - Grid search optimization
- `/frontend/src/components/backtest/Tooltip.tsx` - Help tooltips component
- `/frontend/src/services/api.ts` - Added `simulatePortfolioV2()` method

#### Backend
- `/backend/app/api/v1/backtest.py` - Added `/simulate-v2` endpoint
- `/backend/app/services/backtest/backtest_engine.py` - Added `simulate_portfolio_v2()` method

### Critical Fix Applied:
The original backtest was hardcoded to use tier-based filtering (`'tier_1'`). This was replaced with proper viability-based filtering that:
1. Applies hard failure thresholds (age, reserve, outflow, drawdown)
2. Scores using 4-factor viability (FAI 35%, Reserve 25%, Emission 25%, Stability 15%)
3. Selects top N% by viability score (NOT by tier)
4. Supports equal weight or FAI-weighted allocation

---

*Plan created February 2026 for TAO Treasury backtesting enhancement*
*Implementation completed February 2026*
