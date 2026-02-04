# TaoStats SDK and Examples Analysis

Deep dive analysis of the TaoStats SDK and examples repos, with recommendations for TAO Treasury improvements.

## Repositories Analyzed

1. **ts-sdk** (`https://github.com/taostat/ts-sdk.git`) - Official TypeScript SDK
2. **awesome-taostats-api-examples** (`https://github.com/taostat/awesome-taostats-api-examples.git`) - Python examples

---

## Executive Summary

### Key Opportunities Found

| Category | Impact | Effort | Priority |
|----------|--------|--------|----------|
| Slippage Calculation (client-side) | High | Medium | 1 |
| Validator Yield/APY Endpoint | High | Low | 2 |
| Fear & Greed Index Integration | Medium | Low | 3 |
| Live Balance/Block Endpoints | Medium | Low | 4 |
| Stake Earnings Calculation | High | Medium | 5 |
| TradingView UDF Data | Low | Low | 6 |
| Weight Copier Detection | Medium | Medium | 7 |
| Parent-Child Hotkey Relations | Low | Low | 8 |

---

## Part 1: API Endpoints We're Missing

### 1.1 High-Value Missing Endpoints

#### `/api/dtao/validator/yield/latest/v1` - Validator APY Data
**Current State**: We call this endpoint but may not be extracting all available data.

**SDK reveals these fields**:
- `apy` - Annualized percentage yield
- `epoch_participation` - How often validator participates
- `min_stake` filtering
- Ordering by APY

**Recommendation**: Enhance validator sync to pull APY data and use it for recommendation scoring.

---

#### `/api/dtao/slippage/v1` - Slippage API with Full Response
**Current State**: We use this but the SDK shows additional response fields we may be missing.

**SDK response fields**:
```typescript
interface SlippageData {
  netuid: number;
  block_number: number;
  timestamp: string;
  alpha_price: string;           // Price in TAO
  output_tokens: string;         // Output tokens received as rao
  expected_output_tokens: string; // Tokens expected as rao
  diff: string;                  // Difference in rao
  slippage: string;              // Slippage as value
}
```

**Recommendation**: Update slippage response parsing to capture `expected_output_tokens` for better UI display.

---

#### `/api/dtao/pool/latest/v1` - Enhanced Pool Data
**Current State**: We use this endpoint.

**SDK reveals additional fields we might not be using**:
```typescript
interface CurrentSubnetPools {
  fear_and_greed_index: string;
  fear_and_greed_sentiment: string;
  price_change_1_hour: string;
  price_change_1_day: string;
  price_change_1_week: string;
  price_change_1_month: string;
  tao_volume_24_hr: string;
  tao_buy_volume_24_hr: string;
  tao_sell_volume_24_hr: string;
  buys_24_hr: number;
  sells_24_hr: number;
  buyers_24_hr: number;
  sellers_24_hr: number;
  seven_day_prices: SevenDayPrice[];  // Mini chart data!
  startup_mode: boolean;
}
```

**High-Value Fields to Add**:
1. `fear_and_greed_index/sentiment` - Market sentiment indicator
2. `price_change_*` - Price momentum data
3. `seven_day_prices` - Sparkline chart data without extra API calls
4. `startup_mode` - Identify new subnets in bootstrap phase

---

#### `/api/v1/live/accounts/{address}/balance-info` - Live Balance
**Current State**: Not implemented.

**Value**: Real-time free TAO balance without caching delays. Useful for:
- Pre-trade balance validation
- Real-time portfolio updates
- Transaction confirmation

---

#### `/api/validator/weight_copier/v1` - Weight Copiers
**Current State**: Not implemented.

**Value**: Identify validators that copy weights from others. Important for:
- Validator quality scoring
- Avoiding validators that don't add unique value
- Understanding validator behavior

---

#### `/api/hotkey/family/latest/v1` - Parent-Child Hotkey Relations
**Current State**: Not implemented.

**Value**: Track validator "families" (parent validators with child hotkeys). Useful for:
- Understanding validator stake distribution across multiple hotkeys
- Detecting concentration risk across related validators

---

### 1.2 Missing Endpoints We Should Add

| Endpoint | Purpose | Priority |
|----------|---------|----------|
| `/api/dtao/tradingview/udf/history` | Chart data in TradingView format | Low |
| `/api/subnet/distribution/incentive/v1` | Miner incentive distribution | Medium |
| `/api/subnet/distribution/coldkey/v1` | Coldkey distribution per subnet | Medium |
| `/api/metagraph/latest/v1` | Full metagraph data for subnet | Medium |
| `/api/pending_coldkey_swap/v1` | Track pending coldkey swaps | Low |

---

## Part 2: Client-Side Slippage Calculation

### The SDK's Approach

The ts-sdk includes **client-side slippage calculation** using the constant product AMM formula. This is more efficient than calling the API for each calculation.

