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
| **data_sync** | `tao_value_mid`, `alpha_balance`, `current_apy`, `daily_yield_tao` + **interim** `cost_basis_tao`, `alpha_purchased`, `entry_price_tao` (NEW STAKES/RE-ENTRY ONLY) | staking API + validator API. Interim cost basis for new stakes/re-entry only (FIFO can't fill gap until API indexes buy). On unstakes: triggers targeted FIFO instead of adjusting fields. |
| **cost_basis_service** | `entry_price_tao`, `cost_basis_tao`, `alpha_purchased`, `realized_pnl_tao`, `realized_yield_tao`, `realized_alpha_pnl_tao` (SOLE AUTHORITY) | accounting/tax API (`token=SN{n}`) — alpha FIFO. Writes to BOTH Position and PositionCostBasis. Called on full sync AND targeted (on position decreases in any tier). |
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

- **Targeted FIFO on position changes**: When `sync_positions()` detects alpha_balance decreased >0.5%, `sync_all()` immediately calls `cost_basis_service.compute_cost_basis_from_accounting(netuids=changed)` before the decomposition step. This adds 1 API call per changed position to any sync tier. If the accounting API hasn't indexed the transaction yet, the FIFO returns the same stale values (matching TaoStats), and the decomposition uses effective values locally. On new stakes (increase >2%), interim cost_basis is set at current price (FIFO can't fill the gap until the buy is indexed).
- **FIFO authority principle**: FIFO-owned fields (`cost_basis_tao`, `alpha_purchased`, `entry_price_tao`, `realized_*`) are ONLY written by `cost_basis_service`. Exception: initial values on first-entry/re-entry/new-stake in `_upsert_position()` (overwritten by FIFO on next run). No other code modifies these fields.
- **`compute_unrealized_decomposition()`** is a pure math function (zero API calls) that recomputes `unrealized_pnl`, `unrealized_yield`, and `unrealized_alpha_pnl` from cached Position fields. Handles stale FIFO gracefully: when `alpha_purchased > alpha_balance` (API lag after unstake), uses `total_yield_alpha` to estimate emission alpha held, computes `effective_purchased = alpha_balance - emission_estimate` (excludes emission from alpha_pnl), and `effective_cost = cost_basis * (effective_purchased / alpha_purchased)`. Yield is floored at 0 (emission income can never be negative). FIFO-owned DB fields are never modified. This is what makes Tier 1 fast.
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
- **Unrealized/realized split differs from TaoStats**: We use FIFO book cost (cost of remaining lots) for unrealized; TaoStats uses net invested (total_staked - total_unstaked). Both produce the same total P&L (unrealized + realized), just split differently. Our FIFO gives a more precise per-position view (better for tax); TaoStats gives a simpler aggregate. Yield matches closely (<1% gap).
- Positions without accounting data fall back to dtao/trade-based FIFO (may be incomplete).
- **API lag after position changes**: Between a position change and the accounting/tax API indexing it (typically minutes), the decomposition uses effective values that approximate the yield/alpha split. For unindexed buys (FIFO shows 0 lots but position is active), interim cost_basis is set from current price. TaoStats match is preserved during this window because both systems use the same stale data. The FIFO catches up on the next sync after the API indexes the transaction.

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

### 2026-02-09: Interim cost basis adjustments for position changes (SUPERSEDED — see fix below)
- **Problem**: When user shifted ~10τ from Chutes (SN64) to DSperse (SN2), Chutes showed the TAO reduction as negative yield.
- **Fix attempted**: Two-layer interim cost basis adjustment (proportional scaling on unstake + `_correct_stale_cost_basis()` safety net).
- **Result**: Broke TaoStats match. See next entry for root cause and proper fix.

