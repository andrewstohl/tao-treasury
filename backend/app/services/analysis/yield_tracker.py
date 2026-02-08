"""Yield tracker service using TaoStats accounting/tax API.

This service provides authoritative yield data by fetching directly from
TaoStats's accounting/tax endpoint. No derivations or estimations.

Key fields from the API:
- daily_income: Yield earned each day (alpha tokens)
- token_swap credits: Alpha purchased when staking TAO
- token_swap debits: Alpha sold when unstaking

The accounting endpoint is the single source of truth because it:
1. Captures ALL transactions including batch extrinsics
2. Provides pre-computed daily_income (yield) values
3. Includes historical price data for cost basis
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.services.data.taostats_client import taostats_client, TaoStatsError

logger = structlog.get_logger()


class YieldTrackerService:
    """Service for tracking yield using TaoStats accounting/tax API.

    Uses the accounting/tax endpoint which provides:
    - daily_income: Authoritative yield earned (no derivation needed)
    - token_swap: Exact alpha purchased/sold amounts
    - token_price_in_tao: Entry prices for cost basis
    """

    def __init__(self):
        self._wallet_address = None

    @property
    def wallet_address(self):
        if self._wallet_address is None:
            settings = get_settings()
            self._wallet_address = settings.wallet_address
        return self._wallet_address

    async def compute_all_position_yields(self) -> Dict[str, Any]:
        """Compute yield for all open positions using accounting/tax API.

        Returns:
            Dict with processing results
        """
        logger.info("Computing yields from accounting/tax API")

        results = {
            "positions_processed": 0,
            "total_yield_alpha": Decimal("0"),
            "total_yield_tao": Decimal("0"),
            "errors": [],
        }

        try:
            async with get_db_context() as db:
                # Get all open positions
                stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address
                )
                result = await db.execute(stmt)
                positions = result.scalars().all()

                for position in positions:
                    try:
                        yield_data = await self._compute_position_yield(
                            db, position
                        )
                        if yield_data:
                            results["positions_processed"] += 1
                            results["total_yield_alpha"] += yield_data.get(
                                "total_yield_alpha", Decimal("0")
                            )
                            results["total_yield_tao"] += yield_data.get(
                                "unrealized_yield_tao", Decimal("0")
                            )
                    except Exception as e:
                        logger.error(
                            "Failed to compute yield for position",
                            netuid=position.netuid,
                            error=str(e),
                        )
                        results["errors"].append(f"SN{position.netuid}: {str(e)}")

                await db.commit()

            logger.info(
                "Yield computation completed",
                positions=results["positions_processed"],
                total_yield_tao=results["total_yield_tao"],
            )

        except Exception as e:
            logger.error("Yield computation failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def _compute_position_yield(
        self, db: AsyncSession, position: Position
    ) -> Optional[Dict[str, Any]]:
        """Compute yield for a single position from accounting/tax API.

        Fetches alpha token accounting data and extracts:
        - total_yield_alpha: Sum of all daily_income values
        - alpha_purchased: Sum of token_swap credits
        - alpha_sold: Sum of token_swap debits
        - avg_entry_price: Weighted average from token_swap prices
        """
        netuid = position.netuid

        # Skip SN0 (Root) - it uses TAO directly, not alpha tokens
        if netuid == 0:
            return None

        token = f"SN{netuid}"

        # Fetch accounting data for this alpha token
        # Handle 12-month API limit by fetching from position entry date
        records = await self._fetch_accounting_records(token, position.entry_date)

        if not records:
            # No accounting data - reset yield to 0 (don't trust old derived values)
            logger.debug("No accounting records found, resetting yield to 0", netuid=netuid)
            position.total_yield_alpha = Decimal("0")
            position.unrealized_yield_tao = Decimal("0")
            position.unrealized_alpha_pnl_tao = Decimal("0")
            position.total_unrealized_pnl_tao = Decimal("0")
            return {"total_yield_alpha": Decimal("0"), "unrealized_yield_tao": Decimal("0")}

        # Process records to extract yield and purchase data
        total_yield_alpha = Decimal("0")
        total_purchased_alpha = Decimal("0")
        total_sold_alpha = Decimal("0")
        weighted_price_sum = Decimal("0")

        for record in records:
            tx_type = record.get("transaction_type")
            credit = Decimal(str(record.get("credit_amount") or 0))
            debit = Decimal(str(record.get("debit_amount") or 0))
            daily_income = Decimal(str(record.get("daily_income") or 0))
            price_tao = record.get("token_price_in_tao")

            # Yield from daily_income (authoritative)
            if daily_income > 0:
                total_yield_alpha += daily_income

            # Alpha purchased/sold from token_swap transactions
            if tx_type == "token_swap":
                if credit > 0:
                    total_purchased_alpha += credit
                    # Track weighted entry price
                    if price_tao:
                        weighted_price_sum += credit * Decimal(str(price_tao))
                if debit > 0:
                    total_sold_alpha += debit

        # Calculate net purchased alpha (what we still hold from purchases)
        net_purchased_alpha = total_purchased_alpha - total_sold_alpha

        # Calculate weighted average entry price
        if total_purchased_alpha > 0:
            avg_entry_price = weighted_price_sum / total_purchased_alpha
        else:
            avg_entry_price = Decimal("0")

        # Get current alpha price from position
        current_alpha_price = Decimal("0")
        if position.alpha_balance > 0 and position.tao_value_mid > 0:
            current_alpha_price = position.tao_value_mid / position.alpha_balance

        # Calculate unrealized yield in TAO
        # Yield alpha is still held, so value it at current price
        unrealized_yield_tao = total_yield_alpha * current_alpha_price

        # Calculate alpha P&L (price movement on purchased alpha)
        # P&L = net_purchased × (current_price - entry_price)
        if net_purchased_alpha > 0 and avg_entry_price > 0:
            unrealized_alpha_pnl_tao = net_purchased_alpha * (
                current_alpha_price - avg_entry_price
            )
        else:
            unrealized_alpha_pnl_tao = Decimal("0")

        # Update position with authoritative values
        position.total_yield_alpha = total_yield_alpha
        position.alpha_purchased = net_purchased_alpha  # Update to authoritative value
        position.unrealized_yield_tao = unrealized_yield_tao
        position.unrealized_alpha_pnl_tao = unrealized_alpha_pnl_tao
        position.total_unrealized_pnl_tao = unrealized_yield_tao + unrealized_alpha_pnl_tao

        # Update entry price if we have better data
        if avg_entry_price > 0:
            position.entry_price_tao = avg_entry_price

        logger.debug(
            "Computed yield from accounting API",
            netuid=netuid,
            total_yield_alpha=total_yield_alpha,
            net_purchased_alpha=net_purchased_alpha,
            unrealized_yield_tao=unrealized_yield_tao,
            unrealized_alpha_pnl_tao=unrealized_alpha_pnl_tao,
        )

        return {
            "total_yield_alpha": total_yield_alpha,
            "net_purchased_alpha": net_purchased_alpha,
            "avg_entry_price": avg_entry_price,
            "unrealized_yield_tao": unrealized_yield_tao,
            "unrealized_alpha_pnl_tao": unrealized_alpha_pnl_tao,
        }

    async def _fetch_accounting_records(
        self, token: str, entry_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Fetch accounting/tax records for a token.

        Handles the 12-month date range limit by chunking requests.

        Args:
            token: Token name (e.g., "SN64")
            entry_date: Position entry date (for historical range)

        Returns:
            List of all accounting records
        """
        all_records: List[Dict[str, Any]] = []

        # Determine date range (use timezone-aware datetimes)
        end_date = datetime.now(timezone.utc)

        if entry_date:
            # Ensure entry_date is timezone-aware
            if entry_date.tzinfo is None:
                start_date = entry_date.replace(tzinfo=timezone.utc)
            else:
                start_date = entry_date
        else:
            # Default to 12 months ago if no entry date
            start_date = end_date - timedelta(days=365)

        # Fetch in 12-month chunks (API limit)
        current_start = start_date
        max_chunk_days = 365  # 12 months

        while current_start < end_date:
            current_end = min(
                current_start + timedelta(days=max_chunk_days),
                end_date
            )

            try:
                records = await taostats_client.get_all_accounting_tax(
                    coldkey=self.wallet_address,
                    token=token,
                    date_start=current_start.strftime("%Y-%m-%d"),
                    date_end=current_end.strftime("%Y-%m-%d"),
                    max_pages=50,
                )
                all_records.extend(records)

            except TaoStatsError as e:
                # Log but continue - some tokens may not have data
                logger.warning(
                    "Failed to fetch accounting data",
                    token=token,
                    start=current_start.strftime("%Y-%m-%d"),
                    error=str(e),
                )

            current_start = current_end + timedelta(days=1)

        return all_records


# Singleton instance
yield_tracker_service = YieldTrackerService()
