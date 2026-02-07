# Flow Momentum Research: TAO Treasury Subnet Allocation Strategy

**Research Date:** February 2026
**Data Period:** February 13, 2025 - February 6, 2026 (~357 days)
**Subnets Analyzed:** 129
**Total Observations:** ~37,000

---

## Executive Summary

This research analyzed flow-based metrics for predicting Bittensor subnet alpha price movements. The key finding is that **flow momentum (the rate of change of flow) is significantly more predictive than absolute flow levels**.

### Key Discoveries

1. **Absolute flow levels have NEGATIVE predictive power** - High flow predicts mean reversion, not continuation
2. **Flow Acceleration Index (FAI) is the best predictive signal** - Comparing 1-day flow to 7-day average
3. **Optimal holding period is 14 days** - Returns peak at Day 14 after a momentum signal
4. **Quintile-based dynamic allocation outperforms all strategies tested**
5. **Win rate improves from 46.6% (equal weight) to 69.6% (momentum-based)**

---

## Part 1: What Doesn't Work - Absolute Flow Levels

### Finding: Raw Flow is a Contrarian Indicator

All absolute flow metrics showed **strongly negative** correlations with future returns:

| Metric | 7D Horizon Spread | Interpretation |
|--------|-------------------|----------------|
| flow_7d | -981% | Higher flow → WORSE returns |
| FTI (composite) | -997% | Higher FTI → WORSE returns |
| FTI_normalized | -1018% | Higher normalized FTI → WORSE returns |

**Implication:** Buying when flow is high is actually a contrarian indicator. High absolute flow predicts mean reversion, not continuation.

### Original FTI Formula (Abandoned)

```
FTI = (flow_1d * 0.5) + (flow_7d/7 * 0.3) + (flow_30d/30 * 0.2)
```

This formula provided **no improvement** over raw 7D flow and was abandoned.

---

## Part 2: What Works - Flow Momentum

### The Flow Acceleration Index (FAI)

The most predictive signal discovered:

```
FAI = flow_1d / (flow_7d / 7)
     = Today's 1-day flow / Average daily flow over past 7 days
```

**Interpretation:**
- FAI > 1.5 (top quintile): Strong BUY signal - flow is accelerating
- FAI 1.0-1.5: Neutral - slight acceleration
- FAI < 1.0: Flow is decelerating - no signal or bearish

### FAI Performance by Horizon

| Horizon | Top Quintile Spread | Monotonicity | P-Value |
|---------|---------------------|--------------|---------|
| 1D | +9.1% | +0.10 | 0.98 |
| 7D | +156.2% | +0.10 | 0.98 |
| **14D** | **+533.2%** | **+0.90** | **0.05** |
| 21D | -181.6% | -0.10 | - |
| 30D | +43.3% | +0.30 | - |

**Key Insight:** FAI predicts 14-day returns with +533% spread between top and bottom quintiles, and near-perfect monotonicity (0.90).

---

## Part 3: Alpha Window Analysis

### When Does Price Peak After a Momentum Signal?

For top quintile FAI observations:

| Day | Avg Return | Win Rate | Status |
|-----|------------|----------|--------|
| 1 | +19.68% | 42% | Building |
| 3 | +63.93% | 43% | Building |
| 7 | +312.11% | 43% | Building |
| **14** | **+863.59%** | **44%** | **PEAK** |
| 21 | +506.19% | 44% | Declining |
| 30 | +790.49% | 45% | Recovery/Noise |

### Peak Timing Distribution

When momentum is positive, peaks cluster around:
- **Average peak day:** 12.8-13.1 days
- **Median peak day:** 7 days
- Distribution is bimodal: Day 1 (short-term) and Day 30 (trend followers)

### Mean Reversion Warning

After Day 14, returns decline from +863% to +506% by Day 21. This represents significant mean reversion risk for positions held too long.

---

## Part 4: Momentum Crossover Event Study

### When FAI Crosses from Negative to Positive

**Total Events Analyzed:** 3,279

| Days After Crossover | Avg Return | Median Return | Win Rate |
|---------------------|------------|---------------|----------|
| 1D | +19.26% | -0.29% | 40% |
| 3D | +130.31% | -0.64% | 42% |
| 7D | +224.80% | -1.28% | 43% |
| 14D | +660.68% | -2.12% | 44% |
| 21D | +506.42% | -2.85% | 43% |
| 30D | +508.21% | -3.82% | 44% |

