# TAO Treasury Management App
## Comprehensive Spec Sheet v1.0
**Date:** Jan 24, 2026

---

## Project Purpose

Build a local first web app that manages a TAO treasury wallet across Root and dTAO subnets. The app must maximize long term TAO accumulation while keeping drawdown limited, measured in TAO using executable prices net of slippage and fees. The app does not execute trades. It produces recommendations and risk alerts.

---

## Core Outcomes

- Track wallet positions, history, and returns in TAO.
- Compute two NAVs. Mid NAV for diagnostics. Executable NAV for risk and decisions.
- Detect taoflow regime shifts and liquidity cliffs early.
- Recommend buys, trims, exits, and rebalances that respect liquidity, turnover, and concentration limits.
- Provide a backtest simulator that validates feasibility and outputs APY vs drawdown tradeoffs.

---

## Non Goals

- No wallet signing, auto execution, or custody.
- No multi user SaaS. Local only for v1.
- No complex ML models in v1. Rules first.

---

## Definitions and Constraints

- **Principal unit:** TAO. USD is informational only.
- **Portfolio risk basis:** executable NAV.
- **Soft portfolio drawdown limit:** 15% peak to trough on executable NAV.
- **Hard portfolio drawdown limit:** 20% peak to trough triggers forced risk off recommendations.
- **Trading constraints for recommendations:** max 2 trades per day by default. Allow 3 only in emergency mode. Also enforce turnover caps (daily and weekly).
- **Position sizing:** constrained by exitability first, then by portfolio concentration caps.

---

## High Level Strategy Design

### Portfolio Structure

- **Barbell.** Root ballast plus dTAO yield sleeve plus unstaked buffer.
- **Default target ranges:**
  - Root: 55% to 75%
  - dTAO sleeve: 20% to 40%
  - Unstaked TAO: 5% to 10%
- Sleeve must hold 8 to 15 positions, subject to eligibility and liquidity.

### Taoflow Regime Model

- Treat taoflow as a gate and a state machine, not a soft factor.
- Use multi horizon flow signals: 1d, 3d, 7d, 14d.
- Require persistence to avoid whipsaws.
- **Regimes:** Risk On, Neutral, Risk Off. Plus Quarantine and Dead for per subnet states.

**Policy by Regime:**

| Regime | Policy |
|--------|--------|
| Risk On | New buys allowed if eligibility passes. Sleeve can expand to upper bound. |
| Neutral | Higher bar for new buys. Prefer adds to existing winners. |
| Risk Off | No new buys. Sleeve shrinks toward lower bound. Prefer Root. |
| Quarantine (subnet) | No adds. Trim 25% to 50% and monitor 48 to 72h. |
| Dead (subnet) | Mandatory exit ladder accelerated, even if it crystallizes a larger loss. |

---

## Eligibility Gate: Investable Universe Rules

**Hard excludes for a subnet:**

- Emission share is zero or near zero.
- Sustained negative taoflow. Example: 7d flow negative and 14d flow negative, or 3 of last 4 days negative.
- Liquidity too low for target size based on slippage surfaces.
- Holder count below minimum.
- Too new below minimum age.
- Owner take above maximum.
- Validator quality fails (vtrust floor, take cap).
- Exit slippage exceeds caps for the candidate position size.

---

## Execution and Pricing Model

- **Mid price:** Spot pool rate. Used for charts and diagnostics only.
- **Executable price:** Based on expected output from the slippage endpoint for defined trade sizes.
- Maintain slippage surfaces per subnet for stake and unstake at sizes: 2, 5, 10, 15 TAO, and optionally 20 TAO.

**For each position, compute:**
- Executable value for 50% unwind.
- Executable value for 100% unwind.
- Risk NAV uses 100% unwind. Primary NAV uses 50% unwind. Both are shown.

---

## Return Decomposition

Compute realized TAO return net of costs. Attribute returns into:
- Emissions component
- Rate change component
- Fees
- Slippage

This must work per position and at portfolio level.

---

## Position Sizing Rules

