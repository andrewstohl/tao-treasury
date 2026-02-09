# CLAUDE.md - TAO Treasury Mgmt

## CRITICAL WORKING RULES (NON-NEGOTIABLE)

### 1. STOP AND ASK BEFORE CODING
- NEVER start writing code without explaining your plan first
- NEVER assume the user wants you to continue from where you left off
- ALWAYS get explicit approval before making changes
- If unsure about ANYTHING, ask - don't guess

### 2. ACT LIKE A PROFESSIONAL SOFTWARE ENGINEER
- Think through the FULL problem before proposing a solution
- Consider ALL downstream implications of any change
- Make the RIGHT fix, not the quick fix
- Value correctness and scalability over speed
- No shortcuts. No lazy patches. No "good enough for now."

### 3. NO TUNNEL VISION
- Don't follow broken code patterns just because they exist
- Step back and question whether the current approach is even correct
- If an approach is fundamentally broken, say so - don't patch it

### 4. COMPLETE FIXES ONLY
- If fixing one code path, check if the same broken logic exists elsewhere
- Never leave related broken things unfixed
- Think through the FULL impact of every change

---

## PROJECT

Build a local first web app that manages a TAO treasury wallet across Root and dTAO subnets. The app must maximize long term TAO accumulation while keeping drawdown limited, measured in TAO using executable prices net of slippage and fees. The app does not execute trades. It produces recommendations and risk alerts.

**Spec:** [SPEC.md](./SPEC.md)

---

## INFRASTRUCTURE

- **Backend:** Python/FastAPI, port **8050**, Docker container `tao-treasury-backend`
- **Frontend:** React/Vite, port **3050**, Docker container `tao-treasury-frontend`
- **Database:** PostgreSQL on port 5435, Redis on port 6381
- **Start everything:** `docker compose up -d` from project root
- **.env location:** `/Users/drewstohl/Desktop/TAO-Treasury/.env` (project root, NOT backend/)
- **Wallet:** `5EnHLga3MddTALC4qqB3GH7an96WQk4oRJ2xtbiRgV3n2grd`

---

## SUBNET POSITION MODEL

**Subnets are the investment universe. Each subnet (including Root/SN0) is a persistent entity.**

### Core Concepts

- **128 subnets** = FIXED investment universe (not dynamic). Always 128 possible investments.
- Each subnet has ONE Position record per wallet — **never deleted**
- **Active** = `alpha_balance > 0` (currently staked)
- **Inactive** = `alpha_balance = 0` (fully exited, record persists with realized values)
- Positions are **ACTIVE/INACTIVE** (not "open/closed"). The user cycles in and out frequently and opportunistically.
- **Root (SN0) is just another subnet** — no special handling, no separate `root_stake` logic

### Position Lifecycle

1. **First entry**: Position record created with alpha_balance, tao_value_mid from stake API
2. **Partial add (overweight)**: New FIFO lot created at current price, cost_basis increases
3. **Partial remove (underweight)**: FIFO lots consumed oldest-first, P&L realized on consumed lots
4. **Full exit**: All FIFO lots consumed, all P&L realized. Position stays in DB with `alpha_balance = 0`, unrealized fields = 0, realized fields preserved
5. **Re-entry**: Stake API returns subnet again, new FIFO lots created. FIFO replay of full history naturally handles this — old buys/sells are already consumed, new buys create fresh lots

### Two Tables, Clear Roles

| Table | Role | Lifecycle |
|---|---|---|
| **Position** | Current state + ALL fields needed for KPI aggregation | Never deleted. Zeroed when inactive. |
| **PositionCostBasis** | Full FIFO lot history, trade counts, timestamps | Never deleted. Accumulates across entries/exits. |

- **KPI cards sum Position records ONLY** — no PositionCostBasis queries at portfolio level
- Each sync: cost_basis_service writes FIFO results to BOTH tables. Realized values are copied from PositionCostBasis → Position so everything is in one place for aggregation.

### Service Processing Rules (Active vs All Positions)

