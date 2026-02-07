#!/usr/bin/env python3
"""
FIXED Viability Cutoff Backtest v2

Properly computes historical flow from pool_tao_reserve changes.
Relaxes hard failures to only use historically available data.

Available in snapshots: price, reserve, emission_share
NOT available historically: holder_count, owner_take

Hard Failures (using available data):
- Age < 14 days
- Severe outflow (7d flow < -50% of reserve)

4-Factor Viability Model:
- FAI (40%) - Flow Acceleration Index
- Emission Share (25%) - from snapshots
- TAO Reserve (20%) - from snapshots
- Max Drawdown 30D (15%) - computed from price history
"""

import os
import sys
from datetime import timedelta
from collections import defaultdict
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tao_treasury")
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


VIABILITY_WEIGHTS = {
    "fai": 0.40,
    "emission_share": 0.25,
    "tao_reserve": 0.20,
    "max_drawdown_30d": 0.15,
}

# Relaxed hard failures - only use what we have historically
HARD_FAILURES = {
    "min_age_days": 14,
    "max_negative_flow_ratio": 0.50,
    "min_reserve": 100,  # Minimum TAO reserve for liquidity
}

HOLDING_PERIOD_DAYS = 14
FAI_QUINTILE_MULTIPLIERS = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}


async def load_snapshot_data():
    """Load subnet snapshots."""
    async with async_session() as db:
        query = text("""
            WITH daily_snapshots AS (
                SELECT DISTINCT ON (netuid, timestamp::date)
                    netuid,
                    timestamp::date as snap_date,
                    alpha_price_tao,
                    pool_tao_reserve,
                    emission_share
                FROM subnet_snapshots
                WHERE alpha_price_tao IS NOT NULL
                  AND alpha_price_tao > 0
                  AND netuid != 0
                ORDER BY netuid, timestamp::date, timestamp DESC
            )
            SELECT * FROM daily_snapshots
            ORDER BY snap_date ASC, netuid ASC
        """)

        result = await db.execute(query)
        rows = result.fetchall()

        data_by_netuid = defaultdict(list)
        for row in rows:
            data_by_netuid[row[0]].append({
                'netuid': row[0],
                'date': row[1],
                'price': float(row[2]) if row[2] else 0,
                'reserve': float(row[3]) if row[3] else 0,
                'emission_share': float(row[4]) if row[4] else 0,
            })

        dates = sorted(set(row[1] for row in rows))
        netuids = list(data_by_netuid.keys())

        # Get subnet names
        meta_result = await db.execute(text("SELECT netuid, name FROM subnets"))
        names = {row[0]: row[1] for row in meta_result.fetchall()}

        print(f"Loaded {len(netuids)} subnets, {len(dates)} days")
        print(f"Date range: {dates[0]} to {dates[-1]}")

        return data_by_netuid, dates, names


def get_record(history, target_date):
    """Get record for date or None."""
    for r in history:
        if r['date'] == target_date:
            return r
    return None


def compute_flow(history, target_date, days_back):
    """Compute flow from reserve change."""
    target = get_record(history, target_date)
    past = get_record(history, target_date - timedelta(days=days_back))
    if target and past:
        return target['reserve'] - past['reserve']
    return 0


def calculate_fai(flow_1d, flow_7d):
    if flow_7d == 0:
        return 1.0
    avg_daily = flow_7d / 7
    if avg_daily == 0:
        return 1.0
    return flow_1d / avg_daily


def compute_drawdown(history, end_date, days=30):
    start = end_date - timedelta(days=days)
    prices = [r['price'] for r in history if start <= r['date'] <= end_date and r['price'] > 0]
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def compute_age(history, target_date):
    if not history:
        return 0
    first = min(r['date'] for r in history)
    return (target_date - first).days


def pct_rank(values, target):
    if len(values) <= 1:
        return 50.0
    sv = sorted(values)
    rank = sum(1 for v in sv if v < target)
    return rank / (len(sv) - 1) * 100


