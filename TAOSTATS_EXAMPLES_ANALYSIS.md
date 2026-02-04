# TaoStats API Examples Analysis

Deep dive into the `awesome-taostats-api-examples` repository with actionable insights for TAO Treasury.

**Repository**: https://github.com/taostat/awesome-taostats-api-examples.git

---

## Repository Contents

| File | Purpose | Relevance to TAO Treasury |
|------|---------|---------------------------|
| `apibase.py` | API client template with pagination | Pattern reference |
| `balances.py` | Daily account balance tracking | Portfolio history |
| `delegation_stake_earnings.py` | Calculate actual stake earnings | **High value** - earnings tracking |
| `valis_24hour_change.py` | 24-hour validator stake changes | Validator flow analysis |

---

## Example 1: `apibase.py` - API Client Pattern

### What It Does
A reusable API client class with:
- Rate limit handling (429 status with Retry-After header)
- Automatic pagination through results
- CSV export of paginated data

### Key Code Pattern
```python
class APIClient:
    def __init__(self, base_url, api_key=None, max_retries=3, retry_delay=60):
        self.base_url = base_url
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def get_json(self, endpoint, params=None):
        retries = 0
        while retries <= self.max_retries:
            response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 429:
                # Use Retry-After header if available
                retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                time.sleep(retry_after)
                retries += 1
            elif response.status_code == 200:
                return response.json()
```

### Pagination Pattern
```python
params['page'] = 1
while params['page'] is not None:
    response_json = api.get_json(endpoint=endpoint, params=params)
    if response_json is not None:
        next_page = response_json['pagination']['next_page']
        if page_no == 1:
            df = pd.DataFrame(response_json['data'])
        else:
            df = df.append(response_json['data'])
        params['page'] = next_page
```

### What We Can Learn
1. **Retry-After Header**: We should check for and respect the `Retry-After` header from the API
2. **DataFrame accumulation**: They build up a DataFrame for analysis - good pattern for bulk data processing

### Current Gap in TAO Treasury
Our client doesn't check the `Retry-After` header:
```python
# Our current code:
if response.status_code == 429:
    raise TaoStatsRateLimitError("Rate limit exceeded")

# Should be:
if response.status_code == 429:
    retry_after = int(response.headers.get('Retry-After', 60))
    logger.warning(f"Rate limited, waiting {retry_after}s")
    await asyncio.sleep(retry_after)
    # Then retry...
```

---

## Example 2: `balances.py` - Account Balance History

### What It Does
Fetches daily account balance snapshots and calculates day-over-day changes:
- Free balance (available TAO)
- Staked balance (delegated TAO)
- Total balance
- Daily changes for each

### Key API Call
```python
url = f"https://api.taostats.io/api/account/history/v1?address={coldkey}&timestamp_start={start_date}&timestamp_end={end_date}&limit={count}&page={page}&order=timestamp_asc"
```

### Key Calculation
```python
for index, date in enumerate(total_address_history):
    total = float(date['balance_total']) / 1e9
    staked = float(date['balance_staked']) / 1e9
    free = float(date['balance_free']) / 1e9

    if index > 0:
        total_difference = total - float(total_address_history[index-1]['balance_total']) / 1e9
        staked_difference = staked - float(total_address_history[index-1]['balance_staked']) / 1e9
        free_difference = free - float(total_address_history[index-1]['balance_free']) / 1e9
```

### What We Can Learn
1. **Day-over-day tracking**: Simple but powerful - track changes between snapshots
2. **RAO to TAO conversion**: Always divide by 1e9
3. **Order by timestamp_asc**: Chronological processing is easier for delta calculations

### Application to TAO Treasury