### 2026-02-09: Fix position change accounting (revert interim adjustments)
- **Problem**: Interim cost_basis adjustments (from entry above) broke TaoStats match by reducing cost_basis without increasing realized_pnl. Also zeroed yield by scaling alpha_purchased ≈ alpha_balance. The proportional scaling approach was fundamentally wrong because it changed one side of the ledger without the other.
- **Fix**: Reverted interim unstake adjustments. Established FIFO as sole authority on cost_basis/alpha_purchased/realized fields. Added targeted FIFO recomputation (1 API call per changed position) on alpha decreases in all sync tiers. Added stale-FIFO detection in decomposition that uses effective local values when alpha_purchased > alpha_balance.
- **Key principle**: TaoStats and our FIFO use the same data source (accounting/tax API) with the same lag. Don't try to be "ahead" of TaoStats — stale FIFO values that match TaoStats are better than interim values that diverge.
- **Architectural rule**: FIFO-owned fields (cost_basis_tao, alpha_purchased, entry_price_tao, realized_*) are ONLY written by cost_basis_service. Exception: initial values on first-entry/re-entry/new-stake in _upsert_position (overwritten by FIFO on next run).
- **Key changes**:
  - `data_sync.py`: Removed proportional scaling on unstake. Removed `_correct_stale_cost_basis()` entirely. `_upsert_position()` returns `(position, alpha_decreased)` signal. `sync_positions()` collects decreased netuids. `sync_all()` triggers targeted FIFO before decomposition.
  - `cost_basis.py`: `compute_cost_basis_from_accounting(netuids=...)` accepts optional filter for targeted recomputation.
  - `yield_tracker.py`: `compute_unrealized_decomposition()` uses effective local values (`min(alpha_purchased, alpha_balance)`) when FIFO is stale, preserving TaoStats match.

### 2026-02-09: Fix stale-FIFO decomposition and unindexed buy handling
- **Problem 1**: Chutes (SN64) yield was -0.000000346τ. When stale FIFO (alpha_purchased > alpha_balance), `effective_purchased = alpha_balance` included emission alpha (~10.1α). This over-attributed to alpha_pnl, leaving yield as an impossible small negative.
- **Problem 2**: DSperse (SN2) had cost_basis=0, alpha_purchased=0 despite holding 886.77α worth 9.91τ. The FIFO correctly consumed all old lots (3 buys, 3 sells). The recent buy (Chutes→DSperse rebalance) wasn't indexed by the accounting API. The decomposition guard `if effective_cost > 0 else 0` zeroed unrealized PnL.
- **Root cause analysis**: P&L gap of 1.17τ (our total_pnl 1.68 vs true total_pnl 2.85) was almost entirely from DSperse's missing unrealized. Unrealized/realized split differs from TaoStats because we use FIFO book_cost, they use net_invested — total P&L converges, split differs. Yield matched well even before fix (6.55 vs 7.53).
- **Fix 1** (`yield_tracker.py`): In stale FIFO case, use `total_yield_alpha` to estimate emission alpha held: `effective_purchased = max(alpha_balance - min(total_yield_alpha, alpha_balance), 0)`. This correctly excludes emission from alpha_pnl calculation. Added yield floor at 0 (emission income cannot be negative).
- **Fix 2** (`cost_basis.py`): After FIFO processing, when all lots consumed but position active with alpha exceeding emission estimate, set interim cost_basis from current price. `unindexed_alpha = alpha_balance - emission_estimate`, `cost_basis = unindexed_alpha * current_price`. Overwritten when API indexes the buy.
- **Results after fix**: Chutes yield = +0.95τ (was -0.000). DSperse cost_basis = 9.79τ (was 0), unrealized = +0.11τ. Total yield = 7.60τ (TaoStats: 7.53τ, <1% gap). P&L gap reduced from 1.17τ to 0.13τ (89% reduction). Zero negative yields. Zero ledger identity violations.

### 2026-02-09: FX Exposure card rewrite (per-position decomposition)
- **Problem**: `_compute_conversion_exposure()` had 4 bugs: inactive positions invisible (query found nothing after position model changes), active positions missed realized FX, aggregated entry price lost per-position accuracy, root yield misattributed.
- **Fix**: Rewrote with single per-position loop over PositionCostBasis records. For each position: α/τ = tao_pnl × entry_usd_per_tao, τ/$ = total_usd_pnl - α/τ (residual enforces identity). Root: α/τ = 0, τ/$ = total_usd_pnl.
- **Key changes**: `portfolio.py` `_compute_conversion_exposure()` reduced from ~240 lines to ~95 lines. No schema/frontend changes needed.
- **Result**: Identity α/τ + τ/$ = total_pnl_usd holds exactly (0.00 difference). 46/46 positions included (39 active + 7 inactive).

### 2026-02-07: Eliminated competing calculation paths
- Removed yield_tracker writes to `alpha_purchased`/`entry_price_tao` (owned by cost_basis)
- Removed `unrealized_pnl_tao` overwrite in `data_sync.sync_position_yields` (owned by cost_basis)
- Changed portfolio cost basis from `NAV - PnL` derivation to `sum(position.cost_basis_tao)`
- Deleted dead code: `compute_realized_pnl_from_accounting`, `backfill_usd_from_accounting`
- Frontend already uses pre-computed backend values (no local calculations)
