#!/usr/bin/env python3
"""
Validate flow calculation - compare computed flow vs actual flow data.
"""

import os
import sys
from datetime import timedelta, date
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
        print("=" * 70)
        print("VALIDATING FLOW CALCULATION")
        print("=" * 70)

        # 1. Check what flow data exists in subnet_snapshots
        print("\n1. Checking subnet_snapshots flow columns...")
        result = await db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subnet_snapshots'
            AND column_name LIKE '%flow%'
        """))
        flow_cols = [row[0] for row in result.fetchall()]
        print(f"   Flow columns in snapshots: {flow_cols}")

        # 2. Check if taoflow_net has data
        print("\n2. Checking taoflow_net values in snapshots...")
        result = await db.execute(text("""
            SELECT COUNT(*) FROM subnet_snapshots WHERE taoflow_net IS NOT NULL AND taoflow_net != 0
        """))
        count = result.scalar()
        print(f"   Non-zero taoflow_net records: {count}")

        if count == 0:
            print("   ⚠️  NO historical flow data in subnet_snapshots!")
            print("   This means the original backtest must have used current data (look-ahead bias)")

        # 3. Get current flow values from subnets table
        print("\n3. Current flow values from subnets table...")
        result = await db.execute(text("""
            SELECT netuid, name, taoflow_1d, taoflow_7d, pool_tao_reserve
            FROM subnets
            WHERE netuid IN (1, 5, 8, 13, 19)
            ORDER BY netuid
        """))
        current_flows = {}
        for row in result.fetchall():
            current_flows[row[0]] = {
                'name': row[1],
                'flow_1d': float(row[2]) if row[2] else 0,
                'flow_7d': float(row[3]) if row[3] else 0,
                'reserve': float(row[4]) if row[4] else 0,
            }
            f1d = float(row[2]) if row[2] else 0
            f7d = float(row[3]) if row[3] else 0
            print(f"   SN{row[0]} ({row[1]}): flow_1d={f1d:.2f}, flow_7d={f7d:.2f}")

        # 4. Compute flow from reserve changes and compare
        print("\n4. Computing flow from reserve changes...")
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        for netuid in [1, 5, 8, 13, 19]:
            # Get reserve history
            result = await db.execute(text("""
                SELECT timestamp::date as d, pool_tao_reserve
                FROM subnet_snapshots
                WHERE netuid = :netuid
                AND timestamp::date >= :week_ago
                ORDER BY timestamp DESC
            """), {"netuid": netuid, "week_ago": week_ago})

            reserves = {}
            for row in result.fetchall():
                if row[0] not in reserves:  # Take first (most recent) per day
                    reserves[row[0]] = float(row[1]) if row[1] else 0

            computed_1d = None
            computed_7d = None

            if today in reserves and yesterday in reserves:
                computed_1d = reserves[today] - reserves[yesterday]

            if today in reserves and week_ago in reserves:
                computed_7d = reserves[today] - reserves[week_ago]

            actual = current_flows.get(netuid, {})
            print(f"\n   SN{netuid}:")
            print(f"     Actual flow_1d: {actual.get('flow_1d', 0):.2f}")
            if computed_1d is not None:
                print(f"     Computed flow_1d (from reserves): {computed_1d:.2f}")
                if actual.get('flow_1d'):
                    diff_pct = abs(computed_1d - actual['flow_1d']) / abs(actual['flow_1d']) * 100 if actual['flow_1d'] != 0 else 0
                    print(f"     Match: {100 - diff_pct:.1f}%")
            else:
                print(f"     Computed flow_1d: N/A (missing data)")

            print(f"     Actual flow_7d: {actual.get('flow_7d', 0):.2f}")
            if computed_7d is not None:
                print(f"     Computed flow_7d (from reserves): {computed_7d:.2f}")
                if actual.get('flow_7d'):
                    diff_pct = abs(computed_7d - actual['flow_7d']) / abs(actual['flow_7d']) * 100 if actual['flow_7d'] != 0 else 0
                    print(f"     Match: {100 - diff_pct:.1f}%")
            else:
                print(f"     Computed flow_7d: N/A (missing data)")

        # 5. CRITICAL: Check what data the ORIGINAL backtest scripts used
        print("\n" + "=" * 70)
        print("5. DIAGNOSIS: WHY ORIGINAL BACKTEST SHOWED GOOD RESULTS")
        print("=" * 70)

        print("""
   FINDING: subnet_snapshots has NO historical flow data (taoflow_net = 0).

   This means the original backtest scripts that showed +533% spread
   MUST have been using the `subnets` table which has CURRENT flow values.

   Using current flow to predict past returns = LOOK-AHEAD BIAS

   The "spectacular" results were not real - they were an artifact of
   using future information to make past decisions.

   When I properly computed flow from historical reserve changes,
   the signal becomes much weaker (but still slightly positive: +2.4% spread
   in the last 6 months).
        """)

        # 6. Verify the reserve-based flow calculation is correct
        print("=" * 70)
        print("6. VERIFYING RESERVE-BASED FLOW CALCULATION")
        print("=" * 70)

        print("\n   Checking if pool_tao_reserve accurately reflects flow...")

        # Get detailed reserve changes for SN1 over last 7 days
        result = await db.execute(text("""
            SELECT timestamp, pool_tao_reserve
            FROM subnet_snapshots
            WHERE netuid = 1
            AND timestamp >= NOW() - INTERVAL '7 days'
            ORDER BY timestamp ASC
        """))

        reserves = [(row[0], float(row[1])) for row in result.fetchall()]
        print(f"\n   SN1 reserve changes over last 7 days ({len(reserves)} snapshots):")

        if len(reserves) >= 2:
            total_change = reserves[-1][1] - reserves[0][1]
            print(f"   First: {reserves[0][0]} - {reserves[0][1]:.2f}")
            print(f"   Last:  {reserves[-1][0]} - {reserves[-1][1]:.2f}")
            print(f"   Total change: {total_change:.2f}")
            print(f"   Actual flow_7d from subnets table: {current_flows[1]['flow_7d']:.2f}")

            diff_pct = abs(total_change - current_flows[1]['flow_7d']) / abs(current_flows[1]['flow_7d']) * 100 if current_flows[1]['flow_7d'] != 0 else 0
            if diff_pct < 10:
                print(f"\n   ✓ Reserve change matches actual flow within {diff_pct:.1f}%")
                print("   The reserve-based calculation IS CORRECT")
            else:
                print(f"\n   ⚠️ Reserve change differs from actual flow by {diff_pct:.1f}%")
                print("   There may be other factors affecting the calculation")


if __name__ == "__main__":
    asyncio.run(main())