**Important:** Median returns are negative while averages are highly positive. This indicates returns are **right-skewed** - a few big winners drive the averages. Position sizing and risk management are critical.

---

## Part 5: Portfolio Allocation Strategy

### Backtest Configuration

- **Universe:** 30 viable subnets (simulating viability filter)
- **Period:** March 2025 - February 2026 (~10 months)
- **Rebalancing:** Daily

### Strategy Comparison Results

| Strategy | Total Return | Sharpe Ratio | Max Drawdown | Win Rate |
|----------|--------------|--------------|--------------|----------|
| **Quintile-based** | Top performer | 205,386 | 19.88% | **69.6%** |
| Aggressive Early | Very high | 176,134 | 25.82% | 65.5% |
| Peak at 14 | High | 11,296 | 32.06% | 61.7% |
| Linear Buildup | Moderate | 2,030 | 40.78% | 58.5% |
| Conservative | Moderate | 1,342 | 41.87% | 58.1% |
| Equal Weight | Baseline | 129 | 53.49% | 46.6% |

### Winning Strategy: Quintile-Based Dynamic Allocation

**Outperformance vs Equal Weight:**
- Max Drawdown reduced by 33.6%
- Win rate improved from 46.6% to 69.6%
- Sharpe ratio improved 1,595x

---

## Part 6: Recommended Allocation Algorithm

### Step 1: Calculate FAI for Each Subnet

```python
FAI = flow_1d / (flow_7d / 7)

# Where:
# flow_1d = today's pool_reserve - yesterday's pool_reserve
# flow_7d = today's pool_reserve - 7_days_ago pool_reserve
```

### Step 2: Determine FAI Quintile

Calculate FAI for all viable subnets, then rank into quintiles:
- Q1 (bottom 20%): FAI < 20th percentile
- Q2: 20th-40th percentile
- Q3: 40th-60th percentile
- Q4: 60th-80th percentile
- Q5 (top 20%): FAI > 80th percentile

### Step 3: Track Days in Signal

When a subnet's FAI enters Q5 (top quintile):
- Mark "in_signal = True"
- Start counting "days_in_signal"

When FAI drops below Q5:
- Mark "in_signal = False"
- Reset "days_in_signal = 0"

### Step 4: Calculate Allocation Weight

```python
def calculate_allocation(fai_quintile, days_in_signal, n_subnets):
    base_weight = 1.0 / n_subnets  # e.g., 3.33% for 30 subnets

    # Quintile multiplier
    quintile_mult = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}[fai_quintile]

    # Days in signal modifier
    if days_in_signal <= 0:
        days_mult = 0.5
    elif days_in_signal <= 7:
        days_mult = 1.0 + (days_in_signal / 7) * 0.5  # 1.0x to 1.5x
    elif days_in_signal <= 14:
        days_mult = 1.5  # Peak allocation period
    elif days_in_signal <= 21:
        days_mult = 1.5 - ((days_in_signal - 14) / 7) * 0.5  # 1.5x to 1.0x
    else:
        days_mult = 0.8  # Mean reversion zone

    raw_weight = base_weight * quintile_mult * days_mult

    # Cap at 10% max position
    return min(raw_weight, 0.10)
```

### Step 5: Normalize and Rebalance

```python
# Normalize weights to sum to 100%
total_weight = sum(all_weights)
normalized_weights = {subnet: w / total_weight for subnet, w in all_weights.items()}

# Execute rebalance via TaoStats SDK
```

---

## Part 7: Implementation Notes

### Entry Signals

1. **Primary:** FAI enters top quintile (Q5)
2. **Confirmation:** FAI > 1.5 (daily flow exceeds 1.5x weekly average)

### Position Sizing Rules

| Days in Signal | FAI Quintile | Weight Multiplier |
|----------------|--------------|-------------------|
| 0 (not in signal) | Q1-Q2 | 0.1x-0.25x |
| 0 (not in signal) | Q3-Q4 | 0.5x-0.75x |
| 1-7 | Q5 | 2.5x-3.75x |
| 7-14 | Q5 | 3.75x (PEAK) |
| 14-21 | Q5 | 3.75x-2.5x |
| 21+ | Any | 2.0x (reduce) |

### Exit Signals

