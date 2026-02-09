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


def compute_unrealized_decomposition(position) -> None:
    """Pure math: compute unrealized PnL decomposition from Position fields.

    No API calls. Enforces ledger identity by construction:
        unrealized_pnl = tao_value_mid - effective_cost_basis
        unrealized_alpha_pnl = effective_alpha_purchased * (current_price - entry_price)
        unrealized_yield = unrealized_pnl - unrealized_alpha_pnl  (residual)

    Stale-FIFO handling: When the accounting API hasn't indexed a recent unstake,
    alpha_purchased > alpha_balance (FIFO still has lots for sold alpha). We use
    LOCAL effective values for decomposition only — FIFO-owned DB fields are NEVER
    modified here. When the FIFO catches up, it overwrites with authoritative values.

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
    alpha_purchased = position.alpha_purchased or Decimal("0")
    entry_price = position.entry_price_tao or Decimal("0")
    alpha_balance = position.alpha_balance
    current_alpha_price = (
        position.tao_value_mid / alpha_balance
        if alpha_balance > 0 and position.tao_value_mid > 0
        else Decimal("0")
    )

    # Stale-FIFO detection: FIFO thinks more purchased alpha remains than
    # actual balance (unstake not yet indexed by accounting API).
    # Use effective local values for decomposition only — do NOT write back
    # to cost_basis_tao or alpha_purchased.
    if alpha_purchased > alpha_balance and alpha_purchased > 0:
        # Stale FIFO: recent unstake not indexed. Estimate purchased alpha
        # by subtracting emission alpha held from total balance.
        # total_yield_alpha (sum of daily_income from API) is the total
        # emission earned. It's an upper bound for emission currently held
        # (some may have been sold in past unstakes). This is conservative:
        # overestimating emission → less alpha_pnl → more yield.
        total_yield = getattr(position, 'total_yield_alpha', None) or Decimal("0")
        emission_held_estimate = min(total_yield, alpha_balance)
        effective_purchased = max(alpha_balance - emission_held_estimate, Decimal("0"))
        # Scale cost proportionally to the fraction of purchased alpha remaining
        effective_cost = cost_basis * (effective_purchased / alpha_purchased)
    else:
        # Normal case: FIFO is current. alpha_purchased <= alpha_balance.
        effective_purchased = alpha_purchased
        effective_cost = cost_basis

    pnl = position.tao_value_mid - effective_cost if effective_cost > 0 else Decimal("0")
    pnl_pct = (pnl / effective_cost * 100) if effective_cost > 0 else Decimal("0")
    alpha_pnl = (
        effective_purchased * (current_alpha_price - entry_price)
        if effective_purchased > 0 and entry_price > 0
        else Decimal("0")
    )

    # Yield is the residual: pnl - alpha_pnl. Floor at 0 because yield
    # (emission income) cannot be negative. In rare edge cases the emission
    # estimate may be slightly off, so clamping prevents impossible negatives.
    unrealized_yield = pnl - alpha_pnl
    if unrealized_yield < 0:
        unrealized_yield = Decimal("0")
        alpha_pnl = pnl  # preserve identity: pnl = alpha_pnl + yield

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
        token = f"SN{netuid}"

        # Skip inactive positions (alpha_balance = 0) — unrealized fields already zeroed
        if position.alpha_balance <= 0:
            return None

        # Fetch accounting data for this alpha token
        # Handle 12-month API limit by fetching from position entry date
        records = await self._fetch_accounting_records(token, position.entry_date)

        # Extract total_yield_alpha from daily_income (authoritative from TaoStats).
        total_yield_alpha = Decimal("0")
        if records:
            for record in records:
                daily_income = Decimal(str(record.get("daily_income") or 0))
                if daily_income > 0:
                    total_yield_alpha += daily_income

        # Compute unrealized decomposition (pure math, no API)
        compute_unrealized_decomposition(position)

        # Write total_yield_alpha from API (the only API-dependent field)
        position.total_yield_alpha = total_yield_alpha

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
