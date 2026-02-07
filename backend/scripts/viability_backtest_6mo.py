#!/usr/bin/env python3
"""
Viability Cutoff Backtest - Last 6 Months Only

4-Factor Viability Model:
- FAI (40%)
- Emission Share (25%)
- TAO Reserve (20%)
- Max Drawdown 30D (15%)
"""

import os
import sys
from datetime import timedelta, date
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

HARD_FAILURES = {
    "min_age_days": 14,
    "max_negative_flow_ratio": 0.50,
    "min_reserve": 100,
}

HOLDING_PERIOD_DAYS = 14
FAI_QUINTILE_MULTIPLIERS = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}


async def load_data():
    async with async_session() as db:
        cutoff_date = date.today() - timedelta(days=180)

        query = text("""
            WITH daily AS (
                SELECT DISTINCT ON (netuid, timestamp::date)
                    netuid,
                    timestamp::date as snap_date,
                    alpha_price_tao,
                    pool_tao_reserve,
                    emission_share
                FROM subnet_snapshots
                WHERE alpha_price_tao > 0
                  AND netuid != 0
                  AND timestamp::date >= :cutoff
                ORDER BY netuid, timestamp::date, timestamp DESC
            )
            SELECT * FROM daily ORDER BY snap_date, netuid
        """)
        result = await db.execute(query, {"cutoff": cutoff_date})
        rows = result.fetchall()

        by_netuid = defaultdict(list)
        for row in rows:
            by_netuid[row[0]].append({
                'date': row[1],
                'price': float(row[2]),
                'reserve': float(row[3]) if row[3] else 0,
                'emission': float(row[4]) if row[4] else 0,
            })

        dates = sorted(set(r[1] for r in rows))

        meta_result = await db.execute(text("SELECT netuid, name FROM subnets"))
        names = {row[0]: row[1] for row in meta_result.fetchall()}

        print(f"Loaded {len(by_netuid)} subnets, {len(dates)} days")
        print(f"Date range: {dates[0]} to {dates[-1]}")

        return by_netuid, dates, names


def get_rec(history, d):
    for r in history:
        if r['date'] == d:
            return r
    return None


def compute_flow(history, d, days):
    t = get_rec(history, d)
    p = get_rec(history, d - timedelta(days=days))
    if t and p:
        return t['reserve'] - p['reserve']
    return 0


def calc_fai(f1d, f7d):
    if f7d == 0:
        return 1.0
    avg = f7d / 7
    return f1d / avg if avg != 0 else 1.0


def compute_dd(history, end_date, days=30):
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


def compute_age(history, d):
    if not history:
        return 0
    first = min(r['date'] for r in history)
    return (d - first).days


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


async def run_backtest(by_netuid, dates, names, cutoff):
    rebal_dates = dates[21::7]
    trades = []

    for rebal_date in rebal_dates[:-3]:
        subnet_data = []

        for netuid, history in by_netuid.items():
            rec = get_rec(history, rebal_date)
            if not rec or rec['price'] <= 0:
                continue

            f1d = compute_flow(history, rebal_date, 1)
            f7d = compute_flow(history, rebal_date, 7)
            fai = calc_fai(f1d, f7d)
            dd = compute_dd(history, rebal_date)
            age = compute_age(history, rebal_date)

            if age < HARD_FAILURES['min_age_days']:
                continue
            if rec['reserve'] < HARD_FAILURES['min_reserve']:
                continue
            if rec['reserve'] > 0 and f7d / rec['reserve'] < -HARD_FAILURES['max_negative_flow_ratio']:
                continue

            subnet_data.append({
                'netuid': netuid,
                'name': names.get(netuid, f'SN{netuid}'),
                'price': rec['price'],
                'reserve': rec['reserve'],
                'emission': rec['emission'],
                'fai': fai,
                'f7d': f7d,
                'dd': dd,
            })

        if len(subnet_data) < 5:
            continue

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
            history = by_netuid[s['netuid']]
            exit_rec = get_rec(history, exit_date)
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
    rr = [t['raw_return'] for t in trades]
    capped = [min(5.0, max(-1.0, r)) for r in wr]

    return {
        'cutoff': cutoff,
        'total_trades': len(trades),
        'unique_subnets': len(set(t['netuid'] for t in trades)),
        'avg_return': statistics.mean(wr),
        'median_return': statistics.median(wr),
        'raw_median': statistics.median(rr),
        'capped_avg': statistics.mean(capped),
        'win_rate': sum(1 for r in wr if r > 0) / len(wr),
        'std': statistics.stdev(capped) if len(capped) > 1 else 0.01,
        'sharpe': statistics.mean(capped) / (statistics.stdev(capped) if len(capped) > 1 else 0.01) * (26**0.5),
        'trades': trades,
    }


