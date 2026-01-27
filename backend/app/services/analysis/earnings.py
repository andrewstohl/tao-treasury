"""Earnings attribution service for Phase 2.

Computes earnings using the core identity:
    earnings_tao = (end_value_tao - start_value_tao) - net_flows_tao

Data sources:
- PositionSnapshot for start/end values
- DelegationEvent for net flows (stakes and unstakes)
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position, PositionSnapshot
from app.models.transaction import DelegationEvent, StakeTransaction

logger = structlog.get_logger()


class EarningsService:
    """Service for computing earnings attribution."""

    def __init__(self):
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def get_earnings_summary(
        self,
        start: datetime,
        end: datetime,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute earnings summary for a wallet over a time range.

        Args:
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            wallet_address: Wallet to analyze (defaults to configured wallet)

        Returns:
            Dictionary with total and per-netuid earnings breakdown
        """
        wallet = wallet_address or self.settings.wallet_address

        logger.info(
            "Computing earnings summary",
            wallet=wallet,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        async with get_db_context() as db:
            # Get all netuids with positions in this period
            netuids = await self._get_active_netuids(db, wallet, start, end)

            if not netuids:
                return self._empty_summary(start, end, wallet)

            # Compute earnings per netuid
            by_netuid = []
            total_start_value = Decimal("0")
            total_end_value = Decimal("0")
            total_net_flows = Decimal("0")
            total_earnings = Decimal("0")

            for netuid in netuids:
                result = await self._compute_netuid_earnings(
                    db, wallet, netuid, start, end
                )
                by_netuid.append(result)

                total_start_value += result["start_value_tao"]
                total_end_value += result["end_value_tao"]
                total_net_flows += result["net_flows_tao"]
                total_earnings += result["earnings_tao"]

            # Compute total metrics
            total_earnings_pct = Decimal("0")
            if total_start_value > 0:
                total_earnings_pct = (total_earnings / total_start_value) * Decimal("100")

            # Annualized APY estimate
            days = max((end - start).days, 1)
            annualized_apy = Decimal("0")
            if total_start_value > 0 and days > 0:
                daily_rate = total_earnings / total_start_value / Decimal(str(days))
                annualized_apy = daily_rate * Decimal("365") * Decimal("100")

            return {
                "wallet_address": wallet,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "period_days": days,
                "total_start_value_tao": str(total_start_value),
                "total_end_value_tao": str(total_end_value),
                "total_net_flows_tao": str(total_net_flows),
                "total_earnings_tao": str(total_earnings),
                "total_earnings_pct": str(round(total_earnings_pct, 4)),
                "total_annualized_apy_estimate": str(round(annualized_apy, 4)),
                "by_netuid": by_netuid,
            }

    async def get_earnings_timeseries(
        self,
        start: datetime,
        end: datetime,
        granularity: str = "day",
        wallet_address: Optional[str] = None,
        include_by_netuid: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Compute earnings timeseries for a wallet.

        Args:
            start: Start datetime
            end: End datetime
            granularity: "hour" or "day"
            wallet_address: Wallet to analyze
            include_by_netuid: Include per-netuid breakdown (can be heavy)

        Returns:
            Dictionary with array of time buckets
        """
        wallet = wallet_address or self.settings.wallet_address

        if include_by_netuid is None:
            include_by_netuid = self.settings.enable_earnings_timeseries_by_netuid

        logger.info(
            "Computing earnings timeseries",
            wallet=wallet,
            start=start.isoformat(),
            end=end.isoformat(),
            granularity=granularity,
        )

        # Generate time buckets
        if granularity == "hour":
            delta = timedelta(hours=1)
        else:
            delta = timedelta(days=1)

        buckets = []
        bucket_start = start

        while bucket_start < end:
            bucket_end = min(bucket_start + delta, end)

            async with get_db_context() as db:
                result = await self._compute_bucket_earnings(
                    db, wallet, bucket_start, bucket_end, include_by_netuid
                )
                result["bucket_start"] = bucket_start.isoformat()
                result["bucket_end"] = bucket_end.isoformat()
                buckets.append(result)

            bucket_start = bucket_end

        return {
            "wallet_address": wallet,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "granularity": granularity,
            "bucket_count": len(buckets),
            "buckets": buckets,
        }

    async def _get_active_netuids(
        self,
        db: AsyncSession,
        wallet: str,
        start: datetime,
        end: datetime,
    ) -> List[int]:
        """Get all netuids with activity in the time range."""
        # Check positions
        pos_stmt = select(Position.netuid).where(
            Position.wallet_address == wallet
        ).distinct()
        pos_result = await db.execute(pos_stmt)
        position_netuids = {row[0] for row in pos_result.fetchall()}

        # Check snapshots in range
        snap_stmt = select(PositionSnapshot.netuid).where(
            and_(
                PositionSnapshot.wallet_address == wallet,
                PositionSnapshot.timestamp >= start,
                PositionSnapshot.timestamp <= end,
            )
        ).distinct()
        snap_result = await db.execute(snap_stmt)
        snapshot_netuids = {row[0] for row in snap_result.fetchall()}

        # Check delegation events in range
        event_stmt = select(DelegationEvent.netuid).where(
            and_(
                DelegationEvent.wallet_address == wallet,
                DelegationEvent.timestamp >= start,
                DelegationEvent.timestamp <= end,
            )
        ).distinct()
        event_result = await db.execute(event_stmt)
        event_netuids = {row[0] for row in event_result.fetchall()}

        all_netuids = position_netuids | snapshot_netuids | event_netuids
        return sorted(list(all_netuids))

    async def _compute_netuid_earnings(
        self,
        db: AsyncSession,
        wallet: str,
        netuid: int,
        start: datetime,
        end: datetime,
    ) -> Dict[str, Any]:
        """Compute earnings for a single netuid.

        Core identity: earnings = end_value - start_value - net_flows
        """
        # Get start value (closest snapshot at or before start)
        start_value = await self._get_value_at_time(db, wallet, netuid, start, "before")

        # Get end value (closest snapshot at or before end)
        end_value = await self._get_value_at_time(db, wallet, netuid, end, "before")

        # Get net flows in period (positive = net deposit, negative = net withdrawal)
        net_flows = await self._get_net_flows(db, wallet, netuid, start, end)

        # Core earnings calculation
        earnings = end_value - start_value - net_flows

        # Compute percentage return
        earnings_pct = Decimal("0")
        if start_value > 0:
            earnings_pct = (earnings / start_value) * Decimal("100")

        # Annualized APY
        days = max((end - start).days, 1)
        annualized_apy = Decimal("0")
        if start_value > 0 and days > 0:
            daily_rate = earnings / start_value / Decimal(str(days))
            annualized_apy = daily_rate * Decimal("365") * Decimal("100")

        return {
            "netuid": netuid,
            "start_value_tao": start_value,
            "end_value_tao": end_value,
            "net_flows_tao": net_flows,
            "earnings_tao": earnings,
            "earnings_pct": str(round(earnings_pct, 4)),
            "annualized_apy_estimate": str(round(annualized_apy, 4)),
        }

    async def _get_value_at_time(
        self,
        db: AsyncSession,
        wallet: str,
        netuid: int,
        timestamp: datetime,
        direction: str = "before",
    ) -> Decimal:
        """Get position value at a specific timestamp.

        Uses the closest snapshot before/after the target timestamp.
        """
        if direction == "before":
            # Get latest snapshot at or before timestamp
            stmt = (
                select(PositionSnapshot)
                .where(
                    and_(
                        PositionSnapshot.wallet_address == wallet,
                        PositionSnapshot.netuid == netuid,
                        PositionSnapshot.timestamp <= timestamp,
                    )
                )
                .order_by(PositionSnapshot.timestamp.desc())
                .limit(1)
            )
        else:
            # Get earliest snapshot at or after timestamp
            stmt = (
                select(PositionSnapshot)
                .where(
                    and_(
                        PositionSnapshot.wallet_address == wallet,
                        PositionSnapshot.netuid == netuid,
                        PositionSnapshot.timestamp >= timestamp,
                    )
                )
                .order_by(PositionSnapshot.timestamp.asc())
                .limit(1)
            )

        result = await db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot:
            return snapshot.tao_value_mid

        # No snapshot found - check if position exists currently
        # If end time and no snapshot, use current position value
        if direction == "before":
            pos_stmt = select(Position).where(
                and_(
                    Position.wallet_address == wallet,
                    Position.netuid == netuid,
                )
            )
            pos_result = await db.execute(pos_stmt)
            position = pos_result.scalar_one_or_none()
            if position:
                return position.tao_value_mid

        return Decimal("0")

    async def _get_net_flows(
        self,
        db: AsyncSession,
        wallet: str,
        netuid: int,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        """Get net TAO flows for a netuid in a time range.

        Positive = net deposit (more staked than unstaked)
        Negative = net withdrawal (more unstaked than staked)
        """
        # Try DelegationEvent first (more accurate)
        event_stmt = select(DelegationEvent).where(
            and_(
                DelegationEvent.wallet_address == wallet,
                DelegationEvent.netuid == netuid,
                DelegationEvent.timestamp >= start,
                DelegationEvent.timestamp <= end,
            )
        )
        event_result = await db.execute(event_stmt)
        events = event_result.scalars().all()

        net_flows = Decimal("0")
        for event in events:
            if event.event_type == "stake":
                net_flows += event.amount_tao
            elif event.event_type == "unstake":
                net_flows -= event.amount_tao

        # If no delegation events, try StakeTransaction
        if not events:
            tx_stmt = select(StakeTransaction).where(
                and_(
                    StakeTransaction.wallet_address == wallet,
                    StakeTransaction.netuid == netuid,
                    StakeTransaction.timestamp >= start,
                    StakeTransaction.timestamp <= end,
                    StakeTransaction.success == True,
                )
            )
            tx_result = await db.execute(tx_stmt)
            transactions = tx_result.scalars().all()

            for tx in transactions:
                if tx.tx_type == "stake":
                    net_flows += tx.amount_tao
                elif tx.tx_type in ("unstake", "unstake_all"):
                    net_flows -= tx.amount_tao

        return net_flows

    async def _compute_bucket_earnings(
        self,
        db: AsyncSession,
        wallet: str,
        start: datetime,
        end: datetime,
        include_by_netuid: bool,
    ) -> Dict[str, Any]:
        """Compute earnings for a single time bucket."""
        netuids = await self._get_active_netuids(db, wallet, start, end)

        total_start_value = Decimal("0")
        total_end_value = Decimal("0")
        total_net_flows = Decimal("0")
        total_earnings = Decimal("0")

        by_netuid = []

        for netuid in netuids:
            result = await self._compute_netuid_earnings(db, wallet, netuid, start, end)

            total_start_value += result["start_value_tao"]
            total_end_value += result["end_value_tao"]
            total_net_flows += result["net_flows_tao"]
            total_earnings += result["earnings_tao"]

            if include_by_netuid:
                by_netuid.append(result)

        total_earnings_pct = Decimal("0")
        if total_start_value > 0:
            total_earnings_pct = (total_earnings / total_start_value) * Decimal("100")

        result = {
            "total_start_value_tao": str(total_start_value),
            "total_end_value_tao": str(total_end_value),
            "total_net_flows_tao": str(total_net_flows),
            "total_earnings_tao": str(total_earnings),
            "total_earnings_pct": str(round(total_earnings_pct, 4)),
        }

        if include_by_netuid:
            result["by_netuid"] = by_netuid

        return result

    def _empty_summary(
        self,
        start: datetime,
        end: datetime,
        wallet: str,
    ) -> Dict[str, Any]:
        """Return empty summary when no data exists."""
        days = max((end - start).days, 1)
        return {
            "wallet_address": wallet,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "period_days": days,
            "total_start_value_tao": "0",
            "total_end_value_tao": "0",
            "total_net_flows_tao": "0",
            "total_earnings_tao": "0",
            "total_earnings_pct": "0",
            "total_annualized_apy_estimate": "0",
            "by_netuid": [],
        }


# Lazy singleton
_earnings_service: Optional[EarningsService] = None


def get_earnings_service() -> EarningsService:
    """Get or create the EarningsService singleton."""
    global _earnings_service
    if _earnings_service is None:
        _earnings_service = EarningsService()
    return _earnings_service