| Service | Processes | Why |
|---|---|---|
| **cost_basis pass-2** | ALL positions | Must process final unstakes for realized P&L |
| **yield_tracker** | Active only (`alpha_balance > 0`) | Inactive = no unrealized P&L |
| **compute_unrealized_decomposition** | ALL | Zeros inactive; recomputes active from cached fields |
| **position_metrics._compute_realized_metrics** | ALL PositionCostBasis | Creates missing Position records for orphaned CB entries |
| **slippage_sync** | Active only | Only staked positions have slippage |
| **portfolio_snapshot** | ALL (sum) | Inactive contribute realized values |

---

## AUTHORITATIVE DATA ARCHITECTURE (SINGLE SOURCE OF TRUTH)

**RULE: Read from TaoStats. Never derive what TaoStats provides directly.**

### TaoStats API Endpoints Used

| Endpoint | What it provides |
|---|---|
| `GET /api/dtao/stake/balance/latest/v1?coldkey=` | Position balances: `alpha_balance`, `balance_as_tao` (current value) |
| `GET /api/accounting/tax/v1?coldkey=&token=SN{n}` | Per-subnet: `daily_income` (yield), `token_swap` records (buys/sells) |
| `GET /api/account/balance/latest/v1?address=` | Wallet: `balance_free` (unstaked TAO only — root stake comes from stake API as SN0) |

### Position-Level Field Mapping

| Display Field | TaoStats Source | Formula |
|---|---|---|
| **Current Value** | `balance_as_tao` from staking API | Direct read (rao_to_tao conversion) |
| **Alpha Balance** | `alpha_balance` from staking API | Direct read |
| **Yield (alpha)** | `daily_income` from accounting/tax API | `sum(daily_income)` = total yield alpha earned |
| **Yield (TAO)** | Computed from yield alpha | `total_yield_alpha * (tao_value_mid / alpha_balance)` |
| **Alpha PnL** | `token_swap` records from accounting/tax | `net_purchased_alpha * (current_price - avg_entry_price)` |
| **Cost Basis** | `token_swap` debit amounts from accounting/tax | `sum(debit_amount)` for all buys into this subnet |
| **APY** | Validator data | Direct read from validator record |

### Portfolio-Level Aggregation (KPI Cards)

**Portfolio KPI cards are SIMPLE SUMS of Position records. No separate calculation path. No PositionCostBasis queries.**

| KPI Card | Formula | Notes |
|---|---|---|
| **Current Value** | `unstaked_tao + sum(ALL position.tao_value_mid)` | SN0 included (it IS root). No root_stake add-back. |
| **Yield** | `sum(ALL position.unrealized_yield_tao + position.realized_yield_tao)` | Pure sum across active AND inactive |
| **Alpha** | `sum(ALL position.unrealized_alpha_pnl_tao + position.realized_alpha_pnl_tao)` | Pure sum across active AND inactive |
| **APY** | `sum(position.tao_value_mid * position.apy) / sum(position.tao_value_mid)` | Value-weighted average (active only) |
| **Cost Basis** | `sum(ALL position.cost_basis_tao)` | Direct sum, NEVER derived from NAV - PnL |

### Ledger Identity (Must Always Hold)

```
For each active position:
  unrealized_pnl = tao_value_mid - cost_basis             (ground truth)
  unrealized_alpha_pnl = alpha_purchased * (current_price - entry_price)
  unrealized_yield = unrealized_pnl - unrealized_alpha_pnl (residual, enforces identity)
  current_value = cost_basis + unrealized_pnl

For each inactive position (alpha_balance = 0):
  All unrealized fields = 0
  Realized fields preserved from last FIFO computation

For the portfolio:
  total_current_value = sum(ALL position.tao_value_mid) + unstaked_tao
  total_yield = sum(ALL position.unrealized_yield + position.realized_yield)
  total_alpha_pnl = sum(ALL position.unrealized_alpha_pnl + position.realized_alpha_pnl)
```

**Enforcement**: Yield in TAO is derived as the residual (`unrealized_pnl - alpha_pnl`) so the identity always holds. Yield in alpha terms (`total_yield_alpha`) is still read directly from `daily_income`.

### TaoStats Label → Our API Field Mapping

| TaoStats Label | Our API Field | Meaning |
|---|---|---|
| Current Value | `nav_mid` | Must match TaoStats (sum of all positions + unstaked + root) |
| Unrealized Gains | `pnl.unrealized` | Total unrealized P&L (yield + alpha). Decomposition available via `pnl.unrealized_yield` and `pnl.unrealized_alpha_pnl`. |
| Realized Gains | `pnl.realized` | From FIFO on unstakes |
| Earnings | `yield_income.total_yield` | Sum of all yield (realized + unrealized) |
| APY | `yield_income.portfolio_apy` | Value-weighted avg across positions |