1. FAI drops below Q5 (top quintile)
2. Days in signal exceeds 21 (mean reversion zone)
3. FAI drops below 1.0 (flow decelerating)

### Risk Management

1. **Max single position:** 10% of portfolio
2. **Min position:** 0.5% (maintain diversification)
3. **Rebalancing frequency:** Daily recommended
4. **Win rate expectation:** ~70% with this strategy

### Concentration Guidelines

Based on backtest allocation dynamics:
- Top 5 positions: ~50-55% of portfolio
- Top 10 positions: ~75% of portfolio
- Remaining positions: ~25% spread across 20 subnets

---

## Part 8: Caveats and Limitations

### Statistical Significance

- P-values hover around 0.05 (borderline significant)
- Sample size: ~37,000 observations across 129 subnets
- dTAO launched February 2025 - limited historical data (~12 months)

### Return Distribution

- Returns are **heavily right-skewed**
- Average returns driven by outlier winners
- Median returns often negative while averages positive
- Position sizing critical for surviving losing streaks

### Market Regime Risk

- Backtest period was generally bullish for dTAO
- Strategy may underperform in sustained bear markets
- Mean reversion effects may be stronger in downtrends

### Survivorship Bias

- Dead/deregistered subnets not fully captured
- Successful subnets overrepresented in later data

---

## Part 9: Future Research

### Potential Improvements

1. **Add flow_7d_momentum to FAI:** Combine acceleration with momentum
2. **Volume-weight the signal:** Larger pool reserves = stronger signal
3. **Cross-subnet momentum:** When multiple subnets signal together
4. **Market regime detection:** Adjust strategy for bull/bear conditions

### Integration with Viability Scoring

FAI should be one component of overall viability score alongside:
- Pool TAO reserve (liquidity)
- Emission share (yield)
- Subnet age (stability)
- Holder count (adoption)
- Validator APY (staking returns)

---

## Part 10: Quick Reference

### The Algorithm in 5 Steps

1. **Filter:** Start with ~30 viable subnets from viability scoring
2. **Calculate FAI:** `flow_1d / (flow_7d / 7)` for each subnet
3. **Rank:** Determine FAI quintile (1-5) for each subnet
4. **Weight:** Apply quintile + days-in-signal multipliers
5. **Rebalance:** Execute daily via TaoStats SDK

### Key Numbers to Remember

| Metric | Value |
|--------|-------|
| Optimal hold period | 14 days |
| Peak return timing | Day 12-14 |
| Mean reversion starts | Day 14-21 |
| Top quintile FAI threshold | ~1.5x weekly avg |
| Max single position | 10% |
| Expected win rate | ~70% |
| Top 5 concentration | ~50-55% |

### Files Created

- `/backend/scripts/fti_backtest.py` - Initial FTI analysis
- `/backend/scripts/flow_backtest_framework.py` - Comprehensive metric comparison
- `/backend/scripts/momentum_deep_dive.py` - Momentum and timing analysis
- `/backend/scripts/portfolio_momentum_backtest.py` - Portfolio allocation testing

---

## Part 11: CRITICAL UPDATE - Validated Backtest Results (February 2026)

### ⚠️ IMPORTANT CORRECTION

The findings in Parts 1-10 above contain **significant methodological flaws** that invalidated the original research conclusions. This section documents the corrected methodology and actual results.

---

### AMM Model Change - November 5, 2025

**Critical Context:** Bittensor fundamentally changed their AMM pricing model on **November 5, 2025**:

- **Before Nov 5:** Pricing-based model
- **After Nov 5:** Flow-based model (dTAO)

**Implication:** All data prior to November 5, 2025 is irrelevant for flow-based strategy analysis. The original research spanning February 2025 - November 2025 was analyzing a completely different market mechanism.

**Corrected Analysis Period:** November 1, 2025 - February 6, 2026 (~98 days)

---

### Methodological Flaws Discovered

#### 1. Look-Ahead Bias (CRITICAL)

The original backtests used **current flow data to make historical allocation decisions**. This created impossible results where the strategy appeared to predict future price movements perfectly.

**Example of the error:**
```python
# WRONG: Using current flow values for historical decisions
flow_7d = current_pool_reserve - pool_reserve_7_days_ago  # Look-ahead!
```

**Correct approach:** Calculate flow using only data available at decision time.

#### 2. Age Calculation Bug (CRITICAL)

