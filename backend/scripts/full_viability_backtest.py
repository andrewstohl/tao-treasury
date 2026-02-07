#!/usr/bin/env python3
"""
Full Viability + FAI Trading Backtest

Specification:
1. Hard Failure Gates: Age>=60d, Reserve>=500 TAO, Outflow>-50%, DD<=50%
2. Viability Scoring: FAI(35%), Reserve(25%), Emission(25%), Stability(15%)
3. Trading: Quintile weights + Days-in-signal lifecycle
4. Test rebalancing: Daily, 3-Day, Weekly
"""

import os
import time
import json
from datetime import datetime, timedelta, date
from collections import defaultdict
import statistics
import requests

# Configuration
TAOSTATS_API_KEY = os.environ.get("TAOSTATS_API_KEY", "tao-dab24c32-ecc6-434b-ad56-980192efd160:27bd8dac")
TAOSTATS_BASE_URL = "https://api.taostats.io/api"
START_DATE = date(2025, 11, 1)  # Post-AMM change

# Hard Failure Thresholds
HARD_FAILURES = {
    "min_age_days": 60,
    "min_reserve_tao": 500,
    "max_outflow_ratio": 0.50,  # 7d outflow < -50% of reserve
    "max_drawdown": 0.50,       # 30d drawdown <= 50%
}

# Viability Scoring Weights
VIABILITY_WEIGHTS = {
    "fai": 0.35,
    "reserve": 0.25,
    "emission": 0.25,
    "stability": 0.15,
}
VIABILITY_CUTOFF = 50  # Score >= 50 = VIABLE

# Trading Configuration
QUINTILE_MULTIPLIERS = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}
MAX_POSITION = 0.10  # 10% max


def taostats_request(endpoint, params=None, retries=3):
    """Make authenticated request to TaoStats API."""
    url = f"{TAOSTATS_BASE_URL}{endpoint}"
    headers = {"Authorization": TAOSTATS_API_KEY, "accept": "application/json"}

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"API Error: {e}")
    return None


def fetch_pool_history():
    """Fetch all pool history from TaoStats."""
    print("Fetching pool history...")
    all_data = []
    page = 1

    while True:
        result = taostats_request("/dtao/pool/history/v1", {
            "limit": 200, "page": page, "order": "timestamp_asc"
        })
        if not result or not result.get("data"):
            break

        all_data.extend(result["data"])
        pagination = result.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)

        if page % 50 == 0:
            print(f"  Page {page}/{total_pages} ({len(all_data)} records)")

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.2)

    print(f"  Fetched {len(all_data)} pool records")
    return all_data


def fetch_subnet_metadata():
    """Fetch subnet metadata including registration dates."""
    print("Fetching subnet metadata...")
    result = taostats_request("/subnet/latest/v1", {"limit": 200})
    if not result or not result.get("data"):
        return {}

    metadata = {}
    for s in result["data"]:
        netuid = s.get("netuid")
        if netuid is not None:
            reg_ts = s.get("registration_timestamp", "")
            reg_date = None
            if reg_ts:
                try:
                    reg_date = datetime.fromisoformat(reg_ts.replace("Z", "+00:00")).date()
                except:
                    pass
            metadata[netuid] = {
                "registration_date": reg_date,
                "name": s.get("name", ""),
            }

    print(f"  Found metadata for {len(metadata)} subnets")
    return metadata


def fetch_subnet_history(metadata):
    """Fetch subnet history for emission data."""
    print("Fetching subnet history (emissions)...")
    all_data = defaultdict(list)

    netuids = list(metadata.keys())
    print(f"  Fetching for {len(netuids)} subnets")

    # Fetch history for each subnet (limited to save time)
    for i, netuid in enumerate(netuids):
        if i % 20 == 0:
            print(f"  Fetching subnet {i+1}/{len(netuids)}...")

        result = taostats_request("/subnet/history/v1", {
            "netuid": netuid, "limit": 200, "order": "timestamp_desc"
        })
        if result and result.get("data"):
            for rec in result["data"]:
                ts = rec.get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                        if dt >= START_DATE:
                            all_data[netuid].append({
                                "date": dt,
                                "emission": float(rec.get("projected_emission", 0) or 0),
                            })
                    except:
                        pass
        time.sleep(0.1)

    print(f"  Fetched emission data for {len(all_data)} subnets")
    return all_data