### RULES (Read Every Session)

1. **NEVER derive cost basis** from `NAV - realized - unrealized`. Track it directly from staking transactions.
2. **NEVER have competing calculation paths.** One service computes each metric. No overrides.
3. **Yield = daily_income from accounting/tax API.** No estimations or derivations.
4. **Alpha PnL = price change on purchased alpha only.** Yield alpha is NOT included in alpha PnL.
5. **"Unrealized gains" on TaoStats = alpha PnL only.** Yield is shown separately as "Earnings."
6. **Portfolio values = sum of position values.** No separate portfolio-level calculations.
7. **Verify against TaoStats after every change.** If numbers don't match, the code is wrong.
8. **Cost basis MUST use accounting/tax API** (not dtao/trade). The dtao/trade endpoint misses batch extrinsics.

---

## SERVICE OWNERSHIP (Single Writer Principle)

Each field is written by exactly ONE service. No overrides.

| Service | Owns These Fields | Data Source |
|---|---|---|
| **data_sync** | `tao_value_mid`, `alpha_balance`, `current_apy`, `daily_yield_tao` | staking API + validator API |
| **cost_basis_service** | `entry_price_tao`, `cost_basis_tao`, `alpha_purchased`, `realized_pnl_tao`, `realized_yield_tao`, `realized_alpha_pnl_tao` | accounting/tax API (`token=SN{n}`) — alpha FIFO. Writes to BOTH Position and PositionCostBasis. |
| **yield_tracker** | `total_yield_alpha`, `unrealized_pnl_tao`, `unrealized_yield_tao`, `unrealized_alpha_pnl_tao` | `total_yield_alpha` from accounting/tax API (`daily_income`). Unrealized fields computed with enforced identity: `pnl = value - cost`, `alpha = purchased * (price - entry)`, `yield = pnl - alpha`. |
| **position_metrics_service** | Orchestrator only | Calls cost_basis_service + yield_tracker in correct order |

---

## SYNC TIERS

**`sync_all(mode)` runs in three tiers to balance freshness vs API budget.**

| Tier | Mode | API Calls | Interval | What Runs |
|---|---|---|---|---|
| **1 (Refresh)** | `refresh` | ~5 | 5 min | `sync_positions`, `sync_validators`, `sync_subnet_apys`, `sync_position_yields`, `compute_unrealized_decomposition` (pure math), `create_portfolio_snapshot` |
| **2 (Full)** | `full` | ~130 | 60 min | Tier 1 + `sync_subnets`, `sync_pools`, `sync_delegation_events`, `sync_stake_balance_history`, `transaction_sync`, `cost_basis` (both passes), `position_metrics`/`yield_tracker` (API), `risk_monitor` |
| **3 (Deep)** | `deep` | ~500+ | 24h | Tier 1 + Tier 2 + `slippage_sync` (~380 calls), `nav_calculator` (executable NAV) |

### Key Design Decisions

- **`compute_unrealized_decomposition()`** is a pure math function (zero API calls) that recomputes `unrealized_pnl`, `unrealized_yield`, and `unrealized_alpha_pnl` from cached Position fields (`cost_basis_tao`, `alpha_purchased`, `entry_price_tao` from last full sync). This is what makes Tier 1 fast.
- **`total_yield_alpha`** (from `daily_income` API) is written by yield_tracker in Tier 2 but is **not used by KPI cards or frontend**. KPI yield uses `unrealized_yield_tao` (the residual from ledger identity).
- **Slippage** is 60-70% of all API calls but only feeds executable NAV, which is not shown on KPI cards.

### API Endpoint

```
POST /api/v1/tasks/refresh?mode=refresh|full|deep
```

Default mode is `refresh`. Frontend: click = refresh, shift+click = full.

### Scheduler Jobs

| Job ID | Interval | Mode |
|---|---|---|
| `data_sync_refresh` | `wallet_refresh_minutes` (5 min) | refresh |
| `data_sync_full` | `full_sync_minutes` (60 min) | full |
| `data_sync_deep` | `slippage_refresh_hours` (24h) | deep |