def pct_rank_inv(values, target):
    if len(values) <= 1:
        return 50.0
    sv = sorted(values, reverse=True)
    rank = sum(1 for v in sv if v > target)
    return rank / (len(sv) - 1) * 100


def viability_score(fai, emission, reserve, dd, all_fai, all_em, all_res, all_dd):
    return (
        pct_rank(all_fai, fai) * VIABILITY_WEIGHTS['fai'] +
        pct_rank(all_em, emission) * VIABILITY_WEIGHTS['emission_share'] +
        pct_rank(all_res, reserve) * VIABILITY_WEIGHTS['tao_reserve'] +
        pct_rank_inv(all_dd, dd) * VIABILITY_WEIGHTS['max_drawdown_30d']
    )


def fai_quintile(fai, all_fai):
    if len(all_fai) < 5:
        return 3
    sf = sorted(all_fai)
    n = len(sf)
    qs = [sf[int(n * q)] for q in [0.2, 0.4, 0.6, 0.8]]
    if fai <= qs[0]: return 1
    if fai <= qs[1]: return 2
    if fai <= qs[2]: return 3
    if fai <= qs[3]: return 4
    return 5


async def run_backtest(data_by_netuid, dates, names, cutoff):
    rebal_dates = dates[21::7]  # Start after 21 days, weekly

    trades = []

    for rebal_date in rebal_dates[:-3]:
        subnet_data = []

        for netuid, history in data_by_netuid.items():
            record = get_record(history, rebal_date)
            if not record or record['price'] <= 0:
                continue

            flow_1d = compute_flow(history, rebal_date, 1)
            flow_7d = compute_flow(history, rebal_date, 7)
            fai = calculate_fai(flow_1d, flow_7d)
            dd = compute_drawdown(history, rebal_date)
            age = compute_age(history, rebal_date)

            # Hard failure checks
            if age < HARD_FAILURES['min_age_days']:
                continue
            if record['reserve'] < HARD_FAILURES['min_reserve']:
                continue
            if record['reserve'] > 0 and flow_7d / record['reserve'] < -HARD_FAILURES['max_negative_flow_ratio']:
                continue

            subnet_data.append({
                'netuid': netuid,
                'name': names.get(netuid, f'SN{netuid}'),
                'price': record['price'],
                'reserve': record['reserve'],
                'emission': record['emission_share'],
                'fai': fai,
                'flow_1d': flow_1d,
                'flow_7d': flow_7d,
                'dd': dd,
            })

        if len(subnet_data) < 5:
            continue

        # Compute viability scores
        all_fai = [s['fai'] for s in subnet_data]
        all_em = [s['emission'] for s in subnet_data]
        all_res = [s['reserve'] for s in subnet_data]
        all_dd = [s['dd'] for s in subnet_data]

        for s in subnet_data:
            s['vscore'] = viability_score(s['fai'], s['emission'], s['reserve'], s['dd'],
                                          all_fai, all_em, all_res, all_dd)

        viable = [s for s in subnet_data if s['vscore'] >= cutoff]
        if len(viable) < 3:
            continue

        viable_fai = [s['fai'] for s in viable]
        for s in viable:
            s['quintile'] = fai_quintile(s['fai'], viable_fai)

        exit_date = rebal_date + timedelta(days=HOLDING_PERIOD_DAYS)

        for s in viable:
            history = data_by_netuid[s['netuid']]
            exit_rec = get_record(history, exit_date)
            if not exit_rec:
                continue

            raw_ret = (exit_rec['price'] - s['price']) / s['price'] if s['price'] > 0 else 0
            wt = FAI_QUINTILE_MULTIPLIERS[s['quintile']]

            trades.append({
                'date': rebal_date,
                'netuid': s['netuid'],
                'name': s['name'],
                'raw_return': raw_ret,
                'weighted_return': raw_ret * wt,
                'fai': s['fai'],
                'quintile': s['quintile'],
                'vscore': s['vscore'],
            })

    if not trades:
        return {'cutoff': cutoff, 'total_trades': 0}

    wr = [t['weighted_return'] for t in trades]
    capped = [min(5.0, max(-1.0, r)) for r in wr]

    return {
        'cutoff': cutoff,
        'total_trades': len(trades),
        'unique_subnets': len(set(t['netuid'] for t in trades)),
        'avg_return': statistics.mean(wr),
        'median_return': statistics.median(wr),
        'capped_avg': statistics.mean(capped),
        'win_rate': sum(1 for r in wr if r > 0) / len(wr),
        'std': statistics.stdev(capped) if len(capped) > 1 else 0.01,
        'sharpe': statistics.mean(capped) / (statistics.stdev(capped) if len(capped) > 1 else 0.01) * (26**0.5),
        'trades': trades,
    }