**Key file**: `src/helpers/network/get-slippage.ts`

```typescript
// Constant product formula: x * y = k
// After adding tao input: (taoPool + tao) * (alphaPool - alphaOut) = k
// Solving for alphaOut: alphaOut = alphaPool - (k / (taoPool + tao))

function getAlphaFromTaoForSlippageCalc(taoAmount, taoReserves, alphaReserves) {
  const k = taoPool.multipliedBy(alphaPool);
  const newAlphaReserves = k.dividedBy(taoPool.plus(tao));
  const alphaOut = alphaPool.minus(newAlphaReserves);
  return alphaOut;
}
```

### Recommendation: Implement Client-Side Slippage

**Benefits**:
1. **No API calls needed** - Calculate slippage locally
2. **Instant updates** - Recalculate on input change without network latency
3. **Reduced API usage** - One fewer endpoint to rate-limit against

**Implementation Plan**:
```python
# backend/app/services/analysis/slippage_calculator.py

from decimal import Decimal

def calculate_stake_slippage(
    tao_amount: Decimal,
    tao_reserves: Decimal,
    alpha_reserves: Decimal,
    tao_emission: Decimal = Decimal("0"),
    alpha_emission: Decimal = Decimal("0"),
) -> dict:
    """Calculate slippage for TAO -> Alpha (stake) using constant product formula."""
    # Include emissions in reserves
    effective_tao = tao_reserves + tao_emission
    effective_alpha = alpha_reserves + alpha_emission

    # k = x * y
    k = effective_tao * effective_alpha

    # After swap: (tao + input) * (alpha - output) = k
    new_alpha_reserves = k / (effective_tao + tao_amount)
    alpha_output = effective_alpha - new_alpha_reserves

    # Ideal output (1:1 ratio)
    ideal_output = tao_amount

    # Slippage percentage
    slippage_pct = ((ideal_output - alpha_output) / ideal_output) * 100

    return {
        "output_tokens": alpha_output,
        "expected_tokens": ideal_output,
        "slippage_pct": max(Decimal("0"), slippage_pct),
    }
```

---

## Part 3: Stake Earnings Calculation

### What the Examples Teach Us

The `delegation_stake_earnings.py` example shows a sophisticated approach to calculating actual stake earnings:

```python
# The key insight: stake balance changes include both earnings AND delegations
# Formula: earnings = balance_change - (delegations - undelegations)

total_stake_earnings = dod_staked_sum - sum_delegation_events
```

### Current Gap

We track transactions but don't separate:
- **Passive earnings** (emissions, staking rewards)
- **Active changes** (user stakes/unstakes)

### Recommendation: Implement Earnings Tracker

```python
# backend/app/services/analysis/earnings_tracker.py

async def calculate_stake_earnings(
    coldkey: str,
    start_timestamp: int,
    end_timestamp: int,
) -> dict:
    """Calculate actual stake earnings (excluding deposits/withdrawals)."""

    # 1. Get balance changes from account history
    history = await taostats_client.get_account_history(
        address=coldkey,
        timestamp_start=start_timestamp,
        timestamp_end=end_timestamp,
    )

    total_balance_change = Decimal("0")
    for i, record in enumerate(history["data"][1:], 1):
        prev = history["data"][i-1]
        change = Decimal(record["balance_staked"]) - Decimal(prev["balance_staked"])
        total_balance_change += change

    # 2. Get all delegation events (stakes + unstakes)
    events = await taostats_client.get_all_delegation_events(coldkey=coldkey)

    net_delegations = Decimal("0")
    for event in events:
        amount = Decimal(event["amount"]) / Decimal("1e9")
        if event["action"] == "DELEGATE":
            net_delegations += amount
        else:  # UNDELEGATE
            net_delegations -= amount

    # 3. Earnings = Balance Change - Net Delegations
    earnings = total_balance_change - net_delegations

    return {
        "period_start": start_timestamp,
        "period_end": end_timestamp,
        "total_balance_change_tao": total_balance_change,
        "net_delegations_tao": net_delegations,
        "stake_earnings_tao": earnings,
    }
```

---

## Part 4: Architecture Improvements from SDK

### 4.1 Modular Design

The ts-sdk uses a clean modular architecture:

```
TaoStatsClient
├── taoPrices: TaoPricesModule
├── subnets: SubnetsModule
├── validators: ValidatorsModule
├── delegations: DelegationsModule
├── accounts: AccountsModule
├── metagraph: MetagraphModule
├── chain: ChainModule
└── live: LiveModule
```

**Current TAO Treasury**: Single 791-line `taostats_client.py` file.

**Recommendation**: Consider splitting into modules for maintainability:
```
taostats/
├── __init__.py
├── client.py (base HTTP client)
├── accounts.py
├── subnets.py
├── validators.py
├── delegations.py
├── prices.py
└── pools.py
```

### 4.2 Type Safety