---

## KNOWN LIMITATIONS

- **dtao/trade endpoint** misses batch extrinsics (cross-subnet rebalances). Cost basis uses accounting/tax API instead.
- Realized P&L split (realized vs unrealized) may differ slightly from TaoStats due to FIFO vs their methodology.
- Positions without accounting data fall back to dtao/trade-based FIFO (may be incomplete).

---

## COMPLETED WORK (Do Not Redo)

### 2026-02-08: Subnet position model + KPI card architecture
- **Problem**: Positions deleted when fully unstaked → realized data lost. Root/SN0 special-cased everywhere → scope mismatches. KPI cards read from multiple tables with different lifecycles → numbers don't add up.
- **Fix**: Established subnet position model. Positions are persistent (never deleted), zeroed when inactive. Root = SN0 = just another subnet. KPI cards = pure sums of Position records only. Unrealized yield derived as residual to enforce ledger identity.
- **Key changes**: Stop deleting positions in data_sync. Remove all SN0 carve-outs. Copy realized values from PositionCostBasis → Position each sync. Portfolio snapshot aggregates Position table only.

### 2026-02-08: Cost basis from accounting/tax API (alpha FIFO)
- **Problem**: dtao/trade endpoint missed batch extrinsics → cost_basis_tao was ~50% wrong for positions with rebalances (e.g., SN64 showed P&L +55τ instead of ~3τ)
- **Fix**: Rewrote `compute_cost_basis_from_accounting()` in `cost_basis.py` to fetch per-subnet accounting records (`token=SN{n}`) and build alpha-based FIFO lots from `credit_amount`/`debit_amount` token_swap records
- **Key detail**: For batch extrinsics (same timestamp), buys sort BEFORE sells to avoid false emission attribution
- **Result**: SN64 cost_basis went from 46.96τ to 98.92τ, P&L from +55τ to +2.94τ (TaoStats: 3.16τ)

### 2026-02-09: Three-tier sync + bug fixes + CLAUDE.md codification
- **Problem**: Sync ran ~600 API calls every 5 min (60+ sec). 70% were slippage calls that don't affect KPI cards. Unrealized decomposition fetched from API every sync but is actually pure math. 4 bugs prevented KPI accuracy: cost_basis skipped inactive positions, competing unrealized_pnl write, orphaned PositionCostBasis records, Decimal JSON serialization in risk_monitor.
- **Fix**: Restructured `sync_all()` into three tiers (refresh/full/deep). Extracted `compute_unrealized_decomposition()` as pure function. Fixed all 4 bugs. Updated scheduler to three jobs. Codified subnet position model in CLAUDE.md.
- **Key changes**:
  - `data_sync.py`: `sync_all(mode)` with refresh (<3s, ~5 calls), full (~130 calls), deep (~500+ calls). Added `_recompute_unrealized_decomposition()` helper.
  - `yield_tracker.py`: Extracted `compute_unrealized_decomposition()` as module-level pure function.
  - `cost_basis.py`: Removed `alpha_balance > 0` filter (Bug 1). Removed competing `unrealized_pnl_tao` write (Bug 2).
  - `position_metrics.py`: Auto-create Position for orphaned PositionCostBasis (Bug 3).
  - `risk_monitor.py`: `_sanitize_for_json()` for Decimal → float (Bug 4).
  - `scheduler.py`: Three jobs (`data_sync_refresh` 5m, `data_sync_full` 60m, `data_sync_deep` 24h).
  - `tasks.py`: `mode` query parameter on `/api/v1/tasks/refresh`.
  - Frontend: click = refresh, shift+click = full sync.

### 2026-02-07: Eliminated competing calculation paths
- Removed yield_tracker writes to `alpha_purchased`/`entry_price_tao` (owned by cost_basis)
- Removed `unrealized_pnl_tao` overwrite in `data_sync.sync_position_yields` (owned by cost_basis)
- Changed portfolio cost basis from `NAV - PnL` derivation to `sum(position.cost_basis_tao)`
- Deleted dead code: `compute_realized_pnl_from_accounting`, `backfill_usd_from_accounting`
- Frontend already uses pre-computed backend values (no local calculations)