The original age calculation used the first record in processed data (Nov 1) as the registration date instead of actual subnet registration dates.

**Result:** ZERO subnets passed the 60-day age filter for most of the test period, causing impossible returns (1,247,572% weekly return in some tests).

**Fix:** Fetch actual registration dates from `/subnet/latest/v1` API endpoint:
```python
def fetch_subnet_metadata():
    result = taostats_request("/subnet/latest/v1", {"limit": 200})
    metadata = {}
    for s in result["data"]:
        netuid = s.get("netuid")
        reg_ts = s.get("registration_timestamp", "")
        reg_date = datetime.fromisoformat(reg_ts.replace("Z", "+00:00")).date()
        metadata[netuid] = {"registration_date": reg_date}
    return metadata
```

#### 3. Incomplete Viability Implementation

Original backtests only filtered on `reserve > 100 TAO`, ignoring:
- Hard failure gates (age, reserve minimums, outflow thresholds)
- 4-factor viability scoring
- Top percentile filtering

---

### Corrected Backtest Methodology

#### Data Sources

| Data Type | API Endpoint | Key Fields |
|-----------|--------------|------------|
| Pool History | `/dtao/pool/history/v1` | tao_in, alpha_in, timestamp |
| Subnet Metadata | `/subnet/latest/v1` | registration_timestamp, netuid, name |
| Emission Data | `/subnet/history/v1` | projected_emission (limited availability) |

#### Viability Hard Failures

A subnet is immediately excluded if ANY of these conditions are met:

| Gate | Threshold | Rationale |
|------|-----------|-----------|
| Age | < 60 days | New subnets too volatile |
| TAO Reserve | < 500 TAO | Insufficient liquidity |
| 7D Outflow | > -50% | Catastrophic capital flight |
| Max Drawdown | > 50% | Excessive volatility/risk |

#### Viability Scoring (4 Factors)

For subnets passing hard failures, score using:

| Factor | Weight | Metric |
|--------|--------|--------|
| FAI (Flow Momentum) | 35% | flow_1d / (flow_7d / 7) |
| TAO Reserve | 25% | Current pool liquidity |
| Emission Share | 25% | % of network emissions |
| Stability | 15% | 1 - (volatility / max_volatility) |

#### Trading Methodology

**FAI Quintile Multipliers:**
| Quintile | Multiplier | Interpretation |
|----------|------------|----------------|
| Q1 (bottom 20%) | 0.2x | Strong negative momentum |
| Q2 | 0.5x | Weak negative momentum |
| Q3 | 1.0x | Neutral |
| Q4 | 1.5x | Positive momentum |
| Q5 (top 20%) | 2.5x | Strong positive momentum |

**Days-in-Signal Lifecycle:**
| Phase | Days | Multiplier | Description |
|-------|------|------------|-------------|
| Ramp Up | 1-7 | 1.0x → 1.5x | Building position |
| Peak | 7-14 | 1.5x | Maximum allocation |
| Ramp Down | 14-21 | 1.5x → 1.0x | Reducing exposure |
| Exit Zone | 21+ | 0.8x | Mean reversion risk |

---

### Validated Backtest Results

**Test Period:** November 1, 2025 - February 6, 2026 (98 days / ~14 weeks)
**Universe:** Top 50% of viable subnets by viability score
**Comparison:** FAI+Lifecycle strategy vs Equal Weight baseline

#### Daily Rebalancing Results

| Strategy | Total Return | Sharpe Ratio | Max Drawdown | Avg Subnets |
|----------|--------------|--------------|--------------|-------------|
| FAI+Lifecycle | +30.1% | 4.34 | 5.4% | 52.1 |
| Equal Weight | +24.6% | 5.69 | 4.0% | 52.1 |

#### 3-Day Rebalancing Results

| Strategy | Total Return | Sharpe Ratio | Max Drawdown | Avg Subnets |
|----------|--------------|--------------|--------------|-------------|
| FAI+Lifecycle | +29.8% | 5.30 | 4.9% | 52.5 |
| Equal Weight | +27.1% | 6.53 | 3.4% | 52.5 |

#### Weekly Rebalancing Results

| Strategy | Total Return | Sharpe Ratio | Max Drawdown | Avg Subnets |
|----------|--------------|--------------|--------------|-------------|
| FAI+Lifecycle | +26.2% | 5.13 | 4.1% | 51.8 |
| **Equal Weight** | **+32.5%** | **7.78** | **1.3%** | 51.8 |