The SDK provides comprehensive TypeScript interfaces for all responses. We should add Pydantic models for type safety:

```python
# backend/app/schemas/taostats.py

from pydantic import BaseModel
from decimal import Decimal
from typing import Optional, List

class SubnetPoolData(BaseModel):
    netuid: int
    price: Decimal
    market_cap: Decimal
    fear_and_greed_index: Optional[str]
    fear_and_greed_sentiment: Optional[str]
    price_change_1_day: Optional[Decimal]
    price_change_1_week: Optional[Decimal]
    seven_day_prices: List[dict]
    startup_mode: bool
```

### 4.3 Exponential Backoff

The SDK uses exponential backoff for retries:
```typescript
const delay = Math.pow(2, originalRequest._retryCount) * 1000;
```

Our current implementation uses tenacity with similar logic - this is good!

---

## Part 5: Immediate Action Items

### Priority 1: Quick Wins (< 1 day each)

1. **Add Fear & Greed Index to Dashboard**
   - Already returned by `/api/dtao/pool/latest/v1`
   - Add to Portfolio schema and UI

2. **Add 7-Day Price Sparklines**
   - `seven_day_prices` already in pool response
   - Pass to frontend for mini charts

3. **Add Price Momentum Indicators**
   - `price_change_1_hour`, `price_change_1_day`, `price_change_1_week`
   - Show as colored badges on positions

### Priority 2: Medium Effort (1-3 days each)

4. **Implement Client-Side Slippage Calculator**
   - Reduce API calls for slippage estimation
   - Enable real-time slippage preview in UI

5. **Add Stake Earnings Report**
   - Calculate actual earnings vs deposits
   - Show daily/weekly/monthly earnings

6. **Add Weight Copier Detection**
   - Call `/api/validator/weight_copier/v1`
   - Flag weight copiers in validator selection

### Priority 3: Future Enhancements

7. **Modularize TaoStats Client**
   - Split into domain-specific modules
   - Add Pydantic response models

8. **Add Live Balance Endpoint**
   - Real-time balance checks before trades
   - Transaction confirmation polling

---

## Part 6: Code Bloat Reduction

### Current Redundancies Found

1. **Duplicate Pagination Logic**
   - `get_all_trades`, `get_all_extrinsics`, `get_all_delegation_events` are nearly identical
   - Extract into generic paginator

2. **Cache Key Generation**
   - Manual string concatenation everywhere
   - Create helper function

### Recommended Refactoring

```python
# Generic paginator
async def paginate_all(
    fetch_fn: Callable,
    **kwargs,
) -> List[Dict]:
    """Generic pagination helper."""
    all_data = []
    page = 1
    max_pages = kwargs.pop("max_pages", 100)

    while page <= max_pages:
        response = await fetch_fn(page=page, **kwargs)
        data = response.get("data", [])
        if not data:
            break
        all_data.extend(data)

        pagination = response.get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break

        page += 1
        await asyncio.sleep(0.1)

    return all_data

# Usage:
trades = await paginate_all(self.get_trades, coldkey=wallet, max_pages=50)
```

---

## Part 7: New Feature Opportunities

### 7.1 Validator Quality Score

Using data from multiple endpoints, we could build a validator quality score:

```python
def calculate_validator_score(validator_data: dict) -> int:
    score = 100

    # Deduct for weight copying
    if validator_data.get("is_weight_copier"):
        score -= 30

    # Boost for high APY
    apy = validator_data.get("apy", 0)
    if apy > 20:
        score += 10

    # Deduct for low epoch participation
    participation = validator_data.get("epoch_participation", 1.0)
    if participation < 0.9:
        score -= 20

    # Boost for high vtrust
    vtrust = validator_data.get("vtrust", 0)
    if vtrust > 0.8:
        score += 15

    return max(0, min(100, score))
```

### 7.2 Market Sentiment Dashboard Widget

Using Fear & Greed data:
```python
{
    "index": 45,
    "sentiment": "Fear",
    "recommendation": "Consider accumulating - market is fearful"
}
```

### 7.3 Subnet Startup Mode Alert

Flag subnets in startup mode (bootstrap phase) as higher risk:
```python
if subnet.startup_mode:
    warnings.append({
        "type": "startup_mode",
        "message": f"SN{netuid} is in startup mode - higher volatility expected"
    })
```

---

## Summary

The TaoStats SDK and examples reveal several opportunities to improve TAO Treasury:

1. **Immediate value**: Fear & Greed index, price sparklines, price momentum
2. **Efficiency gains**: Client-side slippage calculation
3. **New capabilities**: Stake earnings tracking, validator quality scoring
4. **Code quality**: Modular architecture, better type safety

The highest-impact items are:
1. Adding the already-available pool data fields to our UI
2. Implementing client-side slippage calculation
3. Building a true stake earnings calculator

These improvements would make the app significantly more informative and responsive without major architectural changes.
