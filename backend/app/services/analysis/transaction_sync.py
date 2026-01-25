"""Transaction sync service for fetching and storing stake transactions."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.transaction import StakeTransaction
from app.services.data.taostats_client import taostats_client

settings = get_settings()
logger = structlog.get_logger()

# 1 TAO = 1e9 rao
RAO_PER_TAO = Decimal("1000000000")


def rao_to_tao(rao: str | int | Decimal) -> Decimal:
    """Convert rao to TAO."""
    return Decimal(str(rao)) / RAO_PER_TAO


# Staking-related call names
STAKE_CALLS = {
    "SubtensorModule.add_stake",
    "SubtensorModule.add_stake_limit",
    "SubtensorModule.add_stake_multiple",
}

UNSTAKE_CALLS = {
    "SubtensorModule.remove_stake",
    "SubtensorModule.remove_stake_limit",
    "SubtensorModule.unstake_all",
    "SubtensorModule.unstake_all_alpha",
}


def parse_hotkey(hotkey_data: Any) -> Optional[str]:
    """Extract hotkey SS58 address from various formats."""
    if hotkey_data is None:
        return None
    if isinstance(hotkey_data, str):
        # Already a string (hex or ss58)
        return hotkey_data
    if isinstance(hotkey_data, dict):
        # Nested structure like {"__kind": "Id", "value": "0x..."}
        return hotkey_data.get("value") or hotkey_data.get("ss58")
    return None


class TransactionSyncService:
    """Service for syncing stake transactions from TaoStats."""

    def __init__(self):
        self.wallet_address = settings.wallet_address
        self._last_sync: Optional[datetime] = None

    async def sync_transactions(self, full_sync: bool = False) -> Dict[str, Any]:
        """Sync stake transactions from TaoStats.

        Args:
            full_sync: If True, fetch all transactions. If False, only fetch new ones.

        Returns:
            Dict with sync results
        """
        logger.info("Starting transaction sync", wallet=self.wallet_address, full_sync=full_sync)

        results = {
            "total_fetched": 0,
            "new_transactions": 0,
            "stake_transactions": 0,
            "unstake_transactions": 0,
            "errors": [],
        }

        try:
            # Determine starting point
            last_block = 0
            if not full_sync:
                last_block = await self._get_last_synced_block()

            # Fetch extrinsics from TaoStats
            extrinsics = await taostats_client.get_all_extrinsics(
                address=self.wallet_address,
                max_pages=500 if full_sync else 50,
            )

            results["total_fetched"] = len(extrinsics)
            logger.info("Fetched extrinsics", count=len(extrinsics))

            # Filter and process staking transactions
            async with get_db_context() as db:
                for ex in extrinsics:
                    # Skip if already synced
                    block_num = ex.get("block_number", 0)
                    if block_num <= last_block and not full_sync:
                        continue

                    # Check if this is a staking transaction
                    call_name = ex.get("full_name", "")
                    if call_name in STAKE_CALLS:
                        tx = await self._process_stake_transaction(db, ex, "stake")
                        if tx:
                            results["stake_transactions"] += 1
                            results["new_transactions"] += 1
                    elif call_name in UNSTAKE_CALLS:
                        tx = await self._process_stake_transaction(db, ex, "unstake")
                        if tx:
                            results["unstake_transactions"] += 1
                            results["new_transactions"] += 1

                await db.commit()

            self._last_sync = datetime.now(timezone.utc)
            logger.info("Transaction sync completed", results=results)

        except Exception as e:
            logger.error("Transaction sync failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def _get_last_synced_block(self) -> int:
        """Get the block number of the last synced transaction."""
        async with get_db_context() as db:
            stmt = select(func.max(StakeTransaction.block_number)).where(
                StakeTransaction.wallet_address == self.wallet_address
            )
            result = await db.execute(stmt)
            last_block = result.scalar()
            return last_block or 0

    async def _process_stake_transaction(
        self,
        db: AsyncSession,
        extrinsic: Dict,
        tx_type: str
    ) -> Optional[StakeTransaction]:
        """Process and store a stake/unstake transaction."""
        extrinsic_id = extrinsic.get("id")
        if not extrinsic_id:
            return None

        # Check if already exists
        stmt = select(StakeTransaction).where(StakeTransaction.extrinsic_id == extrinsic_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return None  # Already synced

        # Parse transaction data
        call_args = extrinsic.get("call_args", {})
        call_name = extrinsic.get("full_name", "")

        # Extract netuid
        netuid = call_args.get("netuid")
        if netuid is None:
            # Some calls might have it nested
            return None

        # Extract amount
        if tx_type == "stake":
            amount_rao = call_args.get("amountStaked", 0) or call_args.get("amount", 0) or 0
        else:
            amount_rao = call_args.get("amountUnstaked", 0) or call_args.get("amount", 0) or 0

        amount_tao = rao_to_tao(amount_rao)

        # Extract hotkey
        hotkey = parse_hotkey(call_args.get("hotkey"))

        # Extract limit price (price per alpha in some unit)
        limit_price_raw = call_args.get("limitPrice")
        limit_price = None
        if limit_price_raw is not None:
            # Convert from raw units - typically needs to be divided by 1e9
            limit_price = Decimal(str(limit_price_raw)) / RAO_PER_TAO

        # Parse timestamp
        timestamp_str = extrinsic.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(timezone.utc)

        # Extract fee
        fee_rao = int(extrinsic.get("fee", 0) or 0)
        fee_tao = rao_to_tao(fee_rao)

        # Create transaction record
        tx = StakeTransaction(
            wallet_address=self.wallet_address,
            extrinsic_id=extrinsic_id,
            block_number=extrinsic.get("block_number", 0),
            timestamp=timestamp,
            tx_hash=extrinsic.get("hash"),
            tx_type=tx_type,
            call_name=call_name,
            netuid=netuid,
            hotkey=hotkey,
            amount_tao=amount_tao,
            limit_price=limit_price,
            fee_rao=fee_rao,
            fee_tao=fee_tao,
            success=extrinsic.get("success", True),
            error_message=extrinsic.get("error"),
            raw_args=call_args,
        )

        db.add(tx)
        logger.debug(
            "Added stake transaction",
            type=tx_type,
            netuid=netuid,
            amount=amount_tao,
            price=limit_price,
        )

        return tx

    async def get_transactions_by_netuid(self, netuid: int) -> List[StakeTransaction]:
        """Get all transactions for a specific subnet."""
        async with get_db_context() as db:
            stmt = (
                select(StakeTransaction)
                .where(
                    StakeTransaction.wallet_address == self.wallet_address,
                    StakeTransaction.netuid == netuid,
                )
                .order_by(StakeTransaction.timestamp)
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def get_transaction_summary(self) -> Dict[str, Any]:
        """Get summary of all transactions."""
        async with get_db_context() as db:
            # Count by type
            stmt = select(
                StakeTransaction.tx_type,
                func.count(StakeTransaction.id),
                func.sum(StakeTransaction.amount_tao),
            ).where(
                StakeTransaction.wallet_address == self.wallet_address
            ).group_by(StakeTransaction.tx_type)

            result = await db.execute(stmt)
            rows = result.fetchall()

            summary = {
                "stake_count": 0,
                "stake_total_tao": Decimal("0"),
                "unstake_count": 0,
                "unstake_total_tao": Decimal("0"),
            }

            for tx_type, count, total in rows:
                if tx_type == "stake":
                    summary["stake_count"] = count
                    summary["stake_total_tao"] = total or Decimal("0")
                elif tx_type == "unstake":
                    summary["unstake_count"] = count
                    summary["unstake_total_tao"] = total or Decimal("0")

            # Get unique netuids
            stmt = select(func.count(func.distinct(StakeTransaction.netuid))).where(
                StakeTransaction.wallet_address == self.wallet_address
            )
            result = await db.execute(stmt)
            summary["unique_subnets"] = result.scalar() or 0

            return summary


# Singleton instance
transaction_sync_service = TransactionSyncService()
