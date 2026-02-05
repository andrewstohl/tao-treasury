"""Historical data backfill service.

Pulls historical pool data from TaoStats pool_history API
and creates SubnetSnapshot records for backtesting.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context
from app.models.subnet import Subnet, SubnetSnapshot
from app.services.data.taostats_client import taostats_client, TaoStatsError

logger = structlog.get_logger()

# 1 TAO = 1e9 rao
RAO_PER_TAO = Decimal("1000000000")


def _rao_to_tao(rao: str | int | Decimal) -> Decimal:
    return Decimal(str(rao)) / RAO_PER_TAO


class BackfillStatus:
    """Tracks backfill progress."""

    def __init__(self):
        self.running = False
        self.total_subnets = 0
        self.completed_subnets = 0
        self.total_records_created = 0
        self.total_records_skipped = 0
        self.errors: List[str] = []
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.current_netuid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "total_subnets": self.total_subnets,
            "completed_subnets": self.completed_subnets,
            "total_records_created": self.total_records_created,
            "total_records_skipped": self.total_records_skipped,
            "errors": self.errors[-20:],  # last 20 errors
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "current_netuid": self.current_netuid,
        }


# Module-level status singleton
_backfill_status = BackfillStatus()


def get_backfill_status() -> BackfillStatus:
    return _backfill_status


class HistoryBackfillService:
    """Backfills SubnetSnapshot records from TaoStats pool_history API."""

    # Pool history returns daily snapshots. Typical record count per subnet: ~350.
    PAGE_SIZE = 100

    def __init__(self):
        self.status = _backfill_status

    async def backfill(
        self,
        lookback_days: int = 365,
        netuids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Run historical backfill for all (or specified) subnets.

        Args:
            lookback_days: How many days of history to fetch.
            netuids: Optional list of specific netuids. If None, uses all known subnets.

        Returns:
            Summary dict with counts.
        """
        if self.status.running:
            return {"error": "Backfill already running", **self.status.to_dict()}

        self.status = BackfillStatus()
        # Re-assign module singleton
        global _backfill_status
        _backfill_status = self.status

        self.status.running = True
        self.status.started_at = datetime.now(timezone.utc)

        try:
            async with get_db_context() as db:
                # Determine which subnets to backfill
                if netuids:
                    target_netuids = netuids
                else:
                    stmt = select(Subnet.netuid).order_by(Subnet.netuid)
                    result = await db.execute(stmt)
                    target_netuids = [row[0] for row in result.fetchall()]

                self.status.total_subnets = len(target_netuids)

                logger.info(
                    "Starting historical backfill",
                    subnet_count=len(target_netuids),
                    lookback_days=lookback_days,
                )

                now = datetime.now(timezone.utc)
                start_time = now - timedelta(days=lookback_days)

                for netuid in target_netuids:
                    self.status.current_netuid = netuid
                    try:
                        created, skipped = await self._backfill_subnet(
                            db, netuid, start_time, now
                        )
                        self.status.total_records_created += created
                        self.status.total_records_skipped += skipped
                    except Exception as e:
                        error_msg = f"Subnet {netuid}: {str(e)}"
                        self.status.errors.append(error_msg)
                        logger.error("Backfill failed for subnet", netuid=netuid, error=str(e))

                    self.status.completed_subnets += 1

                    # Commit after each subnet
                    await db.commit()

        except Exception as e:
            self.status.errors.append(f"Fatal: {str(e)}")
            logger.error("Backfill fatal error", error=str(e))
        finally:
            self.status.running = False
            self.status.finished_at = datetime.now(timezone.utc)
            self.status.current_netuid = None

        summary = self.status.to_dict()
        logger.info(
            "Backfill complete",
            created=self.status.total_records_created,
            skipped=self.status.total_records_skipped,
            errors=len(self.status.errors),
        )
        return summary

    async def _backfill_subnet(
        self,
        db: AsyncSession,
        netuid: int,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[int, int]:
        """Backfill history for a single subnet.

        Returns:
            (records_created, records_skipped)
        """
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())

        # Get existing snapshot timestamps for this subnet to avoid duplicates
        stmt = (
            select(SubnetSnapshot.timestamp)
            .where(SubnetSnapshot.netuid == netuid)
            .where(SubnetSnapshot.timestamp >= start_time)
        )
        result = await db.execute(stmt)
        existing_dates = set()
        for row in result.fetchall():
            # Normalize to date for dedup (pool_history returns daily snapshots)
            existing_dates.add(row[0].date())

        created = 0
        skipped = 0
        page = 1

        while True:
            try:
                resp = await taostats_client.get_pool_history(
                    netuid=netuid,
                    timestamp_start=start_ts,
                    timestamp_end=end_ts,
                    limit=self.PAGE_SIZE,
                )
            except TaoStatsError as e:
                logger.warning("API error during backfill", netuid=netuid, page=page, error=str(e))
                break

            data = resp.get("data", [])
            pagination = resp.get("pagination", {})

            if not data:
                break

            for record in data:
                ts_str = record.get("timestamp")
                if not ts_str:
                    continue

                # Parse timestamp
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                record_date = ts.date()

                # Skip if we already have a snapshot for this date
                if record_date in existing_dates:
                    skipped += 1
                    continue

                # Create SubnetSnapshot from pool_history record
                snapshot = self._build_snapshot(netuid, ts, record)
                db.add(snapshot)
                existing_dates.add(record_date)
                created += 1

            # Check if there are more pages
            next_page = pagination.get("next_page")
            if not next_page or len(data) < self.PAGE_SIZE:
                break

            # For pagination, adjust end_ts to before the oldest record in current page
            # The API returns newest-first, so the last record is the oldest
            oldest_ts_str = data[-1].get("timestamp", "")
            if oldest_ts_str:
                oldest_ts = datetime.fromisoformat(oldest_ts_str.replace("Z", "+00:00"))
                end_ts = int(oldest_ts.timestamp()) - 1
            else:
                break

            page += 1

            # Small delay between pages to be gentle on the API
            await asyncio.sleep(0.2)

        logger.info(
            "Subnet backfill done",
            netuid=netuid,
            created=created,
            skipped=skipped,
        )
        return created, skipped

    def _build_snapshot(
        self, netuid: int, timestamp: datetime, record: Dict[str, Any]
    ) -> SubnetSnapshot:
        """Build a SubnetSnapshot from a pool_history API record."""
        price = Decimal(str(record.get("price", 0) or 0))
        total_tao = record.get("total_tao", 0) or 0
        total_alpha = record.get("total_alpha", 0) or 0

        # root_prop is emission share (proportion of root network weight)
        root_prop = record.get("root_prop")
        emission_share = Decimal(str(root_prop)) if root_prop else Decimal("0")

        return SubnetSnapshot(
            netuid=netuid,
            timestamp=timestamp,
            alpha_price_tao=price,
            pool_tao_reserve=_rao_to_tao(total_tao),
            pool_alpha_reserve=_rao_to_tao(total_alpha),
            emission_share=emission_share,
            taoflow_net=Decimal("0"),  # Not available in pool_history; backtest computes from reserves
            holder_count=0,  # Not available in pool_history
            validator_apy=Decimal("0"),  # Not available in pool_history
            flow_regime="unknown",
        )
