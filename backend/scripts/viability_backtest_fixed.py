#!/usr/bin/env python3
"""
FIXED Viability Cutoff Backtest

Properly computes historical flow from pool_tao_reserve changes,
avoiding look-ahead bias.

Flow calculation:
- flow_1d = reserve_today - reserve_yesterday
- flow_7d = reserve_today - reserve_7d_ago

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

HARD_FAILURES = {
    "min_age_days": 14,
    "min_holders": 50,
    "max_owner_take": 0.18,  # Can't check without historical data
    "max_negative_flow_ratio": 0.50,
}

HOLDING_PERIOD_DAYS = 14
FAI_QUINTILE_MULTIPLIERS = {1: 0.2, 2: 0.5, 3: 1.0, 4: 1.5, 5: 2.5}


async def load_snapshot_data():
    """Load subnet snapshots - the source of truth for historical data."""
    async with async_session() as db:
        # Get one snapshot per day per subnet (to speed up processing)
        query = text("""
            WITH daily_snapshots AS (
                SELECT DISTINCT ON (netuid, timestamp::date)
                    netuid,
                    timestamp::date as snap_date,
                    alpha_price_tao,
                    pool_tao_reserve,
                    emission_share,
                    holder_count
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

        if not rows:
            print("No snapshot data found")
            return None

        # Build indexed structure
        data_by_netuid = defaultdict(list)
        for row in rows:
            data_by_netuid[row[0]].append({
                'netuid': row[0],
                'date': row[1],
                'price': float(row[2]) if row[2] else 0,
                'reserve': float(row[3]) if row[3] else 0,
                'emission_share': float(row[4]) if row[4] else 0,
                'holder_count': int(row[5]) if row[5] else 0,
            })

        dates = sorted(set(row[1] for row in rows))
        netuids = set(row[0] for row in rows)

        print(f"Loaded snapshots for {len(netuids)} subnets")
        print(f"Date range: {dates[0]} to {dates[-1]}")
        print(f"Total days: {len(dates)}")

        # Get subnet metadata for owner_take (static check only)
        meta_query = text("""
            SELECT netuid, owner_take, name
            FROM subnets
        """)
        meta_result = await db.execute(meta_query)
        metadata = {row[0]: {'owner_take': float(row[1]) if row[1] else 0, 'name': row[2]} for row in meta_result.fetchall()}

        return data_by_netuid, dates, metadata


def compute_flow_from_reserve(history: list, target_date, days_back: int) -> float:
    """Compute flow by comparing reserve at target_date vs days_back."""
    # Find reserve at target date
    target_reserve = None
    past_reserve = None
    past_date = target_date - timedelta(days=days_back)

    for record in history:
        if record['date'] == target_date:
            target_reserve = record['reserve']
        if record['date'] == past_date:
            past_reserve = record['reserve']
        # Also accept closest date within 1 day
        if target_reserve is None and abs((record['date'] - target_date).days) <= 1:
            target_reserve = record['reserve']
        if past_reserve is None and abs((record['date'] - past_date).days) <= 1:
            past_reserve = record['reserve']

    if target_reserve is None or past_reserve is None:
        return 0.0

    return target_reserve - past_reserve


def get_record_for_date(history: list, target_date):
    """Get snapshot record for a specific date (or closest)."""
    for record in history:
        if record['date'] == target_date:
            return record
    # Try closest
    for record in history:
        if abs((record['date'] - target_date).days) <= 1:
            return record
    return None


def calculate_fai(flow_1d: float, flow_7d: float) -> float:
    if flow_7d == 0:
        return 1.0
    avg_daily_7d = flow_7d / 7
    if avg_daily_7d == 0:
        return 1.0
    return flow_1d / avg_daily_7d


def compute_max_drawdown(history: list, end_date, lookback_days: int = 30) -> float:
    """Compute max drawdown from price history."""
    start_date = end_date - timedelta(days=lookback_days)
    prices = [r['price'] for r in history if start_date <= r['date'] <= end_date]

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


def compute_age_days(history: list, target_date) -> int:
    """Compute subnet age as days since first snapshot."""
    if not history:
        return 0
    first_date = min(r['date'] for r in history)
    return (target_date - first_date).days


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


async def run_backtest(data_by_netuid, dates, metadata, viability_cutoff: float) -> dict:
    """Run backtest with proper historical data."""

    # Weekly rebalance dates
    rebalance_dates = dates[14::7]  # Start after 14 days for flow calc, weekly

    trades = []

    for rebal_date in rebalance_dates[:-3]:  # Leave room for holding period
        # Gather data for all subnets on this date
        subnet_data = []

        for netuid, history in data_by_netuid.items():
            record = get_record_for_date(history, rebal_date)
            if not record:
                continue

            # Compute historical flow
            flow_1d = compute_flow_from_reserve(history, rebal_date, 1)
            flow_7d = compute_flow_from_reserve(history, rebal_date, 7)
            fai = calculate_fai(flow_1d, flow_7d)

            # Compute historical drawdown
            drawdown_30d = compute_max_drawdown(history, rebal_date, 30)

            # Compute age
            age_days = compute_age_days(history, rebal_date)

            # Get static metadata
            meta = metadata.get(netuid, {})
            owner_take = meta.get('owner_take', 0)
            name = meta.get('name', f'SN{netuid}')

            # Hard failure checks
            failures = []
            if age_days < HARD_FAILURES['min_age_days']:
                failures.append("age")
            if record['holder_count'] < HARD_FAILURES['min_holders']:
                failures.append("holders")
            if owner_take > HARD_FAILURES['max_owner_take']:
                failures.append("owner_take")
            if record['reserve'] > 0 and flow_7d / record['reserve'] < -HARD_FAILURES['max_negative_flow_ratio']:
                failures.append("outflow")

            if len(failures) == 0:
                subnet_data.append({
                    'netuid': netuid,
                    'name': name,
                    'date': rebal_date,
                    'price': record['price'],
                    'reserve': record['reserve'],
                    'emission_share': record['emission_share'],
                    'holder_count': record['holder_count'],
                    'flow_1d': flow_1d,
                    'flow_7d': flow_7d,
                    'fai': fai,
                    'drawdown_30d': drawdown_30d,
                    'age_days': age_days,
                })

        if len(subnet_data) < 5:
            continue

        # Compute viability scores
        all_fai = [s['fai'] for s in subnet_data]
        all_emission = [s['emission_share'] for s in subnet_data]
        all_reserve = [s['reserve'] for s in subnet_data]
        all_drawdown = [s['drawdown_30d'] for s in subnet_data]

        for subnet in subnet_data:
            subnet['viability_score'] = compute_viability_score(
                subnet['fai'], subnet['emission_share'], subnet['reserve'],
                subnet['drawdown_30d'], all_fai, all_emission, all_reserve, all_drawdown
            )

        # Filter by viability cutoff
        viable_subnets = [s for s in subnet_data if s['viability_score'] >= viability_cutoff]
        if len(viable_subnets) < 3:
            continue

        # Assign FAI quintiles
        viable_fai = [s['fai'] for s in viable_subnets]
        for subnet in viable_subnets:
            subnet['fai_quintile'] = get_fai_quintile(subnet['fai'], viable_fai)

        # Calculate forward returns
        exit_date = rebal_date + timedelta(days=HOLDING_PERIOD_DAYS)

        for subnet in viable_subnets:
            netuid = subnet['netuid']
            entry_price = subnet['price']

            history = data_by_netuid[netuid]
            exit_record = get_record_for_date(history, exit_date)
            if not exit_record:
                continue

            exit_price = exit_record['price']
            raw_return = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

            quintile = subnet['fai_quintile']
            weight = FAI_QUINTILE_MULTIPLIERS[quintile]
            weighted_return = raw_return * weight

            trades.append({
                'entry_date': rebal_date,
                'exit_date': exit_date,
                'netuid': netuid,
                'name': subnet['name'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'raw_return': raw_return,
                'fai': subnet['fai'],
                'flow_1d': subnet['flow_1d'],
                'flow_7d': subnet['flow_7d'],
                'fai_quintile': quintile,
                'weight': weight,
                'weighted_return': weighted_return,
                'viability_score': subnet['viability_score'],
            })

    if not trades:
        return {'cutoff': viability_cutoff, 'total_trades': 0}

    weighted_returns = [t['weighted_return'] for t in trades]
    raw_returns = [t['raw_return'] for t in trades]

    # Cap extremes
    capped_returns = [min(5.0, max(-1.0, r)) for r in weighted_returns]

    avg_return = statistics.mean(weighted_returns)
    median_return = statistics.median(weighted_returns)
    capped_avg = statistics.mean(capped_returns)
    win_rate = sum(1 for r in weighted_returns if r > 0) / len(weighted_returns)
    std_return = statistics.stdev(capped_returns) if len(capped_returns) > 1 else 0.01
    sharpe = capped_avg / std_return * (26 ** 0.5) if std_return > 0 else 0

    return {
        'cutoff': viability_cutoff,
        'total_trades': len(trades),
        'unique_subnets': len(set(t['netuid'] for t in trades)),
        'avg_return': avg_return,
        'median_return': median_return,
        'capped_avg': capped_avg,
        'win_rate': win_rate,
        'sharpe': sharpe,
        'trades': trades,
    }


async def main():
    print("=" * 80)
    print("FIXED VIABILITY CUTOFF BACKTEST")
    print("(Computing historical flow from reserve changes - no look-ahead bias)")
    print("=" * 80)
    print()

    result = await load_snapshot_data()
    if not result:
        return

    data_by_netuid, dates, metadata = result

    print()
    print("=" * 80)
    print("TESTING VIABILITY CUTOFFS")
    print("=" * 80)

    cutoffs = [30, 40, 50, 60, 70, 80]
    results = []

    for cutoff in cutoffs:
        print(f"\nTesting cutoff: {cutoff}...")
        result = await run_backtest(data_by_netuid, dates, metadata, cutoff)
        results.append(result)

        if result['total_trades'] > 0:
            print(f"  Trades: {result['total_trades']}")
            print(f"  Median Return: {result['median_return']:.1%}")
            print(f"  Win Rate: {result['win_rate']:.1%}")
            print(f"  Sharpe: {result['sharpe']:.2f}")
        else:
            print("  No trades")

    print()
    print("=" * 80)
    print("RESULTS SUMMARY (FIXED - No Look-Ahead Bias)")
    print("=" * 80)
    print()
    print(f"{'Cut':>4} {'Trades':>7} {'SNs':>4} {'Median':>8} {'Mean':>8} {'Win%':>6} {'Sharpe':>7}")
    print("-" * 55)

    for r in results:
        if r['total_trades'] > 0:
            print(f"{r['cutoff']:>4} {r['total_trades']:>7} {r['unique_subnets']:>4} "
                  f"{r['median_return']:>7.1%} {r['avg_return']:>7.1%} "
                  f"{r['win_rate']:>5.1%} {r['sharpe']:>7.2f}")
        else:
            print(f"{r['cutoff']:>4}       0   --      --       --     --      --")

    # Find best
    valid_results = [r for r in results if r['total_trades'] >= 30]
    if valid_results:
        best_sharpe = max(valid_results, key=lambda x: x['sharpe'])
        best_winrate = max(valid_results, key=lambda x: x['win_rate'])
        best_median = max(valid_results, key=lambda x: x['median_return'])

        print()
        print("=" * 80)
        print("ANALYSIS")
        print("=" * 80)
        print(f"\nBest Sharpe: Cutoff {best_sharpe['cutoff']} (Sharpe: {best_sharpe['sharpe']:.2f})")
        print(f"Best Win Rate: Cutoff {best_winrate['cutoff']} (Win Rate: {best_winrate['win_rate']:.1%})")
        print(f"Best Median: Cutoff {best_median['cutoff']} (Median: {best_median['median_return']:.1%})")

        # Detailed breakdown for best Sharpe
        if best_sharpe['trades']:
            print()
            print(f"Quintile Breakdown (Cutoff {best_sharpe['cutoff']}):")
            print("-" * 50)
            trades = best_sharpe['trades']
            for q in range(1, 6):
                q_trades = [t for t in trades if t['fai_quintile'] == q]
                if q_trades:
                    q_returns = [t['weighted_return'] for t in q_trades]
                    print(f"  Q{q}: {len(q_trades)} trades, "
                          f"Median: {statistics.median(q_returns):.1%}, "
                          f"Win: {sum(1 for r in q_returns if r > 0)/len(q_returns):.1%}")

        print()
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)

        # Balanced recommendation
        recommended = max(valid_results, key=lambda x: x['sharpe'] * 0.5 + x['win_rate'] * 0.3 + (x['median_return'] + 0.5) * 0.2)
        print(f"\nRecommended Viability Cutoff: {recommended['cutoff']}")
        print(f"  - Sharpe Ratio: {recommended['sharpe']:.2f}")
        print(f"  - Win Rate: {recommended['win_rate']:.1%}")
        print(f"  - Median Return: {recommended['median_return']:.1%}")
        print(f"  - Universe: {recommended['total_trades']} trades ({recommended['unique_subnets']} subnets)")
    else:
        print("\nInsufficient data for reliable conclusions.")


if __name__ == "__main__":
    asyncio.run(main())