def process_data(pool_data, emission_data):
    """Process raw data into daily snapshots."""
    print(f"\nProcessing data (from {START_DATE})...")

    by_subnet = defaultdict(dict)

    for record in pool_data:
        netuid = record.get("netuid")
        ts = record.get("timestamp", "")
        if not netuid or not ts:
            continue

        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            d = dt.date()
        except:
            continue

        if d < START_DATE:
            continue

        # Parse values
        tao_raw = float(record.get("total_tao", 0) or 0)
        tao = tao_raw / 1e9 if tao_raw > 1e12 else tao_raw
        price = float(record.get("price", 0) or 0)

        # Get emission for this date/subnet
        emission = 0
        if netuid in emission_data:
            for e in emission_data[netuid]:
                if e["date"] == d:
                    emission = e["emission"]
                    break

        if d not in by_subnet[netuid] or dt > by_subnet[netuid][d].get("dt", dt):
            by_subnet[netuid][d] = {
                "dt": dt,
                "reserve": tao,
                "price": price,
                "emission": emission,
            }

    # Convert to sorted lists
    processed = {}
    for netuid, dates in by_subnet.items():
        sorted_dates = sorted(dates.keys())
        processed[netuid] = [
            {"date": d, **dates[d]} for d in sorted_dates
        ]

    all_dates = set()
    for netuid, history in processed.items():
        for r in history:
            all_dates.add(r["date"])

    all_dates = sorted(all_dates)
    print(f"  {len(processed)} subnets, {len(all_dates)} days")
    if all_dates:
        print(f"  Date range: {all_dates[0]} to {all_dates[-1]}")

    return processed, all_dates


def get_record(history, target_date):
    """Get record for a specific date."""
    for r in history:
        if r["date"] == target_date:
            return r
    return None


def compute_flow(history, target_date, days):
    """Compute flow from reserve changes."""
    current = get_record(history, target_date)
    past = get_record(history, target_date - timedelta(days=days))
    if current and past:
        return current["reserve"] - past["reserve"]
    return None


def compute_fai(history, target_date):
    """Compute Flow Acceleration Index."""
    flow_1d = compute_flow(history, target_date, 1)
    flow_7d = compute_flow(history, target_date, 7)
    if flow_1d is None or flow_7d is None:
        return None
    if flow_7d == 0:
        return 1.0
    avg_daily = flow_7d / 7
    if avg_daily == 0:
        return 1.0
    return flow_1d / avg_daily


def compute_drawdown(history, end_date, days=30):
    """Compute max drawdown over period."""
    start = end_date - timedelta(days=days)
    prices = [r["price"] for r in history if start <= r["date"] <= end_date and r["price"] > 0]
    if len(prices) < 2:
        return 0
    peak = prices[0]
    max_dd = 0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return max_dd


def compute_age(registration_date, target_date):
    """Compute age in days from registration date."""
    if not registration_date:
        return 0
    return (target_date - registration_date).days


def percentile_rank(values, target, higher_is_better=True):
    """Compute percentile rank (0-100)."""
    if len(values) <= 1:
        return 50.0
    sorted_vals = sorted(values, reverse=not higher_is_better)
    rank = sum(1 for v in sorted_vals if (v < target if higher_is_better else v > target))
    return (rank / (len(sorted_vals) - 1)) * 100


def get_quintile(value, all_values):
    """Get quintile (1-5) for a value."""
    if len(all_values) < 5:
        return 3
    sv = sorted(all_values)
    n = len(sv)
    thresholds = [sv[int(n * q)] for q in [0.2, 0.4, 0.6, 0.8]]
    if value <= thresholds[0]: return 1
    if value <= thresholds[1]: return 2
    if value <= thresholds[2]: return 3
    if value <= thresholds[3]: return 4
    return 5


