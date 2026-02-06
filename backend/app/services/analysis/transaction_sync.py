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
        settings = get_settings()
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

    async def sync_root_transactions(self) -> Dict[str, Any]:
        """Create StakeTransaction records for Root (SN0) from balance history.

        The dtao/trade/v1 endpoint only captures dTAO alpha swaps, not Root
        staking (which uses traditional add_stake delegation). This method
        detects staking events by analyzing stake_balance_history for SN0:
        significant balance jumps between consecutive snapshots indicate
        stake/unstake events.

        For Root, alpha = TAO (1:1 ratio), so effective_price is always 1.0.
        USD values are computed using historical TAO prices.
        """
        logger.info("Syncing Root (SN0) transactions from balance history")

        results = {
            "new_transactions": 0,
            "stake_transactions": 0,
            "unstake_transactions": 0,
            "skipped_existing": 0,
            "usd_enriched": 0,
        }

        # Minimum balance change to be considered a stake/unstake (not yield)
        # Normal daily Root yield is tiny (< 0.05 TAO/day for typical positions)
        STAKE_THRESHOLD = Decimal("0.1")

        try:
            # Get Root position hotkey
            async with get_db_context() as db:
                from app.models.position import Position
                stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.netuid == 0,
                )
                result = await db.execute(stmt)
                position = result.scalar_one_or_none()

            if not position or not position.validator_hotkey:
                logger.info("No Root position or hotkey found, skipping")
                return results

            hotkey = position.validator_hotkey

            # Fetch stake balance history for Root (90 days)
            import time
            ts_start = int(time.time()) - (90 * 86400)
            ts_end = int(time.time())
            history = await taostats_client.get_stake_balance_history(
                coldkey=self.wallet_address,
                hotkey=hotkey,
                netuid=0,
                timestamp_start=ts_start,
                limit=200,
            )
            snapshots = history.get("data", [])

            # Fetch TAO price history for USD enrichment
            price_lookup: Dict[str, Decimal] = {}
            try:
                price_response = await taostats_client.get_price_history(
                    timestamp_start=ts_start,
                    timestamp_end=ts_end,
                    limit=6000,
                )
                for price_rec in price_response.get("data", []):
                    ts = price_rec.get("created_at") or price_rec.get("timestamp")
                    if ts:
                        if isinstance(ts, (int, float)):
                            date_key = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                        else:
                            date_key = str(ts)[:10]
                        price = price_rec.get("price") or price_rec.get("close")
                        if price and date_key not in price_lookup:
                            price_lookup[date_key] = Decimal(str(price))
                logger.info("Loaded TAO price history for Root USD enrichment", dates=len(price_lookup))
            except Exception as e:
                logger.warning("Failed to fetch TAO price history for Root", error=str(e))

            # Get current TAO price as fallback
            current_tao_price = Decimal("150")
            try:
                price_data = await taostats_client.get_tao_price()
                price_info = price_data.get("data", [{}])[0]
                if price_info.get("price"):
                    current_tao_price = Decimal(str(price_info["price"]))
            except Exception:
                pass

            if not snapshots:
                logger.info("No Root balance history found")
                return results

            # Sort by timestamp ascending
            snapshots.sort(key=lambda x: x.get("timestamp", ""))

            async with get_db_context() as db:
                prev_balance = Decimal("0")

                for snap in snapshots:
                    balance_rao = snap.get("balance", 0)
                    balance = Decimal(str(balance_rao)) / RAO_PER_TAO
                    timestamp_str = snap.get("timestamp", "")

                    if not timestamp_str:
                        continue

                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )

                    delta = balance - prev_balance
                    prev_balance = balance

                    # Skip tiny changes (yield, not staking)
                    if abs(delta) < STAKE_THRESHOLD:
                        continue

                    # Determine stake or unstake
                    if delta > 0:
                        tx_type = "stake"
                        amount = delta
                    else:
                        tx_type = "unstake"
                        amount = abs(delta)

                    # Create unique extrinsic_id from block number (fits varchar(32))
                    block_num = snap.get("block_number", 0)
                    extrinsic_id = f"r0-{block_num}"

                    # Check if already exists
                    check_stmt = select(StakeTransaction).where(
                        StakeTransaction.extrinsic_id == extrinsic_id
                    )
                    check_result = await db.execute(check_stmt)
                    if check_result.scalar_one_or_none():
                        results["skipped_existing"] += 1
                        continue

                    # Compute USD value using TAO price at transaction time
                    # For Root: stake IS TAO, so USD = amount × TAO_price
                    date_key = timestamp_str[:10] if timestamp_str else ""
                    tao_price_at_tx = price_lookup.get(date_key, current_tao_price)
                    usd_value = amount * tao_price_at_tx
                    if tao_price_at_tx != current_tao_price:
                        results["usd_enriched"] += 1

                    tx = StakeTransaction(
                        wallet_address=self.wallet_address,
                        extrinsic_id=extrinsic_id,
                        block_number=block_num,
                        timestamp=timestamp,
                        tx_hash=None,
                        tx_type=tx_type,
                        call_name=f"root.{tx_type}_detected",
                        netuid=0,
                        hotkey=hotkey,
                        amount_tao=amount,
                        alpha_amount=amount,  # Root alpha = TAO
                        limit_price=Decimal("1"),  # Root price is always 1:1
                        usd_value=usd_value,
                        fee_rao=0,
                        fee_tao=Decimal("0"),
                        success=True,
                        error_message=None,
                        raw_args={"source": "balance_history", "snapshot": snap},
                    )
                    db.add(tx)

                    results["new_transactions"] += 1
                    if tx_type == "stake":
                        results["stake_transactions"] += 1
                    else:
                        results["unstake_transactions"] += 1

                    logger.debug(
                        "Detected Root transaction from balance history",
                        type=tx_type,
                        amount_tao=float(amount),
                        timestamp=timestamp_str,
                    )

                await db.commit()

            logger.info("Root transaction sync completed", results=results)

        except Exception as e:
            logger.error("Root transaction sync failed", error=str(e))
            results["errors"] = [str(e)]

        return results

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


# Lazy singleton instance
_transaction_sync_service: TransactionSyncService | None = None


def get_transaction_sync_service() -> TransactionSyncService:
    """Get or create the transaction sync service singleton."""
    global _transaction_sync_service
    if _transaction_sync_service is None:
        _transaction_sync_service = TransactionSyncService()
    return _transaction_sync_service


class _LazyTransactionSyncService:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_transaction_sync_service(), name)


transaction_sync_service = _LazyTransactionSyncService()
