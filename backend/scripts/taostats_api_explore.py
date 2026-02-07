#!/usr/bin/env python3
"""
Explore TaoStats API to understand available historical data.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta

TAOSTATS_API_KEY = os.environ.get("TAOSTATS_API_KEY", "tao-dab24c32-ecc6-434b-ad56-980192efd160:27bd8dac")
TAOSTATS_BASE_URL = "https://api.taostats.io/api"


def api_request(endpoint, params=None):
    """Make request to TaoStats API."""
    url = f"{TAOSTATS_BASE_URL}{endpoint}"
    headers = {
        "Authorization": TAOSTATS_API_KEY,
        "accept": "application/json"
    }

    print(f"\nRequesting: {endpoint}")
    print(f"  Params: {params}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        print(f"  Status: {response.status_code}")

        if response.status_code != 200:
            print(f"  Error: {response.text[:500]}")
            return None

        data = response.json()
        return data
    except Exception as e:
        print(f"  Exception: {e}")
        return None


def main():
    print("=" * 70)
    print("EXPLORING TAOSTATS API")
    print("=" * 70)

    # 1. Get pool history without timestamp filters
    print("\n" + "=" * 70)
    print("1. Pool History - No filters")
    print("=" * 70)
    result = api_request("/dtao/pool/history/v1", {"limit": 5})
    if result:
        print(f"  Data count: {len(result.get('data', []))}")
        print(f"  Pagination: {result.get('pagination', {})}")
        if result.get('data'):
            print(f"  Sample record keys: {list(result['data'][0].keys())}")
            print(f"  Sample record: {json.dumps(result['data'][0], indent=2, default=str)[:800]}")

    # 2. Pool history with netuid filter
    print("\n" + "=" * 70)
    print("2. Pool History - Single subnet (netuid=1)")
    print("=" * 70)
    result = api_request("/dtao/pool/history/v1", {"netuid": 1, "limit": 10})
    if result:
        data = result.get('data', [])
        print(f"  Data count: {len(data)}")
        print(f"  Pagination: {result.get('pagination', {})}")
        if data:
            # Check date range
            timestamps = [d.get('timestamp') for d in data if d.get('timestamp')]
            if timestamps:
                print(f"  Timestamps: {timestamps[:3]}...")

    # 3. Check what parameters pool/history accepts
    print("\n" + "=" * 70)
    print("3. Pool History - Testing different parameter names")
    print("=" * 70)

    # Try different date parameter formats
    param_tests = [
        {"limit": 5, "netuid": 1},
        {"limit": 5, "netuid": 1, "page": 1},
        {"limit": 5, "netuid": 1, "order": "desc"},
    ]

    for params in param_tests:
        result = api_request("/dtao/pool/history/v1", params)
        if result:
            print(f"  ✓ Works with {params}")
        time.sleep(0.5)

    # 4. Check liquidity position events (trades)
    print("\n" + "=" * 70)
    print("4. Liquidity Position Events")
    print("=" * 70)
    result = api_request("/dtao/liquidity/position_event/v1", {"limit": 5})
    if result:
        data = result.get('data', [])
        print(f"  Data count: {len(data)}")
        if data:
            print(f"  Sample keys: {list(data[0].keys())}")
            print(f"  Sample: {json.dumps(data[0], indent=2, default=str)[:800]}")

    # 5. Check TAO flow endpoint
    print("\n" + "=" * 70)
    print("5. TAO Flow Endpoint")
    print("=" * 70)
    result = api_request("/dtao/tao_flow/v1", {"limit": 10})
    if result:
        data = result.get('data', [])
        print(f"  Data count: {len(data)}")
        if data:
            print(f"  Sample keys: {list(data[0].keys())}")
            # This appears to be current flow, not historical
            for d in data[:3]:
                print(f"    SN{d.get('netuid')}: tao_flow={d.get('tao_flow')}")

    # 6. Check if there's a history endpoint for tao_flow
    print("\n" + "=" * 70)
    print("6. Trying tao_flow history variants")
    print("=" * 70)

    endpoints_to_try = [
        "/dtao/tao_flow/history/v1",
        "/dtao/flow/history/v1",
        "/dtao/subnet/flow/v1",
    ]

    for endpoint in endpoints_to_try:
        result = api_request(endpoint, {"limit": 5})
        time.sleep(0.5)

    # 7. Check pool endpoint for single subnet over time
    print("\n" + "=" * 70)
    print("7. Pool History for SN1 - Check all records")
    print("=" * 70)

    all_sn1_data = []
    page = 1
    while page <= 5:  # Get up to 5 pages
        result = api_request("/dtao/pool/history/v1", {
            "netuid": 1,
            "limit": 200,
            "page": page
        })
        if not result or not result.get('data'):
            break
        all_sn1_data.extend(result['data'])
        pagination = result.get('pagination', {})
        print(f"  Page {page}: got {len(result['data'])} records, total pages: {pagination.get('total_pages')}")
        if page >= pagination.get('total_pages', 1):
            break
        page += 1
        time.sleep(1)

    print(f"\n  Total SN1 records: {len(all_sn1_data)}")

    if all_sn1_data:
        # Analyze date range
        timestamps = []
        for record in all_sn1_data:
            ts = record.get('timestamp')
            if ts:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    else:
                        dt = datetime.fromtimestamp(ts)
                    timestamps.append(dt)
                except:
                    pass

        if timestamps:
            min_dt = min(timestamps)
            max_dt = max(timestamps)
            print(f"  Date range: {min_dt} to {max_dt}")
            print(f"  Span: {(max_dt - min_dt).days} days")

            # Check tao_in values
            tao_values = [float(r.get('tao_in', 0) or 0) for r in all_sn1_data if r.get('tao_in')]
            if tao_values:
                print(f"  TAO in pool range: {min(tao_values):.2f} to {max(tao_values):.2f}")

    # 8. Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
Based on exploration:
- /dtao/pool/history/v1 returns historical pool data
- Data appears to be available per-subnet with pagination
- Need to fetch all pages to get full history
- tao_flow endpoint only returns CURRENT values, not historical

Next step: Fetch all pages of pool/history for all subnets
    """)


if __name__ == "__main__":
    main()