def days_in_signal_multiplier(days):
    """Calculate multiplier based on days in Q5 signal."""
    if days <= 0:
        return 0.5
    elif days <= 7:
        return 1.0 + (days / 7) * 0.5  # 1.0 → 1.5
    elif days <= 14:
        return 1.5  # Peak
    elif days <= 21:
        return 1.5 - ((days - 14) / 7) * 0.5  # 1.5 → 1.0
    else:
        return 0.8  # Mean reversion zone


def run_backtest(data, all_dates, rebalance_freq, subnet_metadata):
    """Run backtest with specified rebalancing frequency."""

    # Build rebalance schedule - start after 7 days for flow calculations
    if rebalance_freq == 1:
        rebal_dates = all_dates[7:]
    else:
        rebal_dates = all_dates[7::rebalance_freq]

    if len(rebal_dates) < 3:
        return None

    # Track days in signal for each subnet
    signal_state = defaultdict(lambda: {"in_signal": False, "days": 0, "entry_date": None})

    # Portfolio tracking
    portfolio_values = [1.0]  # Start with $1
    daily_returns = []
    viable_counts = []  # Track number of viable subnets per period

    for i, rebal_date in enumerate(rebal_dates[:-1]):
        next_date = rebal_dates[i + 1]

        # Step 1: Apply hard failure gates
        candidates = []
        for netuid, history in data.items():
            record = get_record(history, rebal_date)
            if not record or record["price"] <= 0:
                continue

            # Use registration date for true age
            reg_date = subnet_metadata.get(netuid, {}).get("registration_date")
            age = compute_age(reg_date, rebal_date)
            if age < HARD_FAILURES["min_age_days"]:
                continue

            reserve = record["reserve"]
            if reserve < HARD_FAILURES["min_reserve_tao"]:
                continue

            flow_7d = compute_flow(history, rebal_date, 7)
            if flow_7d is not None and reserve > 0:
                if flow_7d / reserve < -HARD_FAILURES["max_outflow_ratio"]:
                    continue

            dd = compute_drawdown(history, rebal_date)
            if dd > HARD_FAILURES["max_drawdown"]:
                continue

            fai = compute_fai(history, rebal_date)
            if fai is None:
                continue

            candidates.append({
                "netuid": netuid,
                "history": history,
                "record": record,
                "fai": fai,
                "reserve": reserve,
                "emission": record.get("emission", 0),
                "dd": dd,
            })

        if len(candidates) < 5:
            portfolio_values.append(portfolio_values[-1])
            continue

        # Step 2: Calculate viability scores
        all_fai = [c["fai"] for c in candidates]
        all_reserve = [c["reserve"] for c in candidates]
        all_emission = [c["emission"] for c in candidates]
        all_dd = [c["dd"] for c in candidates]

        for c in candidates:
            fai_pct = percentile_rank(all_fai, c["fai"], higher_is_better=True)
            res_pct = percentile_rank(all_reserve, c["reserve"], higher_is_better=True)
            em_pct = percentile_rank(all_emission, c["emission"], higher_is_better=True)
            stab_pct = percentile_rank(all_dd, c["dd"], higher_is_better=False)

            c["viability"] = (
                fai_pct * VIABILITY_WEIGHTS["fai"] +
                res_pct * VIABILITY_WEIGHTS["reserve"] +
                em_pct * VIABILITY_WEIGHTS["emission"] +
                stab_pct * VIABILITY_WEIGHTS["stability"]
            )

        # Step 3: Filter to viable subnets
        viable = [c for c in candidates if c["viability"] >= VIABILITY_CUTOFF]
        viable_counts.append(len(viable))
        if len(viable) < 3:
            portfolio_values.append(portfolio_values[-1])
            continue

        # Step 4: Calculate FAI quintiles within viable population
        viable_fai = [c["fai"] for c in viable]
        for c in viable:
            c["quintile"] = get_quintile(c["fai"], viable_fai)

            # Update signal state
            state = signal_state[c["netuid"]]
            if c["quintile"] == 5:
                if not state["in_signal"]:
                    state["in_signal"] = True
                    state["entry_date"] = rebal_date
                    state["days"] = 0
                else:
                    state["days"] = (rebal_date - state["entry_date"]).days
            else:
                state["in_signal"] = False
                state["days"] = 0
                state["entry_date"] = None

            c["days_in_signal"] = state["days"] if state["in_signal"] else 0

        # Step 5: Calculate weights
        n_viable = len(viable)
        base_weight = 1.0 / n_viable

        for c in viable:
            q_mult = QUINTILE_MULTIPLIERS[c["quintile"]]
            d_mult = days_in_signal_multiplier(c["days_in_signal"])
            raw_weight = base_weight * q_mult * d_mult
            c["weight"] = min(raw_weight, MAX_POSITION)

        # Normalize weights
        total_weight = sum(c["weight"] for c in viable)
        for c in viable:
            c["weight"] = c["weight"] / total_weight

        # Step 6: Calculate returns to next rebalance
        period_return = 0
        for c in viable:
            next_record = get_record(c["history"], next_date)
            if next_record and c["record"]["price"] > 0:
                subnet_return = (next_record["price"] - c["record"]["price"]) / c["record"]["price"]
                period_return += subnet_return * c["weight"]

        new_value = portfolio_values[-1] * (1 + period_return)
        portfolio_values.append(new_value)
        daily_returns.append(period_return)

    if not daily_returns:
        return None

    # Calculate metrics
    total_return = (portfolio_values[-1] / portfolio_values[0]) - 1

    # Drawdown
    peak = portfolio_values[0]
    max_dd = 0
    for v in portfolio_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        max_dd = max(max_dd, dd)

    # Sharpe (annualized)
    if len(daily_returns) > 1:
        mean_ret = statistics.mean(daily_returns)
        std_ret = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.01
        periods_per_year = 365 / rebalance_freq
        sharpe = (mean_ret / std_ret) * (periods_per_year ** 0.5) if std_ret > 0 else 0
    else:
        sharpe = 0

    win_rate = sum(1 for r in daily_returns if r > 0) / len(daily_returns) if daily_returns else 0

    avg_viable = statistics.mean(viable_counts) if viable_counts else 0

    return {
        "rebalance_freq": rebalance_freq,
        "periods": len(daily_returns),
        "total_return": total_return,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "final_value": portfolio_values[-1],
        "avg_viable_subnets": avg_viable,
    }


