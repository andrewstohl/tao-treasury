#!/usr/bin/env python3
"""Debug version to see what's filtering out trades."""

import os
import sys
from datetime import timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tao_treasury")
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def main():
    async with async_session() as db:
        # Get daily snapshots
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

        print(f"Total snapshots: {len(rows)}")

        # Build by netuid
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

        # Check sample subnet
        sample_netuid = list(data_by_netuid.keys())[0]
        sample_history = data_by_netuid[sample_netuid]
        print(f"\nSample subnet {sample_netuid}:")
        print(f"  Total records: {len(sample_history)}")
        print(f"  Date range: {sample_history[0]['date']} to {sample_history[-1]['date']}")
        print(f"  Sample record: {sample_history[-1]}")

        # Pick a test date
        test_date = sample_history[-30]['date'] if len(sample_history) >= 30 else sample_history[len(sample_history)//2]['date']
        print(f"\nTesting date: {test_date}")

        # Try to compute flow
        def get_record_for_date(history, target_date):
            for record in history:
                if record['date'] == target_date:
                    return record
            return None

        def compute_flow(history, target_date, days_back):
            target_record = get_record_for_date(history, target_date)
            past_date = target_date - timedelta(days=days_back)
            past_record = get_record_for_date(history, past_date)

            if target_record and past_record:
                return target_record['reserve'] - past_record['reserve']
            return None

        record = get_record_for_date(sample_history, test_date)
        print(f"Record for {test_date}: {record}")

        flow_1d = compute_flow(sample_history, test_date, 1)
        flow_7d = compute_flow(sample_history, test_date, 7)
        print(f"Flow 1d: {flow_1d}")
        print(f"Flow 7d: {flow_7d}")

        # Check holder counts
        print("\n\nHolder counts across subnets on test date:")
        holder_counts = []
        for netuid, history in data_by_netuid.items():
            record = get_record_for_date(history, test_date)
            if record:
                holder_counts.append((netuid, record['holder_count']))

        holder_counts.sort(key=lambda x: x[1], reverse=True)
        for netuid, count in holder_counts[:10]:
            print(f"  SN{netuid}: {count} holders")

        print(f"\nSubnets with >= 50 holders: {sum(1 for _, c in holder_counts if c >= 50)}")
        print(f"Subnets with >= 10 holders: {sum(1 for _, c in holder_counts if c >= 10)}")
        print(f"Subnets with > 0 holders: {sum(1 for _, c in holder_counts if c > 0)}")

        # Get owner_take from subnets table
        meta_result = await db.execute(text("SELECT netuid, owner_take FROM subnets"))
        owner_takes = {row[0]: float(row[1]) if row[1] else 0 for row in meta_result.fetchall()}

        print("\n\nOwner takes:")
        sorted_takes = sorted(owner_takes.items(), key=lambda x: x[1], reverse=True)[:10]
        for netuid, take in sorted_takes:
            print(f"  SN{netuid}: {take:.1%}")
        print(f"\nSubnets with owner_take <= 18%: {sum(1 for _, t in owner_takes.items() if t <= 0.18)}")

        # Count subnets passing all hard failures
        print("\n\nHard failure analysis for test date:")
        failures_count = defaultdict(int)
        passing = 0

        for netuid, history in data_by_netuid.items():
            record = get_record_for_date(history, test_date)
            if not record:
                failures_count['no_record'] += 1
                continue

            # Age
            first_date = min(r['date'] for r in history)
            age_days = (test_date - first_date).days

            failures = []
            if age_days < 14:
                failures.append('age')
            if record['holder_count'] < 50:
                failures.append('holders')
            if owner_takes.get(netuid, 0) > 0.18:
                failures.append('owner_take')

            # Flow check
            flow_7d = compute_flow(history, test_date, 7)
            if flow_7d is not None and record['reserve'] > 0:
                if flow_7d / record['reserve'] < -0.5:
                    failures.append('outflow')

            if failures:
                for f in failures:
                    failures_count[f] += 1
            else:
                passing += 1

        print(f"Passing all hard failures: {passing}")
        print("Failure reasons:")
        for reason, count in sorted(failures_count.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