We could add a **Portfolio Change Report**:
```python
# backend/app/services/analysis/balance_tracker.py

async def get_balance_changes(
    coldkey: str,
    days: int = 30,
) -> List[Dict]:
    """Get daily balance changes for a wallet."""
    end_ts = int(datetime.now().timestamp())
    start_ts = end_ts - (days * 86400)

    history = await taostats_client.get_account_history(
        address=coldkey,
        timestamp_start=start_ts,
        timestamp_end=end_ts,
    )

    changes = []
    data = history.get("data", [])

    for i, record in enumerate(data):
        change = {
            "date": record["timestamp"],
            "total_tao": Decimal(record["balance_total"]) / Decimal("1e9"),
            "staked_tao": Decimal(record["balance_staked"]) / Decimal("1e9"),
            "free_tao": Decimal(record["balance_free"]) / Decimal("1e9"),
        }

        if i > 0:
            prev = data[i-1]
            change["total_change"] = change["total_tao"] - Decimal(prev["balance_total"]) / Decimal("1e9")
            change["staked_change"] = change["staked_tao"] - Decimal(prev["balance_staked"]) / Decimal("1e9")
            change["free_change"] = change["free_tao"] - Decimal(prev["balance_free"]) / Decimal("1e9")

        changes.append(change)

    return changes
```

---

## Example 3: `delegation_stake_earnings.py` - **Most Valuable**

### What It Does
This is the most sophisticated example. It calculates **actual stake earnings** by separating:
- Balance changes from staking rewards
- Balance changes from user deposits/withdrawals

### The Key Insight
```python
# Balance changes include BOTH:
# 1. Passive earnings (emissions, staking rewards)
# 2. Active changes (user stakes/unstakes)

# To get actual earnings:
# earnings = total_balance_change - net_delegation_events
total_stake_earnings = dod_staked_sum - sum_delegation_events
```

### The Algorithm

**Step 1: Get daily staked balance changes**
```python
url = f"https://api.taostats.io/api/account/history/v1?address={coldkey}..."

dod_staked_sum = 0
for index, date in enumerate(total_address_history):
    staked = float(date['balance_staked']) / 1e9
    if index > 0:
        staked_difference = staked - float(total_address_history[index-1]['balance_staked']) / 1e9
    dod_staked_sum += staked_difference
```

**Step 2: Get all delegation events (deposits/withdrawals)**
```python
url = f"https://api.taostats.io/api/delegation/v1?nominator={coldkey}..."

sum_delegation_events = 0
for event in all_delegation_events:
    amount = float(event['amount']) / 1e9
    if event['action'] == "DELEGATE":
        sum_delegation_events += amount
    else:  # UNDELEGATE
        sum_delegation_events -= amount
```

**Step 3: Calculate actual earnings**
```python
total_stake_earnings = dod_staked_sum - sum_delegation_events
print("total stake earnings:", total_stake_earnings)
```

### Edge Cases Noted in Code
```python
# Important notes from the example:
# 1. For new wallets, skip the first delegation event (it's the initial deposit)
# 2. Miner de-registration events are NOT captured (stake auto-returns to coldkey)
# 3. Timing issues: delegation might happen before or after daily balance snapshot
```

### Implementation for TAO Treasury

This is a **high-value feature** we should implement:

```python
# backend/app/services/analysis/earnings_calculator.py

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from app.services.data.taostats_client import get_taostats_client

async def calculate_stake_earnings(
    coldkey: str,
    start_date: datetime,
    end_date: datetime,
    include_first_delegation: bool = True,
) -> Dict:
    """
    Calculate actual stake earnings by separating passive rewards from active changes.

    Returns:
        dict with:
        - total_balance_change: Raw change in staked balance
        - net_delegations: Sum of deposits minus withdrawals
        - stake_earnings: Actual passive earnings (balance_change - delegations)
        - daily_breakdown: Optional day-by-day earnings
    """
    client = get_taostats_client()

    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())

    # Step 1: Get balance history
    balance_history = await client.get_account_history(
        address=coldkey,
        timestamp_start=start_ts,
        timestamp_end=end_ts,
    )

    # Calculate total staked balance change
    data = balance_history.get("data", [])
    total_balance_change = Decimal("0")

    for i in range(1, len(data)):
        current_staked = Decimal(data[i]["balance_staked"]) / Decimal("1e9")
        prev_staked = Decimal(data[i-1]["balance_staked"]) / Decimal("1e9")
        total_balance_change += current_staked - prev_staked

    # Step 2: Get all delegation events
    delegation_events = await client.get_all_delegation_events(coldkey=coldkey)

    # Filter to date range
    events_in_range = [
        e for e in delegation_events
        if start_ts <= _parse_timestamp(e["timestamp"]) <= end_ts
    ]

    # Sum delegations
    net_delegations = Decimal("0")
    first_delegation_skipped = False

    for event in events_in_range:
        amount = Decimal(event["amount"]) / Decimal("1e9")

        if event["action"] == "DELEGATE":
            if not include_first_delegation and not first_delegation_skipped:
                first_delegation_skipped = True
                continue
            net_delegations += amount
        else:  # UNDELEGATE
            net_delegations -= amount

    # Step 3: Calculate actual earnings
    stake_earnings = total_balance_change - net_delegations

    return {
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "total_balance_change_tao": float(total_balance_change),
        "net_delegations_tao": float(net_delegations),
        "stake_earnings_tao": float(stake_earnings),
        "delegation_count": len(events_in_range),
    }


def _parse_timestamp(ts_str: str) -> int:
    """Parse ISO timestamp to unix timestamp."""
    # Handle both formats the API might return
    if len(ts_str) > 20:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
    return int(dt.timestamp())
```

### API Endpoint

```python
# backend/app/api/v1/portfolio.py

@router.get("/earnings")
async def get_stake_earnings(
    days: int = Query(default=30, ge=1, le=365),
):
    """Get stake earnings for the configured wallet."""
    settings = get_settings()

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    earnings = await calculate_stake_earnings(
        coldkey=settings.wallet_address,
        start_date=start_date,
        end_date=end_date,
    )

    return earnings
```

---

## Example 4: `valis_24hour_change.py` - Validator Flow Analysis

### What It Does
Tracks stake flows to/from the top 25 validators over 24 hours:
- Current stake
- Stake 24 hours ago
- Count of delegation events
- Total delegated in
- Total undelegated out

### Key API Calls
```python
# Get current block
block_url = "https://api.taostats.io/api/block/v1?limit=1"
block_end = response['data'][0]['block_number']
block_start = block_end - 7200  # ~24 hours of blocks

# Get top validators
vali_url = f"https://api.taostats.io/api/validator/latest/v1?limit={number_of_valis}&order=stake_desc"

# Get delegation events in block range
delegation_url = f"https://api.taostats.io/api/delegation/v1?block_start={block_start}&block_end={block_end}"
```

### Key Pattern: Block-Based Time Ranges
```python
# Instead of timestamps, use block numbers for precision
# ~1 block every 12 seconds
# 7200 blocks = ~24 hours

block_end = current_block
block_start = block_end - 7200
```

### What We Can Learn

1. **Block-based queries**: More precise than timestamps for recent data
2. **Validator flow tracking**: See where stake is moving
3. **Aggregation pattern**: Build a map, then aggregate events into it

### Application to TAO Treasury