def run_equal_weight_baseline(data, all_dates, rebalance_freq, subnet_metadata):
    """Run equal-weight baseline on same viable population."""

    if rebalance_freq == 1:
        rebal_dates = all_dates[7:]
    else:
        rebal_dates = all_dates[7::rebalance_freq]

    if len(rebal_dates) < 3:
        return None

    portfolio_values = [1.0]
    daily_returns = []
    viable_counts = []

    for i, rebal_date in enumerate(rebal_dates[:-1]):
        next_date = rebal_dates[i + 1]

        # Same filtering as main backtest
        candidates = []
        for netuid, history in data.items():
            record = get_record(history, rebal_date)
            if not record or record["price"] <= 0:
                continue

            # Use registration date for true age
            reg_date = subnet_metadata.get(netuid, {}).get("registration_date")
            age = compute_age(reg_date, rebal_date)
            if age < HARD_FAILURES["min_age_days"]:
                continue

            reserve = record["reserve"]
            if reserve < HARD_FAILURES["min_reserve_tao"]:
                continue

            flow_7d = compute_flow(history, rebal_date, 7)
            if flow_7d is not None and reserve > 0:
                if flow_7d / reserve < -HARD_FAILURES["max_outflow_ratio"]:
                    continue

            dd = compute_drawdown(history, rebal_date)
            if dd > HARD_FAILURES["max_drawdown"]:
                continue

            fai = compute_fai(history, rebal_date)
            if fai is None:
                continue

            candidates.append({
                "netuid": netuid,
                "history": history,
                "record": record,
                "fai": fai,
                "reserve": reserve,
                "emission": record.get("emission", 0),
                "dd": dd,
            })

        if len(candidates) < 5:
            portfolio_values.append(portfolio_values[-1])
            continue

        # Viability scoring
        all_fai = [c["fai"] for c in candidates]
        all_reserve = [c["reserve"] for c in candidates]
        all_emission = [c["emission"] for c in candidates]
        all_dd = [c["dd"] for c in candidates]

        for c in candidates:
            fai_pct = percentile_rank(all_fai, c["fai"], higher_is_better=True)
            res_pct = percentile_rank(all_reserve, c["reserve"], higher_is_better=True)
            em_pct = percentile_rank(all_emission, c["emission"], higher_is_better=True)
            stab_pct = percentile_rank(all_dd, c["dd"], higher_is_better=False)

            c["viability"] = (
                fai_pct * VIABILITY_WEIGHTS["fai"] +
                res_pct * VIABILITY_WEIGHTS["reserve"] +
                em_pct * VIABILITY_WEIGHTS["emission"] +
                stab_pct * VIABILITY_WEIGHTS["stability"]
            )

        viable = [c for c in candidates if c["viability"] >= VIABILITY_CUTOFF]
        viable_counts.append(len(viable))
        if len(viable) < 3:
            portfolio_values.append(portfolio_values[-1])
            continue

        # Equal weight
        weight = 1.0 / len(viable)

        period_return = 0
        for c in viable:
            next_record = get_record(c["history"], next_date)
            if next_record and c["record"]["price"] > 0:
                subnet_return = (next_record["price"] - c["record"]["price"]) / c["record"]["price"]
                period_return += subnet_return * weight

        new_value = portfolio_values[-1] * (1 + period_return)
        portfolio_values.append(new_value)
        daily_returns.append(period_return)

    if not daily_returns:
        return None

    total_return = (portfolio_values[-1] / portfolio_values[0]) - 1

    peak = portfolio_values[0]
    max_dd = 0
    for v in portfolio_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        max_dd = max(max_dd, dd)

    if len(daily_returns) > 1:
        mean_ret = statistics.mean(daily_returns)
        std_ret = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.01
        periods_per_year = 365 / rebalance_freq
        sharpe = (mean_ret / std_ret) * (periods_per_year ** 0.5) if std_ret > 0 else 0
    else:
        sharpe = 0

    win_rate = sum(1 for r in daily_returns if r > 0) / len(daily_returns) if daily_returns else 0

    avg_viable = statistics.mean(viable_counts) if viable_counts else 0

    return {
        "rebalance_freq": rebalance_freq,
        "periods": len(daily_returns),
        "total_return": total_return,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "final_value": portfolio_values[-1],
        "avg_viable_subnets": avg_viable,
    }