1. **First cap:** Max position size so 50% exit slippage is below X% and 100% exit slippage is below Y%. Defaults: 5% for 50% exit, 10% for full exit.
2. **Second cap:** Portfolio concentration. Default 10% to 12% per subnet, never above 15%.
3. **Third cap:** Category cap. Default max 30% of sleeve per category, and max 35% of total portfolio per category if you prefer portfolio based.
4. **Minimum position size:** Skip positions that are too small to matter after fees and slippage.

---

## Rebalancing and Churn Control

- **Scheduled rebalance:** weekly.
- **Event driven checks:** daily for hard triggers.

**Trade limits:**
- Default 2 trades per day.
- Daily turnover cap: Default 10% of portfolio.
- Weekly turnover cap: Default 40% of portfolio.

**Exit ladder:**
- **Standard:** Exit in tranches (example 25% per step), reassess slippage between steps.
- **Emergency:** If Dead state, accelerate exits within turnover caps, or relax caps if hard drawdown is threatened.

---

## Optional Hedging Module (v1.5 or v2)

- Conditional TAO perps hedge as a shock absorber in Risk Off only.
- Low leverage. Isolated margin. Hedge sizing tied to regime plus drawdown plus flow breadth.
- Not required for v1.

---

## Data Sources and Ingestion

### Primary Source: TaoStats API

**Auth:** Authorization header. API key loaded from local .env, never stored in DB, never committed.

**Required data pulls:**
- Wallet stake balances: latest and history
- Subnet list: latest
- Subnet pools: latest and history
- Subnet taoflow history
- Subnet emission: latest and history if available
- Validator metrics and yield history for validators you use
- Slippage estimates: on demand and as a cached surface for standard sizes

**Refresh cadence:**
| Data | Interval |
|------|----------|
| Wallet balances | Every 5 minutes |
| Pools and rates | Every 10 to 15 minutes |
| Flow | Every 30 minutes |
| Validator metrics | Every 60 minutes |
| Slippage surfaces | Recompute at least daily and on demand before recommendations |

### Signal Source: SN88 Strategies (Optional)

- Treat as idea discovery only.
- Pull top strategy allocations if available via a public endpoint or scraped feed.
- Use only to generate candidate subnets. All candidates must pass your eligibility and liquidity gates.

### Data Quality and Reliability

- Rate limit handling and retries with backoff.
- Stale data detection. Freeze recommendations if key datasets are stale beyond a threshold.
- Snapshot versioning. Every recommendation and alert must reference the data snapshot used.

---

## System Architecture

### Deployment Model

Local first via Docker Compose.

### Fixed Ports

| Service | Host Port |
|---------|-----------|
| Frontend | 3050 |
| Backend | 8050 |
| Postgres | 5435 |

### Tech Stack (Proposed Default)

- **Frontend:** React with TypeScript, Vite, TanStack Query
- **UI:** Tailwind plus a component kit
- **Backend:** FastAPI Python
- **DB:** Postgres
- **Jobs and cache:** Redis plus a simple scheduler. APScheduler inside the backend for v1, move to Celery later if needed.
- **Migrations:** Alembic
- **Charts:** Lightweight chart library, keep it stable

**Key rationale:**
- FastAPI is good for data heavy services and numeric logic.
- Postgres handles time series history fine at this scale.
- Redis helps avoid overcalling TaoStats and supports job locks.

### Repository Structure (Example)

```
TAO-Treasury/
├── frontend/    # UI, pages, API client, charting, state
├── backend/     # FastAPI app, services, strategy engine, risk engine, tasks, tests
└── infra/       # docker compose, env templates, scripts
```

---

## Security Requirements

- Never paste API keys in chat or code. Keep in .env. Add .env to .gitignore.
- Bind services to 127.0.0.1 by default.
- Store only derived analytics and public chain metrics in DB. Do not store the API key.
- Add audit logging for recommendations and alerts.

---

## Database Model (Minimum Tables)

### Core

| Table | Purpose |
|-------|---------|
| positions | Current per subnet holdings, entry metadata, validator used |
| position_history | Time series of balances, mid value, executable value, rates, emissions |
| subnets | Current subnet metrics, including flow stats and eligibility flags |
| subnet_history | Time series for pools, rates, flow, emissions share |
| validators | Metrics and yields |
| slippage_surfaces | Cached slippage by subnet, size, action, timestamp |

### Decision and Audit

