#!/usr/bin/env python3
"""
Detailed Viability Cutoff Analysis

Deeper dive into the viability cutoff results:
1. Median vs Mean returns (handle outliers)
2. Finer granularity around the 40-70 range
3. Return distribution analysis
4. Universe size vs quality tradeoff
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


# Same configuration as before
VIABILITY_WEIGHTS = {
    "fai": 0.40,
    "emission_share": 0.25,
    "tao_reserve": 0.20,
    "max_drawdown_30d": 0.15,
}

HARD_FAILURES = {
    "min_age_days": 14,
    "min_holders": 50,
    "max_owner_take": 0.18,
    "max_negative_flow_ratio": 0.50,
}

HOLDING_PERIOD_DAYS = 14
FAI_QUINTILE_MULTIPLIERS = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}


async def load_all_data():
    """Load subnet snapshots and enriched data."""
    async with async_session() as db:
        query = text("""
        SELECT
            ss.netuid,
            ss.timestamp::date as snap_date,
            ss.alpha_price_tao,
            s.name,
            s.age_days,
            s.holder_count,
            s.owner_take,
            s.startup_mode,
            s.emission_share,
            s.pool_tao_reserve,
            s.taoflow_1d,
            s.taoflow_7d
        FROM subnet_snapshots ss
        JOIN subnets s ON ss.netuid = s.netuid
        WHERE ss.alpha_price_tao IS NOT NULL
          AND ss.alpha_price_tao > 0
          AND ss.netuid != 0
        ORDER BY ss.timestamp ASC
        """)

        result = await db.execute(query)
        rows = result.fetchall()

        data = []
        for row in rows:
            data.append({
                'netuid': row[0],
                'date': row[1],
                'alpha_price_tao': float(row[2]) if row[2] else 0,
                'name': row[3] or f"SN{row[0]}",
                'age_days': int(row[4]) if row[4] else 0,
                'holder_count': int(row[5]) if row[5] else 0,
                'owner_take': float(row[6]) if row[6] else 0,
                'startup_mode': bool(row[7]) if row[7] is not None else False,
                'emission_share': float(row[8]) if row[8] else 0,
                'pool_tao_reserve': float(row[9]) if row[9] else 0,
                'taoflow_1d': float(row[10]) if row[10] else 0,
                'taoflow_7d': float(row[11]) if row[11] else 0,
            })

        return data


def calculate_fai(flow_1d: float, flow_7d: float) -> float:
    if flow_7d == 0:
        return 1.0
    avg_daily_7d = flow_7d / 7
    if avg_daily_7d == 0:
        return 1.0
    return flow_1d / avg_daily_7d


def compute_max_drawdown(prices: list) -> float:
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for price in prices:
        if price > peak:
            peak = price
        if peak > 0:
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def check_hard_failures(row: dict) -> list:
    failures = []
    if row['age_days'] < HARD_FAILURES['min_age_days']:
        failures.append("age")
    if row['holder_count'] < HARD_FAILURES['min_holders']:
        failures.append("holders")
    if row['owner_take'] > HARD_FAILURES['max_owner_take']:
        failures.append("owner_take")
    if row['startup_mode'] is True:
        failures.append("startup")
    if row['pool_tao_reserve'] > 0:
        flow_ratio = row['taoflow_7d'] / row['pool_tao_reserve']
        if flow_ratio < -HARD_FAILURES['max_negative_flow_ratio']:
            failures.append("outflow")
    return failures


def percentile_rank(values: list, target: float) -> float:
    if len(values) <= 1:
        return 50.0
    sorted_vals = sorted(values)
    rank = sum(1 for v in sorted_vals if v < target)
    return (rank / (len(sorted_vals) - 1)) * 100.0


def percentile_rank_inverted(values: list, target: float) -> float:
    if len(values) <= 1:
        return 50.0
    sorted_vals = sorted(values, reverse=True)
    rank = sum(1 for v in sorted_vals if v > target)
    return (rank / (len(sorted_vals) - 1)) * 100.0


def compute_viability_score(fai, emission, reserve, drawdown, all_fai, all_emission, all_reserve, all_drawdown):
    fai_pctile = percentile_rank(all_fai, fai)
    emission_pctile = percentile_rank(all_emission, emission)
    reserve_pctile = percentile_rank(all_reserve, reserve)
    drawdown_pctile = percentile_rank_inverted(all_drawdown, drawdown)

    score = (
        fai_pctile * VIABILITY_WEIGHTS['fai'] +
        emission_pctile * VIABILITY_WEIGHTS['emission_share'] +
        reserve_pctile * VIABILITY_WEIGHTS['tao_reserve'] +
        drawdown_pctile * VIABILITY_WEIGHTS['max_drawdown_30d']
    )
    return score


def get_fai_quintile(fai: float, all_fai: list) -> int:
    if len(all_fai) < 5:
        return 3
    sorted_fai = sorted(all_fai)
    n = len(sorted_fai)
    quintiles = [sorted_fai[int(n * q)] for q in [0.2, 0.4, 0.6, 0.8]]

    if fai <= quintiles[0]: return 1
    elif fai <= quintiles[1]: return 2
    elif fai <= quintiles[2]: return 3
    elif fai <= quintiles[3]: return 4
    else: return 5


async def run_backtest(data: list, viability_cutoff: float) -> dict:
    by_date = defaultdict(list)
    for row in data:
        by_date[row['date']].append(row)

    prices_by_netuid = defaultdict(list)
    for row in sorted(data, key=lambda x: x['date']):
        prices_by_netuid[row['netuid']].append({'date': row['date'], 'price': row['alpha_price_tao']})

    unique_dates = sorted(by_date.keys())
    rebalance_dates = unique_dates[::7]

    trades = []

    for rebal_date in rebalance_dates[:-3]:
        date_rows = by_date[rebal_date]
        if len(date_rows) < 10:
            continue

        subnet_data = []
        for row in date_rows:
            netuid = row['netuid']
            fai = calculate_fai(row['taoflow_1d'], row['taoflow_7d'])

            price_history = prices_by_netuid[netuid]
            recent_prices = [p['price'] for p in price_history if p['date'] <= rebal_date and p['date'] >= rebal_date - timedelta(days=30)]
            drawdown_30d = compute_max_drawdown(recent_prices) if recent_prices else 0

            hard_failures = check_hard_failures(row)
            if len(hard_failures) == 0:
                subnet_data.append({**row, 'fai': fai, 'drawdown_30d': drawdown_30d})

        if len(subnet_data) < 5:
            continue

        all_fai = [s['fai'] for s in subnet_data]
        all_emission = [s['emission_share'] for s in subnet_data]
        all_reserve = [s['pool_tao_reserve'] for s in subnet_data]
        all_drawdown = [s['drawdown_30d'] for s in subnet_data]

        for subnet in subnet_data:
            subnet['viability_score'] = compute_viability_score(
                subnet['fai'], subnet['emission_share'], subnet['pool_tao_reserve'],
                subnet['drawdown_30d'], all_fai, all_emission, all_reserve, all_drawdown
            )

        viable_subnets = [s for s in subnet_data if s['viability_score'] >= viability_cutoff]
        if len(viable_subnets) < 3:
            continue

        viable_fai = [s['fai'] for s in viable_subnets]
        for subnet in viable_subnets:
            subnet['fai_quintile'] = get_fai_quintile(subnet['fai'], viable_fai)

        exit_date = rebal_date + timedelta(days=HOLDING_PERIOD_DAYS)

        for subnet in viable_subnets:
            netuid = subnet['netuid']
            entry_price = subnet['alpha_price_tao']

            price_history = prices_by_netuid[netuid]
            exit_prices = [p['price'] for p in price_history if p['date'] >= exit_date]
            if not exit_prices:
                continue

            exit_price = exit_prices[0]
            raw_return = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

            quintile = subnet['fai_quintile']
            weight = FAI_QUINTILE_MULTIPLIERS[quintile]
            weighted_return = raw_return * weight

            trades.append({
                'entry_date': rebal_date,
                'netuid': netuid,
                'name': subnet['name'],
                'raw_return': raw_return,
                'fai': subnet['fai'],
                'fai_quintile': quintile,
                'weighted_return': weighted_return,
                'viability_score': subnet['viability_score'],
            })

    if not trades:
        return {'cutoff': viability_cutoff, 'total_trades': 0}

    weighted_returns = [t['weighted_return'] for t in trades]
    raw_returns = [t['raw_return'] for t in trades]

    # Cap extreme outliers at 500% for more stable metrics
    capped_returns = [min(5.0, max(-1.0, r)) for r in weighted_returns]

    avg_return = statistics.mean(weighted_returns)
    median_return = statistics.median(weighted_returns)
    capped_avg = statistics.mean(capped_returns)
    win_rate = sum(1 for r in weighted_returns if r > 0) / len(weighted_returns)
    std_return = statistics.stdev(capped_returns) if len(capped_returns) > 1 else 0.01
    sharpe = capped_avg / std_return * (26 ** 0.5) if std_return > 0 else 0

    # Percentile returns
    sorted_returns = sorted(weighted_returns)
    n = len(sorted_returns)
    p10 = sorted_returns[int(n * 0.1)] if n >= 10 else sorted_returns[0]
    p25 = sorted_returns[int(n * 0.25)] if n >= 4 else sorted_returns[0]
    p75 = sorted_returns[int(n * 0.75)] if n >= 4 else sorted_returns[-1]
    p90 = sorted_returns[int(n * 0.9)] if n >= 10 else sorted_returns[-1]

    return {
        'cutoff': viability_cutoff,
        'total_trades': len(trades),
        'unique_subnets': len(set(t['netuid'] for t in trades)),
        'avg_return': avg_return,
        'median_return': median_return,
        'capped_avg': capped_avg,
        'win_rate': win_rate,
        'sharpe': sharpe,
        'p10': p10,
        'p25': p25,
        'p75': p75,
        'p90': p90,
        'trades': trades,
    }


async def main():
    print("=" * 80)
    print("DETAILED VIABILITY CUTOFF ANALYSIS")
    print("=" * 80)
    print()

    data = await load_all_data()
    if not data:
        return

    print(f"Loaded {len(data)} snapshots\n")

    # Test finer granularity of cutoffs
    cutoffs = [30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]
    results = []

    for cutoff in cutoffs:
        result = await run_backtest(data, cutoff)
        results.append(result)
        print(f"Cutoff {cutoff}: {result['total_trades']} trades, "
              f"Median: {result.get('median_return', 0):.1%}, "
              f"Win: {result.get('win_rate', 0):.1%}")

    print()
    print("=" * 80)
    print("DETAILED RESULTS (using capped returns to handle outliers)")
    print("=" * 80)
    print()
    print(f"{'Cut':>4} {'Trades':>7} {'SNs':>4} {'Median':>8} {'CappedAvg':>10} {'Win%':>6} {'Sharpe':>7} {'P10':>8} {'P90':>8}")
    print("-" * 80)

    for r in results:
        if r['total_trades'] > 0:
            print(f"{r['cutoff']:>4} {r['total_trades']:>7} {r['unique_subnets']:>4} "
                  f"{r['median_return']:>7.1%} {r['capped_avg']:>9.1%} "
                  f"{r['win_rate']:>5.1%} {r['sharpe']:>7.2f} "
                  f"{r['p10']:>7.1%} {r['p90']:>7.1%}")

    # Find the "sweet spot" - balancing universe size with quality
    print()
    print("=" * 80)
    print("FINDING THE OPTIMAL CUTOFF")
    print("=" * 80)

    # Score each cutoff on multiple criteria
    valid_results = [r for r in results if r['total_trades'] >= 50]

    if valid_results:
        print("\nScoring cutoffs (min 50 trades for reliability):")
        print("-" * 60)

        # Normalize metrics for scoring
        max_sharpe = max(r['sharpe'] for r in valid_results)
        max_win = max(r['win_rate'] for r in valid_results)
        max_median = max(r['median_return'] for r in valid_results)
        max_trades = max(r['total_trades'] for r in valid_results)

        scored = []
        for r in valid_results:
            # Composite score: 40% Sharpe, 30% Win Rate, 20% Median, 10% Universe
            sharpe_score = r['sharpe'] / max_sharpe if max_sharpe > 0 else 0
            win_score = r['win_rate'] / max_win if max_win > 0 else 0
            median_score = (r['median_return'] + 1) / (max_median + 1) if max_median > -1 else 0  # Handle negatives
            universe_score = r['total_trades'] / max_trades

            composite = sharpe_score * 0.40 + win_score * 0.30 + median_score * 0.20 + universe_score * 0.10

            scored.append({
                **r,
                'sharpe_score': sharpe_score,
                'win_score': win_score,
                'median_score': median_score,
                'universe_score': universe_score,
                'composite': composite,
            })

            print(f"Cutoff {r['cutoff']:>2}: Sharpe={sharpe_score:.2f} Win={win_score:.2f} "
                  f"Med={median_score:.2f} Univ={universe_score:.2f} → Composite={composite:.3f}")

        best = max(scored, key=lambda x: x['composite'])

        print()
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        print(f"\nOptimal Viability Cutoff: {best['cutoff']}")
        print(f"  - Sharpe Ratio: {best['sharpe']:.2f}")
        print(f"  - Win Rate: {best['win_rate']:.1%}")
        print(f"  - Median Return: {best['median_return']:.1%}")
        print(f"  - Trade Universe: {best['total_trades']} opportunities ({best['unique_subnets']} subnets)")
        print()
        print("Binary Classification:")
        print(f"  - Viability Score >= {best['cutoff']} → VIABLE (include in trading)")
        print(f"  - Viability Score < {best['cutoff']} → NOT VIABLE (exclude)")

        # Show performance by viability band at optimal cutoff
        if best['trades']:
            print()
            print("Performance by Viability Score Band (at optimal cutoff):")
            print("-" * 60)

            trades = best['trades']
            bands = [(best['cutoff'], 60), (60, 70), (70, 80), (80, 100)]

            for low, high in bands:
                band_trades = [t for t in trades if low <= t['viability_score'] < high]
                if band_trades:
                    band_returns = [t['weighted_return'] for t in band_trades]
                    print(f"  {low}-{high}: {len(band_trades)} trades, "
                          f"Median: {statistics.median(band_returns):.1%}, "
                          f"Win: {sum(1 for r in band_returns if r > 0)/len(band_returns):.1%}")

    else:
        print("\nInsufficient data (need at least 50 trades per cutoff).")


if __name__ == "__main__":
    asyncio.run(main())
