"""Transaction sync service for fetching and storing stake transactions.

Uses the TaoStats dtao/trade/v1 endpoint which provides clean trade data
including TAO and USD values at time of trade.
"""

from datetime import datetime, timezone
from decimal import Decimal
import re
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


def extract_netuid_from_name(name: str) -> Optional[int]:
    """Extract netuid from subnet name like 'SN19' or 'SN120'."""
    if name == "TAO":
        return None
    match = re.match(r"SN(\d+)", name)
    if match:
        return int(match.group(1))
    return None


class TransactionSyncService:
    """Service for syncing stake transactions from TaoStats.

    Uses the dtao/trade/v1 endpoint which provides:
    - from_name/to_name: TAO or subnet name (e.g., SN19)
    - from_amount/to_amount: amounts in rao
    - tao_value: TAO value of the trade
    - usd_value: USD value at time of trade
    """

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

            # Fetch trades from TaoStats using the trade endpoint
            trades = await taostats_client.get_all_trades(
                coldkey=self.wallet_address,
                max_pages=100,
            )

            results["total_fetched"] = len(trades)
            logger.info("Fetched trades", count=len(trades))

            # Process trades
            async with get_db_context() as db:
                for trade in trades:
                    # Skip if already synced (by block number)
                    block_num = trade.get("block_number", 0)
                    if block_num <= last_block and not full_sync:
                        continue

                    tx = await self._process_trade(db, trade)
                    if tx:
                        results["new_transactions"] += 1
                        if tx.tx_type == "stake":
                            results["stake_transactions"] += 1
                        else:
                            results["unstake_transactions"] += 1

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

    async def _process_trade(
        self,
        db: AsyncSession,
        trade: Dict
    ) -> Optional[StakeTransaction]:
        """Process and store a trade as a stake transaction.

        Trade format from API:
        - from_name: 'TAO' or 'SN##'
        - to_name: 'TAO' or 'SN##'
        - from_amount: amount in rao
        - to_amount: amount in rao
        - tao_value: TAO value of trade in rao
        - usd_value: USD value at time of trade
        - extrinsic_id: unique identifier
        - block_number: block number
        - timestamp: ISO timestamp
        - coldkey: wallet address
        """
        extrinsic_id = trade.get("extrinsic_id")
        if not extrinsic_id:
            return None

        # Check if already exists
        stmt = select(StakeTransaction).where(StakeTransaction.extrinsic_id == extrinsic_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return None  # Already synced

        # Determine transaction type and netuid
        from_name = trade.get("from_name", "")
        to_name = trade.get("to_name", "")

        if from_name == "TAO":
            # TAO -> SN## = stake (buying alpha)
            tx_type = "stake"
            netuid = extract_netuid_from_name(to_name)
            # Amount is TAO spent
            amount_tao = rao_to_tao(trade.get("from_amount", 0))
            # Alpha received
            alpha_amount = rao_to_tao(trade.get("to_amount", 0))
            # Effective price = TAO / Alpha
            if alpha_amount > 0:
                effective_price = amount_tao / alpha_amount
            else:
                effective_price = None
        else:
            # SN## -> TAO = unstake (selling alpha)
            tx_type = "unstake"
            netuid = extract_netuid_from_name(from_name)
            # Amount is TAO received
            amount_tao = rao_to_tao(trade.get("tao_value", 0))
            # Alpha sold
            alpha_amount = rao_to_tao(trade.get("from_amount", 0))
            # Effective price = TAO / Alpha
            if alpha_amount > 0:
                effective_price = amount_tao / alpha_amount
            else:
                effective_price = None

        if netuid is None:
            logger.warning("Could not extract netuid from trade", trade=trade)
            return None

        # Parse timestamp
        timestamp_str = trade.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(timezone.utc)

        # Get USD value
        usd_value_str = trade.get("usd_value", "0")
        try:
            usd_value = Decimal(str(usd_value_str))
        except:
            usd_value = Decimal("0")

        # Extract hotkey if available
        coldkey_data = trade.get("coldkey", {})
        hotkey = coldkey_data.get("ss58") if isinstance(coldkey_data, dict) else None

        # Create transaction record
        tx = StakeTransaction(
            wallet_address=self.wallet_address,
            extrinsic_id=extrinsic_id,
            block_number=trade.get("block_number", 0),
            timestamp=timestamp,
            tx_hash=None,  # Trade API doesn't provide hash
            tx_type=tx_type,
            call_name=f"dtao.{'stake' if tx_type == 'stake' else 'unstake'}",
            netuid=netuid,
            hotkey=hotkey,
            amount_tao=amount_tao,
            alpha_amount=alpha_amount,
            limit_price=effective_price,
            usd_value=usd_value,
            fee_rao=0,
            fee_tao=Decimal("0"),
            success=True,
            error_message=None,
            raw_args=trade,
        )

        db.add(tx)
        logger.debug(
            "Added stake transaction",
            type=tx_type,
            netuid=netuid,
            amount_tao=float(amount_tao),
            alpha_amount=float(alpha_amount),
            price=float(effective_price) if effective_price else None,
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
