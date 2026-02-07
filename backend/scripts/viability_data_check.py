#!/usr/bin/env python3
"""
Check data quality for viability backtest.
Identify if we have look-ahead bias or data issues.
"""

import os
import sys
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
        print("DATA QUALITY CHECK")
        print("=" * 70)

        # Check what tables have historical data
        print("\n1. Checking for historical subnet data...")

        # Check subnet_snapshots columns
        result = await db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subnet_snapshots'
            ORDER BY ordinal_position
        """))
        snapshot_cols = [row[0] for row in result.fetchall()]
        print(f"\nSubnet_snapshots columns: {snapshot_cols}")

        # Check if snapshots have flow data
        result = await db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subnet_snapshots'
            AND column_name LIKE '%flow%'
        """))
        flow_cols = [row[0] for row in result.fetchall()]
        print(f"Flow columns in snapshots: {flow_cols}")

        # Check subnets table
        result = await db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subnets'
            AND (column_name LIKE '%flow%' OR column_name LIKE '%emission%' OR column_name = 'age_days')
        """))
        subnet_cols = [row[0] for row in result.fetchall()]
        print(f"\nSubnets table time-varying columns: {subnet_cols}")

        # Check if we have subnet history table
        result = await db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name LIKE '%subnet%history%' OR table_name LIKE '%subnet%snap%'
        """))
        history_tables = [row[0] for row in result.fetchall()]
        print(f"\nHistory-related tables: {history_tables}")

        # Sample subnet snapshots data
        print("\n2. Sample subnet_snapshots data:")
        result = await db.execute(text("""
            SELECT netuid, timestamp, alpha_price_tao
            FROM subnet_snapshots
            WHERE netuid = 1
            ORDER BY timestamp DESC
            LIMIT 5
        """))
        for row in result.fetchall():
            print(f"  SN{row[0]} @ {row[1]}: price={row[2]}")

        # Check current vs historical for a specific subnet
        print("\n3. Checking current subnet data (subnets table):")
        result = await db.execute(text("""
            SELECT netuid, name, age_days, holder_count, taoflow_1d, taoflow_7d, emission_share
            FROM subnets
            WHERE netuid IN (1, 5, 8)
        """))
        for row in result.fetchall():
            print(f"  SN{row[0]} ({row[1]}): age={row[2]}d, holders={row[3]}, "
                  f"flow1d={row[4]}, flow7d={row[5]}, emission={row[6]}")

        # THE KEY QUESTION: Are taoflow_1d, taoflow_7d in subnets table current or historical?
        print("\n4. CRITICAL: Checking if flow data changes over time...")
        print("   (If subnets table only has current values, we have look-ahead bias)")

        # Check if there's a subnet_metrics or subnet_history table
        result = await db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE '%subnet%'
        """))
        all_subnet_tables = [row[0] for row in result.fetchall()]
        print(f"\nAll subnet-related tables: {all_subnet_tables}")

        # Check if subnet_snapshots has flow columns
        result = await db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'subnet_snapshots'
        """))
        all_snapshot_cols = [row[0] for row in result.fetchall()]
        print(f"\nAll subnet_snapshots columns:\n  {all_snapshot_cols}")

        # Check the actual snapshot data
        print("\n5. Sample full snapshot record:")
        result = await db.execute(text("""
            SELECT *
            FROM subnet_snapshots
            WHERE netuid = 1
            ORDER BY timestamp DESC
            LIMIT 1
        """))
        row = result.fetchone()
        if row:
            keys = result.keys()
            for k, v in zip(keys, row):
                print(f"  {k}: {v}")

        print("\n" + "=" * 70)
        print("DIAGNOSIS")
        print("=" * 70)

        has_historical_flow = 'taoflow_1d' in all_snapshot_cols or 'tao_flow_1d' in all_snapshot_cols
        if has_historical_flow:
            print("\n✓ Subnet snapshots contain flow data - can do proper backtesting")
        else:
            print("\n✗ LOOK-AHEAD BIAS DETECTED!")
            print("  The subnets table contains current flow/metrics, not historical.")
            print("  Backtest is using FUTURE information to make past decisions.")
            print()
            print("  To fix: Need to either:")
            print("    1. Use subnet_snapshots for all time-varying metrics, or")
            print("    2. Create a subnet_metrics_history table")


if __name__ == "__main__":
    asyncio.run(main())
