# TAO Treasury Dashboard - Deep Dive Analysis

## Current State: What's Broken

### 1. **Validator APY Data is Completely Missing**

**Root Cause**: We're syncing from the wrong TaoStats endpoint.

- **Currently using**: `/api/dtao/validator/latest/v1` - returns global validator stats WITHOUT netuid or APY
- **Should be using**: `/api/dtao/validator/yield/latest/v1` - returns per-subnet APY data

**Evidence**:
```
# Wrong endpoint returns:
hotkey: {...}, netuid: None, apy: None

# Right endpoint returns:
hotkey: {...}, netuid: 29, thirty_day_apy: 0.373, seven_day_apy: 0.366
```

**Impact**: All yield calculations are zero because there's no APY data to work with.

---

### 2. **Cost Basis is Inaccurate**

**Root Cause**: Cost basis is set on first sync, not from actual transaction history.

- When a position is first synced, we set `cost_basis_tao = current_value`
- This means positions show ~0 P&L regardless of actual performance
- Transaction history sync exists but isn't properly updating cost basis

**Evidence**:
- Root position: cost_basis = tao_value = 15.01 TAO (0 P&L)
- Many positions show suspiciously low P&L

---

### 3. **No Actionable Insights**

**What's missing**:
- `recommended_action: null` for all positions
- `eligible_subnets: 0`
- `overall_regime: neutral` always
- No alerts generated
- 30 pending recommendations but they're not shown

**Root Cause**: The eligibility gate and recommendation engines exist but:
1. Don't have valid data to work with (no APY)
2. Are not integrated into the dashboard response
3. Have overly strict thresholds

---

### 4. **Data Staleness Issues**

- `data_stale: true` frequently
- `last_sync` shows stale timestamps
- Sync process is slow and hits rate limits

---

## What TaoStats Portfolio Actually Shows (The Competition)

Based on their TypeScript SDK, TaoStats shows:
1. **Total stake value** (TAO + USD)
2. **Per-position breakdown** with:
   - Subnet name and ID
   - Alpha balance and TAO value
   - Current alpha price
   - **24h/7d/30d performance**
   - **Validator APY**
3. **Historical charts** of position values
4. **Delegation events** (stake/unstake history)

---

## Proposed Fix: Complete Overhaul

### Phase 1: Fix Data Collection (30 minutes)

1. **Switch validator sync to yield endpoint**
   - Use `/api/dtao/validator/yield/latest/v1`
   - Extract `one_day_apy`, `seven_day_apy`, `thirty_day_apy`
   - Match to positions by (hotkey, netuid)

2. **Add subnet performance data**
   - Get subnet 24h/7d/30d price changes from pool history
   - Show which subnets are trending up/down

### Phase 2: Redesign Dashboard for Actionability (1 hour)

**Current dashboard shows**: Numbers that don't mean anything

**New dashboard should show**:

#### A. Quick Health Check (Top of Page)
```
Portfolio Health: 🟢 GOOD / 🟡 NEEDS ATTENTION / 🔴 ACTION REQUIRED

Top Issue: SN85 Vidaio is down 10.6% - Consider rebalancing
Best Performer: SN19 blockmachine up 23.5% - Consider taking profit
```

#### B. Position Cards with Clear Signals
For each position, show:
- **Status icon**: 🟢🟡🔴 based on performance vs benchmark
- **Daily yield**: "+0.5 TAO/day (12% APY)"
- **7-day trend**: ↗️ +5.2% or ↘️ -3.1%
- **Action button**: "Rebalance" / "Hold" / "Review"

#### C. Opportunities Section
- Subnets with high APY you're NOT in
- Subnets where you could increase stake
- Optimal rebalancing suggestions

#### D. Risk Alerts
- Positions below cost basis (losers)
- Concentrated risk (>20% in one subnet)
- Validator issues (low vtrust, high take rate)

### Phase 3: Add Real-Time Calculations (30 minutes)

Instead of relying on stale synced data:
1. Compute yield on-the-fly from current APY + position size
2. Compute P&L from current price vs stored cost basis
3. Show live data with "as of 30 seconds ago" timestamp

---

## Alternative Approach: Simplify Radically

Instead of trying to replicate TaoStats, focus on **what TaoStats doesn't do well**:

### The "Treasury Manager" Use Case

A treasury manager cares about:
1. **Am I making money?** → Show total daily/weekly yield in TAO
2. **Where should I rebalance?** → Show underperformers vs opportunities
3. **What's my risk?** → Show concentration and drawdown metrics
4. **What changed?** → Show significant events since last check

### Proposed Minimal Dashboard

```
TAO TREASURY DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total Value: 210.75 TAO ($47,213)
Daily Yield: +1.65 TAO ($370)  |  Weekly: +11.5 TAO ($2,577)

━━━━━━━ ACTION REQUIRED ━━━━━━━

⚠️  SN85 Vidaio: -10.6% since entry, APY only 5%
    → Consider: Move to SN120 Affine (15% APY)

⚠️  22% of portfolio in SN120 - concentration risk
    → Consider: Diversify to 2-3 more subnets

━━━━━━━ TOP PERFORMERS ━━━━━━━

🟢 SN19 blockmachine: +23.5%, earning 0.3τ/day
🟢 SN62 Ridges: +10.1%, earning 0.2τ/day
🟢 SN75 Hippius: +8.2%, earning 0.2τ/day

━━━━━━━ UNDERPERFORMERS ━━━━━━━

🔴 SN85 Vidaio: -10.6%, earning 0.1τ/day
🟡 SN56 Gradients: -1.8%, earning 0.15τ/day
🟡 SN64 Chutes: -0.1%, earning 0.2τ/day

━━━━━━━ OPPORTUNITIES ━━━━━━━

High APY subnets you could enter:
• SN43: 60% APY, $1M+ liquidity
• SN73: 42% APY, good vtrust validators
• SN77: 45% APY, trending up 7d

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Last updated: 30 seconds ago
```

This is **actionable**. User sees it and knows exactly what to do.

---

## Recommended Next Steps

1. **Immediate**: Fix validator APY sync (use yield endpoint)
2. **Today**: Add position health scoring (green/yellow/red)
3. **Today**: Show opportunities (high APY subnets not staked in)
4. **Tomorrow**: Add the "Actions Required" section
5. **Later**: Historical charts and detailed analytics

The goal isn't to have the most data - it's to have **the right data presented in an actionable way**.