def main():
    print("=" * 80)
    print("FULL VIABILITY + FAI TRADING BACKTEST")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Start Date: {START_DATE} (post-AMM change)")
    print(f"  Hard Failures: {HARD_FAILURES}")
    print(f"  Viability Weights: {VIABILITY_WEIGHTS}")
    print(f"  Viability Cutoff: >= {VIABILITY_CUTOFF}")
    print(f"  Quintile Multipliers: {QUINTILE_MULTIPLIERS}")
    print(f"  Max Position: {MAX_POSITION:.0%}")

    # Fetch data
    print()
    pool_data = fetch_pool_history()
    subnet_metadata = fetch_subnet_metadata()
    emission_data = fetch_subnet_history(subnet_metadata)

    if not pool_data:
        print("ERROR: Could not fetch pool data")
        return

    if not subnet_metadata:
        print("ERROR: Could not fetch subnet metadata")
        return

    # Process data
    data, all_dates = process_data(pool_data, emission_data)

    if not data or len(all_dates) < 70:
        print("ERROR: Insufficient data")
        return

    # Run backtests
    print()
    print("=" * 80)
    print("RUNNING BACKTESTS")
    print("=" * 80)

    results = []
    baselines = []

    for freq in [1, 3, 7]:
        freq_name = {1: "Daily", 3: "3-Day", 7: "Weekly"}[freq]
        print(f"\n{freq_name} Rebalancing...")

        result = run_backtest(data, all_dates, freq, subnet_metadata)
        baseline = run_equal_weight_baseline(data, all_dates, freq, subnet_metadata)

        if result:
            results.append(result)
            print(f"  FAI Strategy: Return={result['total_return']:.1%}, "
                  f"Sharpe={result['sharpe']:.2f}, DD={result['max_drawdown']:.1%}")

        if baseline:
            baselines.append(baseline)
            print(f"  Equal Weight: Return={baseline['total_return']:.1%}, "
                  f"Sharpe={baseline['sharpe']:.2f}, DD={baseline['max_drawdown']:.1%}")

    # Summary
    print()
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Frequency':<12} {'Strategy':<15} {'Return':>10} {'Sharpe':>8} {'MaxDD':>8} {'WinRate':>8} {'AvgSNs':>8}")
    print("-" * 80)

    for r in results:
        freq_name = {1: "Daily", 3: "3-Day", 7: "Weekly"}[r["rebalance_freq"]]
        print(f"{freq_name:<12} {'FAI+Lifecycle':<15} {r['total_return']:>9.1%} "
              f"{r['sharpe']:>8.2f} {r['max_drawdown']:>7.1%} {r['win_rate']:>7.1%} "
              f"{r['avg_viable_subnets']:>7.1f}")

    print("-" * 80)

    for b in baselines:
        freq_name = {1: "Daily", 3: "3-Day", 7: "Weekly"}[b["rebalance_freq"]]
        print(f"{freq_name:<12} {'Equal Weight':<15} {b['total_return']:>9.1%} "
              f"{b['sharpe']:>8.2f} {b['max_drawdown']:>7.1%} {b['win_rate']:>7.1%} "
              f"{b['avg_viable_subnets']:>7.1f}")

    # Analysis
    print()
    print("=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    for i, r in enumerate(results):
        if i < len(baselines):
            b = baselines[i]
            freq_name = {1: "Daily", 3: "3-Day", 7: "Weekly"}[r["rebalance_freq"]]
            outperformance = r["total_return"] - b["total_return"]
            sharpe_diff = r["sharpe"] - b["sharpe"]
            dd_improvement = b["max_drawdown"] - r["max_drawdown"]

            print(f"\n{freq_name}:")
            print(f"  Return Outperformance: {outperformance:+.1%}")
            print(f"  Sharpe Improvement: {sharpe_diff:+.2f}")
            print(f"  Drawdown Reduction: {dd_improvement:+.1%}")

            if outperformance > 0 and sharpe_diff > 0:
                print(f"  -> FAI strategy OUTPERFORMS equal weight")
            elif outperformance < 0 and sharpe_diff < 0:
                print(f"  -> FAI strategy UNDERPERFORMS equal weight")
            else:
                print(f"  -> Mixed results")

    # Best strategy
    if results:
        best = max(results, key=lambda x: x["sharpe"])
        freq_name = {1: "Daily", 3: "3-Day", 7: "Weekly"}[best["rebalance_freq"]]
        print()
        print("=" * 80)
        print(f"RECOMMENDED: {freq_name} Rebalancing")
        print(f"  Sharpe: {best['sharpe']:.2f}")
        print(f"  Return: {best['total_return']:.1%}")
        print(f"  Max Drawdown: {best['max_drawdown']:.1%}")
        print("=" * 80)


if __name__ == "__main__":
    main()
