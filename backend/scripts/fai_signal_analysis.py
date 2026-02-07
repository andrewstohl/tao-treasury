#!/usr/bin/env python3
"""
Analyze why FAI signal appears inverted in backtest.
Check if the raw signal works without viability filtering.
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


async def load_data():
    async with async_session() as db:
        query = text("""
            WITH daily AS (
                SELECT DISTINCT ON (netuid, timestamp::date)
                    netuid,
                    timestamp::date as snap_date,
                    alpha_price_tao,
                    pool_tao_reserve
                FROM subnet_snapshots
                WHERE alpha_price_tao > 0 AND netuid != 0
                ORDER BY netuid, timestamp::date, timestamp DESC
            )
            SELECT * FROM daily ORDER BY snap_date, netuid
        """)
        result = await db.execute(query)
        rows = result.fetchall()

        by_netuid = defaultdict(list)
        for row in rows:
            by_netuid[row[0]].append({
                'date': row[1],
                'price': float(row[2]),
                'reserve': float(row[3]) if row[3] else 0,
            })

        dates = sorted(set(r[1] for r in rows))
        return by_netuid, dates


def get_rec(history, date):
    for r in history:
        if r['date'] == date:
            return r
    return None


def compute_flow(history, date, days):
    t = get_rec(history, date)
    p = get_rec(history, date - timedelta(days=days))
    if t and p:
        return t['reserve'] - p['reserve']
    return 0


def calc_fai(f1d, f7d):
    if f7d == 0:
        return 1.0
    avg = f7d / 7
    return f1d / avg if avg != 0 else 1.0


async def main():
    print("=" * 70)
    print("FAI SIGNAL ANALYSIS")
    print("Testing raw FAI predictive power without viability filtering")
    print("=" * 70)

    by_netuid, dates = await load_data()
    print(f"\nLoaded {len(by_netuid)} subnets, {len(dates)} days")

    # Test FAI signal directly
    rebal_dates = dates[21::7]

    all_trades = []

    for rebal_date in rebal_dates[:-3]:
        for netuid, history in by_netuid.items():
            rec = get_rec(history, rebal_date)
            if not rec:
                continue

            f1d = compute_flow(history, rebal_date, 1)
            f7d = compute_flow(history, rebal_date, 7)
            fai = calc_fai(f1d, f7d)

            # Check we have entry and exit data
            exit_date = rebal_date + timedelta(days=14)
            exit_rec = get_rec(history, exit_date)
            if not exit_rec:
                continue

            ret = (exit_rec['price'] - rec['price']) / rec['price'] if rec['price'] > 0 else 0

            all_trades.append({
                'date': rebal_date,
                'netuid': netuid,
                'fai': fai,
                'f1d': f1d,
                'f7d': f7d,
                'return': ret,
            })

    print(f"\nTotal trades: {len(all_trades)}")

    # Analyze by FAI quintile
    faival = [t['fai'] for t in all_trades]
    sf = sorted(faival)
    n = len(sf)
    qs = [sf[int(n * q)] for q in [0.2, 0.4, 0.6, 0.8]]

    def get_q(fai):
        if fai <= qs[0]: return 1
        if fai <= qs[1]: return 2
        if fai <= qs[2]: return 3
        if fai <= qs[3]: return 4
        return 5

    print(f"\nFAI Quintile Boundaries:")
    print(f"  Q1: <= {qs[0]:.2f}")
    print(f"  Q2: <= {qs[1]:.2f}")
    print(f"  Q3: <= {qs[2]:.2f}")
    print(f"  Q4: <= {qs[3]:.2f}")
    print(f"  Q5: > {qs[3]:.2f}")

    print()
    print("=" * 70)
    print("RAW FAI QUINTILE PERFORMANCE (14-day returns)")
    print("=" * 70)

    for q in range(1, 6):
        qt = [t for t in all_trades if get_q(t['fai']) == q]
        if qt:
            rets = [t['return'] for t in qt]
            capped = [min(5, max(-1, r)) for r in rets]
            print(f"Q{q}: {len(qt)} trades, Median: {statistics.median(rets):.1%}, "
                  f"Mean (capped): {statistics.mean(capped):.1%}, "
                  f"Win: {sum(1 for r in rets if r > 0)/len(rets):.1%}")

    # Q5 vs Q1 spread
    q5_trades = [t for t in all_trades if get_q(t['fai']) == 5]
    q1_trades = [t for t in all_trades if get_q(t['fai']) == 1]
    q5_med = statistics.median([t['return'] for t in q5_trades])
    q1_med = statistics.median([t['return'] for t in q1_trades])
    spread = q5_med - q1_med

    print()
    print(f"Q5 vs Q1 Spread: {spread:.1%}")

    # Also test 7d flow level (which our earlier research said was contrarian)
    print()
    print("=" * 70)
    print("7D FLOW LEVEL QUINTILE PERFORMANCE")
    print("=" * 70)

    f7d_vals = [t['f7d'] for t in all_trades]
    sf7 = sorted(f7d_vals)
    qs7 = [sf7[int(n * q)] for q in [0.2, 0.4, 0.6, 0.8]]

    def get_q7(f7d):
        if f7d <= qs7[0]: return 1
        if f7d <= qs7[1]: return 2
        if f7d <= qs7[2]: return 3
        if f7d <= qs7[3]: return 4
        return 5

    for q in range(1, 6):
        qt = [t for t in all_trades if get_q7(t['f7d']) == q]
        if qt:
            rets = [t['return'] for t in qt]
            capped = [min(5, max(-1, r)) for r in rets]
            print(f"Q{q}: {len(qt)} trades, Median: {statistics.median(rets):.1%}, "
                  f"Mean (capped): {statistics.mean(capped):.1%}, "
                  f"Win: {sum(1 for r in rets if r > 0)/len(rets):.1%}")

    q5_flow = [t for t in all_trades if get_q7(t['f7d']) == 5]
    q1_flow = [t for t in all_trades if get_q7(t['f7d']) == 1]
    q5_f_med = statistics.median([t['return'] for t in q5_flow])
    q1_f_med = statistics.median([t['return'] for t in q1_flow])
    spread_flow = q5_f_med - q1_f_med

    print()
    print(f"Q5 vs Q1 Spread (Flow Level): {spread_flow:.1%}")

    # Test if NEGATIVE flow (contrarian) works
    print()
    print("=" * 70)
    print("CONTRARIAN TEST: LOW FLOW vs HIGH FLOW")
    print("=" * 70)

    low_flow = [t for t in all_trades if t['f7d'] < 0]
    high_flow = [t for t in all_trades if t['f7d'] > 100]  # Significant inflow

    if low_flow:
        lf_rets = [t['return'] for t in low_flow]
        print(f"Negative 7d Flow: {len(low_flow)} trades, "
              f"Median: {statistics.median(lf_rets):.1%}, "
              f"Win: {sum(1 for r in lf_rets if r > 0)/len(lf_rets):.1%}")

    if high_flow:
        hf_rets = [t['return'] for t in high_flow]
        print(f"High 7d Flow (>100): {len(high_flow)} trades, "
              f"Median: {statistics.median(hf_rets):.1%}, "
              f"Win: {sum(1 for r in hf_rets if r > 0)/len(hf_rets):.1%}")

    # Test different FAI thresholds
    print()
    print("=" * 70)
    print("FAI THRESHOLD ANALYSIS")
    print("=" * 70)

    for threshold in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
        above = [t for t in all_trades if t['fai'] >= threshold]
        below = [t for t in all_trades if t['fai'] < threshold]

        if above and below:
            a_med = statistics.median([t['return'] for t in above])
            b_med = statistics.median([t['return'] for t in below])
            a_win = sum(1 for t in above if t['return'] > 0) / len(above)
            b_win = sum(1 for t in below if t['return'] > 0) / len(below)
            print(f"FAI >= {threshold}: {len(above)} trades, Median: {a_med:.1%}, Win: {a_win:.1%}")
            print(f"FAI <  {threshold}: {len(below)} trades, Median: {b_med:.1%}, Win: {b_win:.1%}")
            print(f"  Spread: {a_med - b_med:.1%}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