async def main():
    print("=" * 80)
    print("VIABILITY CUTOFF BACKTEST - LAST 6 MONTHS")
    print("=" * 80)

    result = await load_data()
    if not result:
        return

    by_netuid, dates, names = result

    print()
    print("=" * 80)
    print("TESTING CUTOFFS")
    print("=" * 80)

    cutoffs = [20, 30, 40, 50, 60, 70, 80]
    results = []

    for c in cutoffs:
        r = await run_backtest(by_netuid, dates, names, c)
        results.append(r)
        if r['total_trades'] > 0:
            print(f"Cutoff {c}: {r['total_trades']} trades, "
                  f"Median: {r['median_return']:.1%}, Win: {r['win_rate']:.1%}, Sharpe: {r['sharpe']:.2f}")
        else:
            print(f"Cutoff {c}: No trades")

    print()
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Cut':>4} {'Trades':>7} {'SNs':>4} {'Median':>8} {'RawMed':>8} {'Win%':>6} {'Sharpe':>7}")
    print("-" * 60)

    for r in results:
        if r['total_trades'] > 0:
            print(f"{r['cutoff']:>4} {r['total_trades']:>7} {r['unique_subnets']:>4} "
                  f"{r['median_return']:>7.1%} {r['raw_median']:>7.1%} "
                  f"{r['win_rate']:>5.1%} {r['sharpe']:>7.2f}")

    # Analysis
    valid = [r for r in results if r['total_trades'] >= 30]
    if valid:
        best_sharpe = max(valid, key=lambda x: x['sharpe'])
        best_winrate = max(valid, key=lambda x: x['win_rate'])
        best_median = max(valid, key=lambda x: x['median_return'])

        print()
        print("=" * 80)
        print("ANALYSIS")
        print("=" * 80)
        print(f"\nBest Sharpe: Cutoff {best_sharpe['cutoff']} (Sharpe: {best_sharpe['sharpe']:.2f})")
        print(f"Best Win Rate: Cutoff {best_winrate['cutoff']} (Win: {best_winrate['win_rate']:.1%})")
        print(f"Best Median: Cutoff {best_median['cutoff']} (Median: {best_median['median_return']:.1%})")

        # Quintile breakdown for best
        best = best_sharpe
        if best['trades']:
            print(f"\nQuintile Breakdown (Cutoff {best['cutoff']}):")
            print("-" * 50)
            for q in range(1, 6):
                qt = [t for t in best['trades'] if t['quintile'] == q]
                if qt:
                    qr = [t['weighted_return'] for t in qt]
                    print(f"  Q{q}: {len(qt)} trades, "
                          f"Median: {statistics.median(qr):.1%}, "
                          f"Win: {sum(1 for r in qr if r > 0)/len(qr):.1%}")

            # Q5 vs Q1 spread
            q5 = [t for t in best['trades'] if t['quintile'] == 5]
            q1 = [t for t in best['trades'] if t['quintile'] == 1]
            if q5 and q1:
                q5_med = statistics.median([t['weighted_return'] for t in q5])
                q1_med = statistics.median([t['weighted_return'] for t in q1])
                spread = q5_med - q1_med
                print(f"\n  Q5 vs Q1 Spread: {spread:.1%}")
                if spread > 1:
                    print(f"  ✓ FAI quintile strategy is WORKING")
                elif spread < -1:
                    print(f"  ✗ FAI quintile strategy INVERTED")
                else:
                    print(f"  ~ FAI quintile strategy is NEUTRAL")

        # Viability score band analysis
        print()
        print("Performance by Viability Score Band:")
        print("-" * 50)

        all_trades = []
        for r in results:
            if r['trades']:
                all_trades.extend(r['trades'])

        bands = [(20, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 100)]
        for low, high in bands:
            bt = [t for t in all_trades if low <= t['vscore'] < high]
            if bt:
                br = [t['weighted_return'] for t in bt]
                print(f"  {low}-{high}: {len(bt)} trades, "
                      f"Median: {statistics.median(br):.1%}, "
                      f"Win: {sum(1 for r in br if r > 0)/len(br):.1%}")

        print()
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        print(f"\nRecommended Viability Cutoff: {best_sharpe['cutoff']}")
        print(f"  - Sharpe: {best_sharpe['sharpe']:.2f}")
        print(f"  - Win Rate: {best_sharpe['win_rate']:.1%}")
        print(f"  - Median Return: {best_sharpe['median_return']:.1%}")
        print(f"  - Universe: {best_sharpe['total_trades']} trades ({best_sharpe['unique_subnets']} subnets)")


if __name__ == "__main__":
    asyncio.run(main())