async def main():
    print("=" * 80)
    print("VIABILITY CUTOFF BACKTEST v2")
    print("(Fixed: Historical flow from reserves, relaxed hard failures)")
    print("=" * 80)

    result = await load_snapshot_data()
    if not result:
        return

    data_by_netuid, dates, names = result

    print()
    print("=" * 80)
    print("TESTING CUTOFFS")
    print("=" * 80)

    cutoffs = [20, 30, 40, 50, 60, 70, 80]
    results = []

    for c in cutoffs:
        r = await run_backtest(data_by_netuid, dates, names, c)
        results.append(r)
        if r['total_trades'] > 0:
            print(f"Cutoff {c}: {r['total_trades']} trades, "
                  f"Median: {r['median_return']:.1%}, Win: {r['win_rate']:.1%}, Sharpe: {r['sharpe']:.2f}")
        else:
            print(f"Cutoff {c}: No trades")

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    print(f"{'Cut':>4} {'Trades':>7} {'SNs':>4} {'Median':>8} {'Mean':>8} {'Win%':>6} {'Sharpe':>7}")
    print("-" * 55)

    for r in results:
        if r['total_trades'] > 0:
            print(f"{r['cutoff']:>4} {r['total_trades']:>7} {r['unique_subnets']:>4} "
                  f"{r['median_return']:>7.1%} {r['avg_return']:>7.1%} "
                  f"{r['win_rate']:>5.1%} {r['sharpe']:>7.2f}")

    # Analysis
    valid = [r for r in results if r['total_trades'] >= 50]
    if valid:
        best = max(valid, key=lambda x: x['sharpe'])
        print()
        print("=" * 80)
        print("ANALYSIS")
        print("=" * 80)
        print(f"\nBest Sharpe: Cutoff {best['cutoff']}")
        print(f"  Sharpe: {best['sharpe']:.2f}")
        print(f"  Win Rate: {best['win_rate']:.1%}")
        print(f"  Median Return: {best['median_return']:.1%}")

        # Quintile breakdown
        if best['trades']:
            print(f"\nQuintile Breakdown:")
            for q in range(1, 6):
                qt = [t for t in best['trades'] if t['quintile'] == q]
                if qt:
                    qr = [t['weighted_return'] for t in qt]
                    print(f"  Q{q}: {len(qt)} trades, "
                          f"Median: {statistics.median(qr):.1%}, "
                          f"Win: {sum(1 for r in qr if r > 0)/len(qr):.1%}")

        # Compare Q5 vs Q1 spread
        q5_trades = [t for t in best['trades'] if t['quintile'] == 5]
        q1_trades = [t for t in best['trades'] if t['quintile'] == 1]
        if q5_trades and q1_trades:
            q5_median = statistics.median([t['weighted_return'] for t in q5_trades])
            q1_median = statistics.median([t['weighted_return'] for t in q1_trades])
            spread = q5_median - q1_median
            print(f"\n  Q5 vs Q1 Spread: {spread:.1%}")
            if spread > 0:
                print(f"  ✓ FAI quintile strategy is WORKING (higher FAI → better returns)")
            else:
                print(f"  ✗ FAI quintile strategy NOT working at this cutoff")

        print()
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        print(f"\nViability Cutoff: {best['cutoff']}")
        print(f"  - Subnets with score >= {best['cutoff']} → VIABLE")
        print(f"  - Subnets with score < {best['cutoff']} → NOT VIABLE")


if __name__ == "__main__":
    asyncio.run(main())