| Table | Purpose |
|-------|---------|
| alerts | Type, severity, netuid, message, data snapshot pointer |
| recommendations | Buy, sell, trim, hold, target allocation, reason, priority, estimated cost |
| decision_log | Full snapshot of inputs and computed outputs at time of recommendation |

---

## Backend API (Minimum Endpoints)

### Read-only Endpoints for UI

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/v1/portfolio | Current NAVs, allocation, drawdowns, regime |
| GET | /api/v1/portfolio/history?days=N | Time series of NAVs and drawdowns |
| GET | /api/v1/positions | Current positions with mid and executable metrics |
| GET | /api/v1/positions/{netuid} | Detail view with history and triggers |
| GET | /api/v1/subnets | Ranked eligible list with gating rationale |
| GET | /api/v1/subnets/{netuid} | Subnet detail with pools, flow, slippage, eligibility |
| GET | /api/v1/alerts | Active alerts |
| POST | /api/v1/alerts/{id}/ack | Acknowledge alert |
| GET | /api/v1/recommendations | Current recommendation set and expected costs |
| POST | /api/v1/recommendations/{id}/mark_executed | Manual bookkeeping only |

### Ops Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/tasks/refresh | Manual refresh trigger |
| GET | /api/v1/health | Service status and staleness checks |

---

## Frontend UX (Minimum Screens)

| Screen | Content |
|--------|---------|
| Dashboard | Total TAO, mid NAV, executable NAV, drawdown, regime, alerts, sleeve vs root vs cash |
| Positions | Sortable table, per position action, exit slippage, flow state |
| Opportunities | Eligible subnets with why, expected net return, liquidity |
| Rebalance | Proposed trades with sizes, estimated slippage, priority |
| Analytics | Return decomposition, attribution, turnover, benchmark comparison |
| Settings | Risk params, trade limits, category caps, default position sizes for slippage |

---

## Backtesting and Validation

### Backtest Engine Requirements

**Input:** Historical pools, flow, emissions, slippage surfaces, validator yields.

**Strategy simulation:** Apply regime rules, gates, sizing, turnover limits, exit ladder.

**Output metrics:**
- Realized TAO return and annualized APY
- Max executable drawdown
- Turnover and trades per period
- Slippage paid and fees paid
- Attribution by subnet and by factor

**Frontier generation:**
- Sweep sleeve weight and risk limits.
- Produce APY vs drawdown tradeoff curve and recommended operating point.

---

## Success Criteria: Acceptance Tests

### Functional

- App runs via Docker with required ports.
- Ingests TaoStats data and persists history.
- Computes mid NAV and executable NAV correctly for test fixtures.
- Computes drawdown on executable NAV.
- Produces consistent eligibility results given fixed input data.
- Generates recommendations that obey all constraints.
- Shows full audit trail for each recommendation.

### Quantitative

- Backtest produces reproducible results from the same dataset.
- Recommendations show estimated execution costs and expected net impact.
- System can answer feasibility of target return vs drawdown with evidence, not projections.

---

## Implementation Phases (Suggested)

### Phase 1: Core Plumbing

- Docker compose with ports 3050, 8050, 5435.
- Backend skeleton, TaoStats client, DB schema and migrations.
- Basic ingestion jobs and staleness checks.
- Minimal UI dashboard and positions list.

### Phase 2: Accounting and Risk

- Mid NAV and executable NAV.
- Slippage surfaces caching.
- Drawdown computation and basic alerts.
- Decision log.

### Phase 3: Strategy Engine v1

- Taoflow regime model and eligibility gate.
- Position sizing by exitability.
- Weekly rebalance recommendation generator.
- Constraint enforcement and explanation strings.

### Phase 4: Backtesting

- CLI to run simulation.
- Report outputs and frontier sweeps.
- Compare hold vs strategy.

### Phase 5: Polish

- Better analytics, attribution, benchmarks.
- Optional SN88 candidate feed if feasible.
- Hardening, tests, docs.

---

## Operational Notes for the Coding Expert

- Do not request or store secrets in code. Use .env and docker secrets patterns.
- Build the strategy module as a pure library with deterministic functions so it is testable.
- Treat data snapshots as immutable inputs to the decision engine.
- Prioritize correctness of executable pricing and taoflow gating. That is the edge and the risk control.
