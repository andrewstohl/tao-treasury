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

from app.core.database import get_db_context
from app.models.position import Position
from app.services.data.taostats_client import taostats_client, TaoStatsError

logger = structlog.get_logger()


def compute_unrealized_decomposition(position) -> None:
    """Compute unrealized PnL decomposition from Position fields.

    Uses net-invested cost basis (matches TaoStats):
        unrealized_pnl = tao_value_mid - cost_basis_tao

    Yield decomposition:
        emission_remaining = min(total_yield_alpha, alpha_balance)
        unrealized_yield = emission_remaining * current_price
        unrealized_alpha_pnl = unrealized_pnl - unrealized_yield  (residual)

    For inactive positions (alpha_balance <= 0), all unrealized fields are zeroed.
    """
    if position.alpha_balance <= 0:
        position.unrealized_pnl_tao = Decimal("0")
        position.unrealized_pnl_pct = Decimal("0")
        position.unrealized_yield_tao = Decimal("0")
        position.unrealized_alpha_pnl_tao = Decimal("0")
        position.total_unrealized_pnl_tao = Decimal("0")
        return

    cost_basis = position.cost_basis_tao or Decimal("0")
    alpha_balance = position.alpha_balance
    current_alpha_price = (
        position.tao_value_mid / alpha_balance
        if alpha_balance > 0 and position.tao_value_mid > 0
        else Decimal("0")
    )

    # Unrealized P&L = current value - net invested
    pnl = position.tao_value_mid - cost_basis if cost_basis > 0 else Decimal("0")
    pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else Decimal("0")

    # Yield: emission alpha still held * current price
    total_yield = getattr(position, 'total_yield_alpha', None) or Decimal("0")
    emission_remaining = min(total_yield, alpha_balance)
    unrealized_yield = emission_remaining * current_alpha_price

    # Alpha P&L is the residual (can be negative if alpha price dropped)
    alpha_pnl = pnl - unrealized_yield

    position.unrealized_pnl_tao = pnl
    position.unrealized_pnl_pct = pnl_pct
    position.unrealized_alpha_pnl_tao = alpha_pnl
    position.unrealized_yield_tao = unrealized_yield
    position.total_unrealized_pnl_tao = pnl


class YieldTrackerService:
    """Service for tracking yield using TaoStats accounting/tax API.

    Uses the accounting/tax endpoint which provides:
    - daily_income: Authoritative yield earned (no derivation needed)
    - token_swap: Exact alpha purchased/sold amounts
    - token_price_in_tao: Entry prices for cost basis
    """

    def __init__(self):
        pass

    async def _get_active_wallets(self) -> List[str]:
        """Get list of active wallet addresses from database."""
        from app.models.wallet import Wallet
        async with get_db_context() as db:
            stmt = select(Wallet.address).where(Wallet.is_active == True)  # noqa: E712
            result = await db.execute(stmt)
            return [row[0] for row in result.fetchall()]

    async def compute_all_position_yields(self, wallet_address: Optional[str] = None) -> Dict[str, Any]:
        """Compute yield for all open positions using accounting/tax API.

        Args:
            wallet_address: Specific wallet to process. If None, processes all active wallets.

        Returns:
            Dict with processing results
        """
        # Resolve wallets to process
        if wallet_address:
            wallets = [wallet_address]
        else:
            wallets = await self._get_active_wallets()

        logger.info("Computing yields from accounting/tax API", wallets=wallets)

        results = {
            "positions_processed": 0,
            "total_yield_alpha": Decimal("0"),
            "total_yield_tao": Decimal("0"),
            "errors": [],
        }

        for wallet in wallets:
            try:
                async with get_db_context() as db:
                    # Get all open positions
                    stmt = select(Position).where(
                        Position.wallet_address == wallet
                    )
                    result = await db.execute(stmt)
                    positions = result.scalars().all()

                    for position in positions:
                        try:
                            yield_data = await self._compute_position_yield(
                                db, position, wallet
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

            except Exception as e:
                logger.error("Yield computation failed", wallet=wallet, error=str(e))
                results["errors"].append(str(e))

        logger.info(
            "Yield computation completed",
            positions=results["positions_processed"],
            total_yield_tao=results["total_yield_tao"],
        )

        return results

    async def _compute_position_yield(
        self, db: AsyncSession, position: Position, wallet_address: str
    ) -> Optional[Dict[str, Any]]:
        """Compute yield for a single position from accounting/tax API.

        Fetches alpha token accounting data and extracts:
        - total_yield_alpha: Sum of all daily_income values
        - alpha_purchased: Sum of token_swap credits
        - alpha_sold: Sum of token_swap debits
        - avg_entry_price: Weighted average from token_swap prices
        """
        netuid = position.netuid
        token = f"SN{netuid}"

        # Skip inactive positions (alpha_balance = 0) — unrealized fields already zeroed
        if position.alpha_balance <= 0:
            return None

        # Fetch accounting data for this alpha token
        # Handle 12-month API limit by fetching from position entry date
        records = await self._fetch_accounting_records(wallet_address, token, position.entry_date)

        # Extract total_yield_alpha from daily_income (authoritative from TaoStats).
        total_yield_alpha = Decimal("0")
        if records:
            for record in records:
                daily_income = Decimal(str(record.get("daily_income") or 0))
                if daily_income > 0:
                    total_yield_alpha += daily_income

        # Write total_yield_alpha BEFORE decomposition so it uses the fresh value
        # (decomposition reads position.total_yield_alpha for unindexed buy detection)
        position.total_yield_alpha = total_yield_alpha

        # Compute unrealized decomposition (pure math, no API)
        compute_unrealized_decomposition(position)

        logger.debug(
            "Computed yield with ledger identity",
            netuid=netuid,
            total_yield_alpha=total_yield_alpha,
            unrealized_pnl=position.unrealized_pnl_tao,
            unrealized_yield=position.unrealized_yield_tao,
            unrealized_alpha_pnl=position.unrealized_alpha_pnl_tao,
        )

        return {
            "total_yield_alpha": total_yield_alpha,
            "alpha_purchased": position.alpha_purchased or Decimal("0"),
            "entry_price": position.entry_price_tao or Decimal("0"),
            "unrealized_yield_tao": position.unrealized_yield_tao,
            "unrealized_alpha_pnl_tao": position.unrealized_alpha_pnl_tao,
        }

    async def _fetch_accounting_records(
        self, wallet_address: str, token: str, entry_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Fetch accounting/tax records for a token.

        Handles the 12-month date range limit by chunking requests.

        Args:
            wallet_address: Wallet coldkey to query
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
                    coldkey=wallet_address,
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
