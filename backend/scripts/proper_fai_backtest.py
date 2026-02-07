#!/usr/bin/env python3
"""
PROPER FAI Backtest using TaoStats Historical Data

This script:
1. Fetches historical pool data from TaoStats API
2. Computes actual historical flow from the data
3. Runs a proper backtest with NO look-ahead bias
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
import requests

# TaoStats API configuration
TAOSTATS_API_KEY = os.environ.get("TAOSTATS_API_KEY", "tao-dab24c32-ecc6-434b-ad56-980192efd160:27bd8dac")
TAOSTATS_BASE_URL = "https://api.taostats.io/api"

HOLDING_PERIOD_DAYS = 14
FAI_QUINTILE_MULTIPLIERS = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}


def taostats_request(endpoint, params=None, retries=3):
    """Make authenticated request to TaoStats API with retry logic."""
    url = f"{TAOSTATS_BASE_URL}{endpoint}"
    headers = {
        "Authorization": TAOSTATS_API_KEY,
        "accept": "application/json"
    }

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 429:
                wait_time = 5 * (attempt + 1)
                print(f"  Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                print(f"  Request failed, retrying... ({e})")
                time.sleep(2)
            else:
                print(f"API Error: {e}")
                return None

    return None


def fetch_historical_pool_data(months_back=12):
    """Fetch historical pool data for all subnets."""
    print("Fetching historical pool data from TaoStats...")
    print(f"  (Fetching all available data, will filter to {months_back} months)")

    all_data = []
    page = 1
    consecutive_empty = 0

    while True:
        print(f"  Fetching page {page}...")

        # Use correct API parameters discovered in exploration:
        # - No timestamp filters (pagination handles everything)
        # - order: "timestamp_asc" (not "asc")
        result = taostats_request("/dtao/pool/history/v1", {
            "limit": 200,
            "page": page,
            "order": "timestamp_asc"  # Correct parameter value
        })

        if not result:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            time.sleep(2)
            continue

        consecutive_empty = 0
        data = result.get("data", [])

        if not data:
            print(f"  No more data at page {page}")
            break

        all_data.extend(data)
        print(f"  Got {len(data)} records (total: {len(all_data)})")

        # Check pagination
        pagination = result.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        total_records = pagination.get("total_count", 0)
        print(f"    Page {page} of {total_pages} (total records: {total_records})")

        if page >= total_pages:
            break

        page += 1
        time.sleep(0.3)  # Rate limiting

        # Safety limit
        if page > 500:
            print("  Hit page limit")
            break

    print(f"Total records fetched: {len(all_data)}")

    # Check actual date range in data
    if all_data:
        timestamps = []
        for record in all_data:
            ts = record.get("timestamp") or record.get("block_timestamp")
            if ts:
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        timestamps.append(dt)
                    except:
                        pass
                else:
                    timestamps.append(datetime.fromtimestamp(ts))

        if timestamps:
            print(f"  Actual data range: {min(timestamps)} to {max(timestamps)}")
            print(f"  Data spans {(max(timestamps) - min(timestamps)).days} days")

    return all_data


def fetch_tao_flow_data(months_back=12):
    """Try fetching from the tao_flow endpoint directly."""
    print("\nTrying tao_flow endpoint...")

    end_time = int(datetime.now().timestamp())
    start_time = int((datetime.now() - timedelta(days=months_back * 30)).timestamp())

    result = taostats_request("/dtao/tao_flow/v1", {
        "timestamp_start": start_time,
        "timestamp_end": end_time,
        "limit": 200,
        "page": 1
    })

    if result:
        data = result.get("data", [])
        print(f"  Got {len(data)} records from tao_flow")
        if data:
            print(f"  Sample record: {json.dumps(data[0], indent=2, default=str)[:500]}")
        return data
    else:
        print("  tao_flow endpoint failed")
        return []


def check_available_endpoints():
    """Check what endpoints and data are available."""
    print("\n" + "=" * 70)
    print("CHECKING AVAILABLE DATA")
    print("=" * 70)

    # Try different endpoints
    endpoints_to_try = [
        ("/dtao/pool/history/v1", "Pool History"),
        ("/dtao/tao_flow/v1", "TAO Flow"),
        ("/dtao/pool/v1", "Current Pools"),
        ("/subnet/latest/v1", "Latest Subnets"),
        ("/price/history/v1", "Price History"),
    ]

    for endpoint, name in endpoints_to_try:
        print(f"\nTrying {name} ({endpoint})...")
        result = taostats_request(endpoint, {"limit": 5})
        if result:
            data = result.get("data", [])
            print(f"  ✓ Works - got {len(data)} records")
            if data and len(data) > 0:
                print(f"  Sample keys: {list(data[0].keys())[:10]}")
        else:
            print(f"  ✗ Failed")


def process_pool_data(raw_data, start_date=None, months_back=12):
    """Process raw pool data into daily snapshots by subnet."""
    from datetime import date as date_type

    # Use explicit start_date if provided, otherwise calculate from months_back
    if start_date:
        cutoff_date = start_date
        print(f"\nProcessing pool data (from {cutoff_date} onwards)...")
    else:
        cutoff_date = date_type.today() - timedelta(days=months_back * 30)
        print(f"\nProcessing pool data (filtering to last {months_back} months)...")

    print(f"  Cutoff date: {cutoff_date}")

    by_subnet_date = defaultdict(dict)
    min_date = None
    max_date = None

    for record in raw_data:
        netuid = record.get("netuid")
        timestamp = record.get("timestamp") or record.get("block_timestamp")

        if not netuid or not timestamp:
            continue

        # Parse timestamp
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except:
                continue
        else:
            dt = datetime.fromtimestamp(timestamp)

        date_key = dt.date()

        # Filter to only include data within the requested time range
        if date_key < cutoff_date:
            continue

        if min_date is None or date_key < min_date:
            min_date = date_key
        if max_date is None or date_key > max_date:
            max_date = date_key

        # TaoStats uses total_tao in rao (1e9 = 1 TAO)
        # Try multiple possible field names
        tao_raw = record.get("total_tao") or record.get("tao_in") or record.get("tao") or 0
        alpha_raw = record.get("alpha_in_pool") or record.get("alpha_in") or record.get("alpha") or 0

        # Convert from rao to TAO if values are very large
        tao_in = float(tao_raw) / 1e9 if float(tao_raw) > 1e12 else float(tao_raw)
        alpha_in = float(alpha_raw) / 1e9 if float(alpha_raw) > 1e12 else float(alpha_raw)

        # Price can also come directly from record
        price = float(record.get("price", 0) or 0)
        if price == 0 and alpha_in > 0:
            price = tao_in / alpha_in

        if date_key not in by_subnet_date[netuid] or dt > by_subnet_date[netuid][date_key]['dt']:
            by_subnet_date[netuid][date_key] = {
                'dt': dt,
                'tao_reserve': tao_in,
                'alpha_reserve': alpha_in,
                'price': price,
            }

    # Convert to sorted lists
    processed = {}
    for netuid, dates in by_subnet_date.items():
        sorted_dates = sorted(dates.keys())
        processed[netuid] = [
            {'date': d, 'tao_reserve': dates[d]['tao_reserve'], 'price': dates[d]['price']}
            for d in sorted_dates
        ]

    total_records = sum(len(v) for v in processed.values())
    print(f"Processed {total_records} daily snapshots for {len(processed)} subnets")
    print(f"Date range in data: {min_date} to {max_date}")

    if min_date and max_date:
        days_span = (max_date - min_date).days
        print(f"Data spans {days_span} days")
        if days_span < 30:
            print(f"⚠️  WARNING: Only {days_span} days of data - not enough for reliable backtest!")

    return processed


def compute_flow(history, target_idx, days_back):
    """Compute flow from reserve changes."""
    if target_idx < days_back:
        return None
    current_reserve = history[target_idx]['tao_reserve']
    past_reserve = history[target_idx - days_back]['tao_reserve']
    return current_reserve - past_reserve


def calculate_fai(flow_1d, flow_7d):
    """Calculate Flow Acceleration Index."""
    if flow_7d is None or flow_1d is None:
        return None
    if flow_7d == 0:
        return 1.0
    avg_daily = flow_7d / 7
    if avg_daily == 0:
        return 1.0
    return flow_1d / avg_daily


def get_fai_quintile(fai, all_fai):
    if len(all_fai) < 5:
        return 3
    sorted_fai = sorted(all_fai)
    n = len(sorted_fai)
    qs = [sorted_fai[int(n * q)] for q in [0.2, 0.4, 0.6, 0.8]]
    if fai <= qs[0]: return 1
    if fai <= qs[1]: return 2
    if fai <= qs[2]: return 3
    if fai <= qs[3]: return 4
    return 5


def run_backtest(pool_data):
    """Run the FAI backtest."""
    print("\n" + "=" * 70)
    print("RUNNING FAI BACKTEST")
    print("=" * 70)

    all_dates = set()
    for netuid, history in pool_data.items():
        for record in history:
            all_dates.add(record['date'])

    all_dates = sorted(all_dates)
    days_of_data = len(all_dates)
    print(f"Date range: {all_dates[0]} to {all_dates[-1]} ({days_of_data} days)")

    if days_of_data < 30:
        print(f"\n⚠️  INSUFFICIENT DATA: Only {days_of_data} days available")
        print("Need at least 30 days for meaningful backtest")
        return []

    # Weekly rebalance dates (start after 14 days for flow calc)
    rebalance_dates = all_dates[14::7]
    print(f"Rebalance dates: {len(rebalance_dates)}")

    if len(rebalance_dates) < 2:
        print("Not enough rebalance periods")
        return []

    trades = []

    for rebal_date in rebalance_dates[:-2]:
        subnet_metrics = []

        for netuid, history in pool_data.items():
            date_lookup = {r['date']: i for i, r in enumerate(history)}

            if rebal_date not in date_lookup:
                continue

            idx = date_lookup[rebal_date]
            record = history[idx]

            if idx < 7:
                continue

            flow_1d = compute_flow(history, idx, 1)
            flow_7d = compute_flow(history, idx, 7)

            if flow_1d is None or flow_7d is None:
                continue

            fai = calculate_fai(flow_1d, flow_7d)
            if fai is None:
                continue

            if record['tao_reserve'] < 100:
                continue

            subnet_metrics.append({
                'netuid': netuid,
                'date': rebal_date,
                'price': record['price'],
                'tao_reserve': record['tao_reserve'],
                'flow_1d': flow_1d,
                'flow_7d': flow_7d,
                'fai': fai,
                'history': history,
                'date_lookup': date_lookup,
            })

        if len(subnet_metrics) < 5:
            continue

        all_fai = [s['fai'] for s in subnet_metrics]
        for s in subnet_metrics:
            s['quintile'] = get_fai_quintile(s['fai'], all_fai)

        exit_date = rebal_date + timedelta(days=HOLDING_PERIOD_DAYS)

        for s in subnet_metrics:
            if exit_date not in s['date_lookup']:
                continue

            exit_idx = s['date_lookup'][exit_date]
            exit_record = s['history'][exit_idx]

            if s['price'] <= 0:
                continue

            raw_return = (exit_record['price'] - s['price']) / s['price']
            weight = FAI_QUINTILE_MULTIPLIERS[s['quintile']]

            trades.append({
                'entry_date': rebal_date,
                'exit_date': exit_date,
                'netuid': s['netuid'],
                'raw_return': raw_return,
                'fai': s['fai'],
                'quintile': s['quintile'],
                'weighted_return': raw_return * weight,
            })

    return trades


def analyze_results(trades):
    """Analyze backtest results."""
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    if not trades:
        print("No trades generated!")
        return

    print(f"\nTotal trades: {len(trades)}")
    print(f"Unique subnets: {len(set(t['netuid'] for t in trades))}")
    print(f"Date range: {trades[0]['entry_date']} to {trades[-1]['entry_date']}")

    raw_returns = [t['raw_return'] for t in trades]

    print(f"\nOverall Performance:")
    print(f"  Median Return: {statistics.median(raw_returns):.2%}")
    print(f"  Mean Return: {statistics.mean(raw_returns):.2%}")
    print(f"  Win Rate: {sum(1 for r in raw_returns if r > 0) / len(raw_returns):.1%}")

    print(f"\n" + "=" * 70)
    print("FAI QUINTILE PERFORMANCE")
    print("=" * 70)

    for q in range(1, 6):
        q_trades = [t for t in trades if t['quintile'] == q]
        if q_trades:
            q_returns = [t['raw_return'] for t in q_trades]
            print(f"Q{q}: {len(q_trades):>4} trades | Median: {statistics.median(q_returns):>7.2%} | "
                  f"Win: {sum(1 for r in q_returns if r > 0) / len(q_returns):>5.1%}")

    q5 = [t for t in trades if t['quintile'] == 5]
    q1 = [t for t in trades if t['quintile'] == 1]

    if q5 and q1:
        spread = statistics.median([t['raw_return'] for t in q5]) - statistics.median([t['raw_return'] for t in q1])
        print(f"\n{'=' * 70}")
        print(f"Q5 vs Q1 SPREAD: {spread:+.2%}")
        print(f"{'=' * 70}")

        if spread > 1:
            print("✓ FAI signal is STRONGLY PREDICTIVE")
        elif spread > 0.5:
            print("✓ FAI signal shows MODERATE predictive power")
        elif spread > 0:
            print("~ FAI signal shows WEAK positive edge")
        else:
            print("✗ FAI signal is NOT working")


def main():
    # Configuration - Use specific date cutoff for post-AMM change analysis
    # Bittensor changed AMM model on Nov 5, 2025 - only analyze post-change data
    from datetime import date
    START_DATE = date(2025, 11, 1)  # Start from Nov 1, 2025

    print("=" * 70)
    print(f"PROPER FAI BACKTEST - Post-AMM Change (Nov 2025+)")
    print(f"Analyzing data from {START_DATE} onwards")
    print("=" * 70)

    # Fetch pool history data (all available, ~41K records)
    raw_pool_data = fetch_historical_pool_data(months_back=12)

    if not raw_pool_data:
        print("\nERROR: Could not fetch historical data from TaoStats")
        print("The API may not have historical pool data.")
        return

    # Show sample record structure
    if raw_pool_data:
        print(f"\nSample record keys: {list(raw_pool_data[0].keys())}")

    pool_data = process_pool_data(raw_pool_data, start_date=START_DATE)

    if not pool_data:
        print("ERROR: No valid pool data after processing")
        return

    trades = run_backtest(pool_data)
    analyze_results(trades)

    print("\n" + "=" * 70)
    print("BACKTEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