**Validator Flow Dashboard Widget**:
```python
# backend/app/services/analysis/validator_flow.py

async def get_validator_flows_24h(limit: int = 25) -> List[Dict]:
    """Get stake flow data for top validators over last 24 hours."""
    client = get_taostats_client()

    # Get current block
    blocks = await client._request("GET", "/api/block/v1", params={"limit": 1})
    current_block = blocks["data"][0]["block_number"]
    block_start = current_block - 7200  # ~24 hours

    # Get top validators
    validators = await client.get_validators(limit=limit)

    # Build validator map
    vali_map = {}
    for v in validators.get("data", []):
        hotkey = v["hotkey"]["ss58"]
        vali_map[hotkey] = {
            "name": v.get("name") or hotkey[:8],
            "stake_now": Decimal(v["stake"]) / Decimal("1e9"),
            "delegate_in": Decimal("0"),
            "delegate_out": Decimal("0"),
            "event_count": 0,
        }

    # Get delegation events
    page = 1
    while True:
        events = await client._request(
            "GET",
            "/api/delegation/v1",
            params={
                "block_start": block_start,
                "block_end": current_block,
                "limit": 200,
                "page": page,
            }
        )

        for event in events.get("data", []):
            hotkey = event["delegate"]["ss58"]
            if hotkey in vali_map:
                amount = Decimal(event["amount"]) / Decimal("1e9")
                vali_map[hotkey]["event_count"] += 1

                if event["action"] == "DELEGATE":
                    vali_map[hotkey]["delegate_in"] += amount
                else:
                    vali_map[hotkey]["delegate_out"] += amount

        if page >= events["pagination"]["total_pages"]:
            break
        page += 1

    # Calculate net flow and stake 24h ago
    results = []
    for hotkey, data in vali_map.items():
        net_flow = data["delegate_in"] - data["delegate_out"]
        stake_24h_ago = data["stake_now"] - net_flow

        results.append({
            "hotkey": hotkey,
            "name": data["name"],
            "stake_now": float(data["stake_now"]),
            "stake_24h_ago": float(stake_24h_ago),
            "net_flow_24h": float(net_flow),
            "delegate_in": float(data["delegate_in"]),
            "delegate_out": float(data["delegate_out"]),
            "event_count": data["event_count"],
        })

    # Sort by net flow (biggest gainers first)
    results.sort(key=lambda x: x["net_flow_24h"], reverse=True)

    return results
```

---

## Summary: What to Implement

### Immediate Value (Copy These Patterns)

| Pattern | From Example | Implementation Effort |
|---------|--------------|----------------------|
| Retry-After header handling | `apibase.py` | 30 minutes |
| Day-over-day balance tracking | `balances.py` | 2 hours |
| Block-based time ranges | `valis_24hour_change.py` | 1 hour |

### High-Value New Features

| Feature | From Example | Implementation Effort |
|---------|--------------|----------------------|
| **Stake Earnings Calculator** | `delegation_stake_earnings.py` | 4-6 hours |
| Validator Flow Analysis | `valis_24hour_change.py` | 3-4 hours |
| Balance Change Report | `balances.py` | 2-3 hours |

### Priority Order

1. **Stake Earnings Calculator** - Users want to know their actual yield, not just balance changes
2. **Retry-After handling** - Simple fix, improves reliability
3. **Validator Flow Analysis** - Helps identify trending validators
4. **Balance Change Report** - Good for portfolio history view

---

## Code to Copy

### Fix: Add Retry-After Header Support

```python
# backend/app/services/data/taostats_client.py

# In _request method, replace:
if response.status_code == 429:
    raise TaoStatsRateLimitError("Rate limit exceeded")

# With:
if response.status_code == 429:
    retry_after = int(response.headers.get('Retry-After', 60))
    logger.warning("Rate limited by API", retry_after=retry_after)
    await asyncio.sleep(retry_after)
    # The @retry decorator will handle the retry
    raise TaoStatsRateLimitError(f"Rate limit exceeded, retry after {retry_after}s")
```

### Fix: Timestamp Parsing Helper

```python
# backend/app/services/data/taostats_client.py

def parse_taostats_timestamp(timestamp: str) -> datetime:
    """Parse TaoStats timestamp which may or may not have milliseconds."""
    # From the examples: "sometimes the chain spits out a time with milliseconds"
    try:
        if len(timestamp) > 20:
            return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        # Fallback for other formats
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
```

---

This analysis shows the examples repo contains practical patterns that directly apply to TAO Treasury, especially the stake earnings calculation which is the most valuable feature we're currently missing.