---

### Key Finding: Equal Weight OUTPERFORMS FAI Strategy

**On a risk-adjusted basis, Equal Weight allocation with weekly rebalancing is the optimal strategy.**

| Metric | FAI+Lifecycle Best | Equal Weight Best | Winner |
|--------|-------------------|-------------------|--------|
| Highest Return | 30.1% (Daily) | 32.5% (Weekly) | **Equal Weight** |
| Best Sharpe | 5.30 (3-Day) | 7.78 (Weekly) | **Equal Weight** |
| Lowest Drawdown | 4.1% (Weekly) | 1.3% (Weekly) | **Equal Weight** |

**Why Equal Weight Outperforms:**

1. **Reduced transaction costs:** Weekly rebalancing minimizes trading friction
2. **Diversification benefit:** Equal weighting avoids concentration risk
3. **Mean reversion:** FAI momentum signals may overshoot, causing reversals
4. **Noise in short-term flow:** Daily flow data is noisy; weekly averaging smooths it

---

### Realistic FAI Signal Strength

The original research claimed +533% Q5 vs Q1 spread at 14-day horizon. **Actual post-AMM results:**

| Horizon | Q5 vs Q1 Spread | Notes |
|---------|-----------------|-------|
| 14D | +0.28% | Minimal difference |
| 7D | +0.15% | Noise level |

**Conclusion:** FAI provides marginal signal improvement, not the dramatic outperformance originally claimed.

---

### Revised Recommendations

#### Strategy 1: Simple Equal Weight (RECOMMENDED)

```python
def allocate_equal_weight(viable_subnets):
    """Simple, effective allocation."""
    n = len(viable_subnets)
    return {subnet: 1.0 / n for subnet in viable_subnets}
```

- **Rebalancing:** Weekly
- **Expected Sharpe:** ~7-8
- **Expected Drawdown:** ~1-3%

#### Strategy 2: FAI-Tilted (Optional Enhancement)

If using FAI, apply modest tilts rather than aggressive multipliers:

```python
def allocate_fai_tilted(viable_subnets, fai_scores):
    """Subtle FAI tilt on top of equal weight."""
    base = 1.0 / len(viable_subnets)

    quintile_tilt = {
        1: 0.8,   # Slight underweight
        2: 0.9,
        3: 1.0,   # Equal weight
        4: 1.1,
        5: 1.2    # Slight overweight
    }

    weights = {}
    for subnet in viable_subnets:
        q = get_quintile(fai_scores[subnet])
        weights[subnet] = base * quintile_tilt[q]

    # Normalize
    total = sum(weights.values())
    return {s: w/total for s, w in weights.items()}
```

---

### Files Created for Validated Backtesting

| File | Purpose |
|------|---------|
| `/backend/scripts/full_viability_backtest.py` | Complete viability + FAI backtest with corrected methodology |
| `/backend/scripts/proper_fai_backtest.py` | Simple FAI quintile backtest for validation |
| `/backend/scripts/taostats_api_explore.py` | API exploration and endpoint discovery |

---

### Lessons Learned

1. **Always use actual registration dates** from `/subnet/latest/v1`, not first data appearance
2. **Post-AMM data only** (Nov 5, 2025+) is relevant for flow-based analysis
3. **Look-ahead bias** is easy to introduce; validate that decisions use only past data
4. **Simple strategies often win** - equal weight with proper viability filtering is robust
5. **Risk-adjusted returns matter** - Sharpe ratio and drawdown are more important than raw returns
6. **Weekly rebalancing** reduces noise and transaction costs

---

### Next Steps: Interactive Backtesting Tool

Based on these findings, an interactive backtesting page should be built with:

1. **Variable testing:** Adjust weights, thresholds, top N subnets
2. **Date range selection:** Start date must be >= Nov 5, 2025
3. **Proper age calculation:** Use registration_date from subnet metadata
4. **Multiple strategies:** Compare equal weight vs FAI-weighted
5. **Optimization mode:** Test ranges of parameters to find optimal configuration
6. **Clear metrics:** Show Sharpe, returns, drawdown, and subnet count

---

*Section added February 2026 after discovery of methodological flaws in original research*

---

*Document generated from TAO Treasury flow momentum research, February 2026*
