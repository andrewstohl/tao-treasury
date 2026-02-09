"""Cost basis computation service.

Computes weighted average entry prices and realized P&L using FIFO lot tracking.

Two computation passes (second overwrites first):
1. Alpha-based FIFO from stake_transactions (dtao/trade endpoint) — fallback
   for positions without accounting data.
2. Alpha-based FIFO from TaoStats accounting/tax API — AUTHORITATIVE source
   because the accounting endpoint captures ALL transactions including batch
   extrinsics that the dtao/trade endpoint misses.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.transaction import StakeTransaction, PositionCostBasis
from app.models.position import Position

logger = structlog.get_logger()


class CostBasisService:
    """Service for computing cost basis and P&L from transaction history."""

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address

    async def compute_all_cost_basis(self) -> Dict[str, Any]:
        """Compute cost basis for all positions (with or without transactions).

        Creates PositionCostBasis records for ALL open positions:
        - Positions WITH transactions: full FIFO cost basis computation
        - Positions WITHOUT transactions: placeholder records with zero values

        This ensures the FX Exposure card can accurately report data completeness.

        Returns:
            Dict with computation results
        """
        logger.info("Computing cost basis for all positions")

        results = {
            "positions_computed": 0,
            "positions_without_transactions": 0,
            "total_invested": Decimal("0"),
            "total_realized_pnl": Decimal("0"),
            "errors": [],
        }

        try:
            async with get_db_context() as db:
                # Get all unique netuids with transactions
                tx_stmt = select(func.distinct(StakeTransaction.netuid)).where(
                    StakeTransaction.wallet_address == self.wallet_address
                )
                tx_result = await db.execute(tx_stmt)
                netuids_with_transactions = set(row[0] for row in tx_result.fetchall())

                # Get all open position netuids
                pos_stmt = select(Position.netuid).where(
                    Position.wallet_address == self.wallet_address
                )
                pos_result = await db.execute(pos_stmt)
                all_open_netuids = set(row[0] for row in pos_result.fetchall())

                # Process positions WITH transactions (full cost basis)
                for netuid in netuids_with_transactions:
                    try:
                        cost_basis = await self._compute_position_cost_basis(db, netuid)
                        if cost_basis:
                            results["positions_computed"] += 1
                            results["total_invested"] += cost_basis.net_invested_tao
                            results["total_realized_pnl"] += cost_basis.realized_pnl_tao

                            # Update the position record with cost basis
                            await self._update_position_with_cost_basis(db, netuid, cost_basis)
                    except Exception as e:
                        logger.error("Failed to compute cost basis", netuid=netuid, error=str(e))
                        results["errors"].append(f"SN{netuid}: {str(e)}")

                # Create placeholder records for positions WITHOUT transactions
                netuids_without_transactions = all_open_netuids - netuids_with_transactions
                for netuid in netuids_without_transactions:
                    try:
                        await self._create_placeholder_cost_basis(db, netuid)
                        results["positions_without_transactions"] += 1
                    except Exception as e:
                        logger.error("Failed to create placeholder cost basis", netuid=netuid, error=str(e))
                        results["errors"].append(f"SN{netuid} (placeholder): {str(e)}")

                await db.commit()

            logger.info("Cost basis computation completed", results=results)

        except Exception as e:
            logger.error("Cost basis computation failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def _create_placeholder_cost_basis(
        self,
        db: AsyncSession,
        netuid: int
    ) -> PositionCostBasis:
        """Create a placeholder PositionCostBasis for positions without transaction data.

        These positions exist (have alpha balance) but we couldn't find their
        transaction history from the TaoStats trade API. This ensures:
        1. The FX Exposure card can accurately report data completeness
        2. The position is counted in portfolio aggregations
        """
        # Check if already exists
        stmt = select(PositionCostBasis).where(
            PositionCostBasis.wallet_address == self.wallet_address,
            PositionCostBasis.netuid == netuid,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return existing  # Don't overwrite existing data

        # Get position for reference (entry date, current value)
        pos_stmt = select(Position).where(
            Position.wallet_address == self.wallet_address,
            Position.netuid == netuid,
        )
        pos_result = await db.execute(pos_stmt)
        position = pos_result.scalar_one_or_none()

        cost_basis = PositionCostBasis(
            wallet_address=self.wallet_address,
            netuid=netuid,
            total_staked_tao=Decimal("0"),
            total_unstaked_tao=Decimal("0"),
            net_invested_tao=Decimal("0"),
            weighted_avg_entry_price=Decimal("0"),
            realized_pnl_tao=Decimal("0"),
            realized_yield_tao=Decimal("0"),
            realized_yield_alpha=Decimal("0"),
            total_fees_tao=Decimal("0"),
            stake_count=0,
            unstake_count=0,
            first_stake_at=position.entry_date if position else None,
            last_transaction_at=None,
            computed_at=datetime.now(timezone.utc),
            # USD tracking - zero values indicate no data
            usd_cost_basis=Decimal("0"),
            weighted_avg_entry_price_usd=Decimal("0"),
            total_staked_usd=Decimal("0"),
            total_unstaked_usd=Decimal("0"),
            realized_pnl_usd=Decimal("0"),
        )
        db.add(cost_basis)

        logger.debug(
            "Created placeholder cost basis for position without transactions",
            netuid=netuid,
        )

        return cost_basis

    async def _compute_position_cost_basis(
        self,
        db: AsyncSession,
        netuid: int
    ) -> Optional[PositionCostBasis]:
        """Compute cost basis for a single position using FIFO method.

        Uses First-In-First-Out (FIFO) for realized P&L calculation:
        - When selling, we sell the oldest shares first
        - Realized P&L = (sale_price - entry_price) * shares_sold
        """
        # Get all transactions for this position ordered by timestamp
        stmt = (
            select(StakeTransaction)
            .where(
                StakeTransaction.wallet_address == self.wallet_address,
                StakeTransaction.netuid == netuid,
                StakeTransaction.success == True,
            )
            .order_by(StakeTransaction.timestamp)
        )
        result = await db.execute(stmt)
        transactions = list(result.scalars().all())

        if not transactions:
            return None

        # Use FIFO lot tracking for cost basis.
        # Lots track ALPHA quantities (not TAO) so that P&L arithmetic
        # is correct:  P&L = (exit_price − entry_price) × alpha_sold
        # where prices are TAO-per-alpha.
        lots: List[Dict] = []

        total_staked = Decimal("0")
        total_unstaked = Decimal("0")
        total_fees = Decimal("0")
        realized_pnl = Decimal("0")
        realized_price_pnl = Decimal("0")   # P&L from alpha price changes on purchased lots
        realized_yield_tao = Decimal("0")   # TAO from selling emission alpha (zero cost basis)
        realized_yield_alpha = Decimal("0") # Emission alpha tokens sold
        stake_count = 0
        unstake_count = 0
        first_stake_at = None
        last_tx_at = None

        # USD tracking for conversion exposure / FX risk
        total_staked_usd = Decimal("0")
        total_unstaked_usd = Decimal("0")
        realized_pnl_usd = Decimal("0")

        for tx in transactions:
            last_tx_at = tx.timestamp

            if tx.tx_type == "stake":
                stake_count += 1
                total_staked += tx.amount_tao
                total_fees += tx.fee_tao

                # Track USD at stake time
                tx_usd = tx.usd_value if tx.usd_value else Decimal("0")
                total_staked_usd += tx_usd

                if first_stake_at is None:
                    first_stake_at = tx.timestamp

                # Add lot to FIFO queue – keyed by ALPHA quantity
                entry_price = tx.limit_price if tx.limit_price else Decimal("0")
                alpha_qty = tx.alpha_amount if tx.alpha_amount else Decimal("0")
                if alpha_qty > 0:
                    lots.append({
                        "amount": alpha_qty,       # alpha tokens purchased
                        "price": entry_price,      # TAO per alpha at purchase
                        "usd_value": tx_usd,       # USD value at purchase (for FX tracking)
                        "timestamp": tx.timestamp,
                    })

            elif tx.tx_type == "unstake":
                unstake_count += 1
                total_unstaked += tx.amount_tao
                total_fees += tx.fee_tao

                # Track USD received on unstake
                tx_usd_received = tx.usd_value if tx.usd_value else Decimal("0")
                total_unstaked_usd += tx_usd_received

                # Calculate realized P&L using FIFO on alpha quantities
                exit_price = tx.limit_price if tx.limit_price else Decimal("0")
                alpha_to_sell = tx.alpha_amount if tx.alpha_amount else Decimal("0")
                original_alpha_to_sell = alpha_to_sell

                # Track USD cost consumed from FIFO lots for this unstake
                usd_cost_consumed = Decimal("0")

                # Process FIFO lots
                while alpha_to_sell > 0 and lots:
                    lot = lots[0]

                    if lot["amount"] <= alpha_to_sell:
                        # Consume entire lot
                        sold_alpha = lot["amount"]
                        alpha_to_sell -= sold_alpha
                        usd_cost_consumed += lot.get("usd_value", Decimal("0"))
                        lots.pop(0)
                    else:
                        # Partial lot - prorate USD cost
                        sold_alpha = alpha_to_sell
                        fraction_sold = sold_alpha / lot["amount"]
                        lot_usd = lot.get("usd_value", Decimal("0"))
                        usd_portion = lot_usd * fraction_sold
                        usd_cost_consumed += usd_portion
                        lot["amount"] -= sold_alpha
                        lot["usd_value"] = lot_usd - usd_portion
                        alpha_to_sell = Decimal("0")

                    # P&L = (exit_price − entry_price) × alpha_sold
                    if lot["price"] > 0 and exit_price > 0:
                        pnl = (exit_price - lot["price"]) * sold_alpha
                        realized_pnl += pnl
                        realized_price_pnl += pnl

                # Any remaining alpha_to_sell is emission yield (zero cost basis).
                # Revenue on that portion is pure profit — tracked separately.
                if alpha_to_sell > 0 and exit_price > 0:
                    yield_income = exit_price * alpha_to_sell
                    realized_pnl += yield_income
                    realized_yield_tao += yield_income
                    realized_yield_alpha += alpha_to_sell

                # USD P&L for this unstake = USD received - USD cost basis consumed
                # Prorate USD received if emission alpha was part of the sale
                if original_alpha_to_sell > 0 and tx_usd_received > 0:
                    # Fraction of sale that was purchased alpha (vs emission)
                    purchased_alpha_sold = original_alpha_to_sell - alpha_to_sell
                    if purchased_alpha_sold > 0:
                        usd_received_for_purchased = tx_usd_received * (purchased_alpha_sold / original_alpha_to_sell)
                        realized_pnl_usd += usd_received_for_purchased - usd_cost_consumed
                    # Emission alpha portion is pure USD profit (zero cost basis)
                    if alpha_to_sell > 0:
                        usd_received_for_yield = tx_usd_received * (alpha_to_sell / original_alpha_to_sell)
                        realized_pnl_usd += usd_received_for_yield

        # Compute weighted average entry price and book cost from remaining ALPHA lots
        # Book cost = sum of remaining lots' (alpha × price), i.e. what you paid for what you still hold
        total_remaining_alpha = sum(lot["amount"] for lot in lots)
        if total_remaining_alpha > 0:
            weighted_sum = sum(lot["amount"] * lot["price"] for lot in lots)
            weighted_avg_price = weighted_sum / total_remaining_alpha
            book_cost = weighted_sum
        else:
            weighted_avg_price = Decimal("0")
            book_cost = Decimal("0")

        # USD cost basis = sum of remaining lots' USD values
        usd_cost_basis = sum(lot.get("usd_value", Decimal("0")) for lot in lots)
        if total_remaining_alpha > 0 and usd_cost_basis > 0:
            weighted_avg_usd_per_alpha = usd_cost_basis / total_remaining_alpha
        else:
            weighted_avg_usd_per_alpha = Decimal("0")

        # Net invested = total staked - total unstaked (in TAO)
        net_invested = total_staked - total_unstaked

        # Upsert cost basis record
        stmt = select(PositionCostBasis).where(
            PositionCostBasis.wallet_address == self.wallet_address,
            PositionCostBasis.netuid == netuid,
        )
        result = await db.execute(stmt)
        cost_basis = result.scalar_one_or_none()

        if cost_basis is None:
            cost_basis = PositionCostBasis(
                wallet_address=self.wallet_address,
                netuid=netuid,
            )
            db.add(cost_basis)

        cost_basis.total_staked_tao = total_staked
        cost_basis.total_unstaked_tao = total_unstaked
        cost_basis.net_invested_tao = net_invested
        cost_basis.weighted_avg_entry_price = weighted_avg_price
        cost_basis.realized_pnl_tao = realized_pnl
        cost_basis.realized_yield_tao = realized_yield_tao
        cost_basis.realized_yield_alpha = realized_yield_alpha
        cost_basis.total_fees_tao = total_fees
        cost_basis.stake_count = stake_count
        cost_basis.unstake_count = unstake_count
        cost_basis.first_stake_at = first_stake_at
        cost_basis.last_transaction_at = last_tx_at
        cost_basis.computed_at = datetime.now(timezone.utc)

        # USD cost basis tracking (for FX/conversion exposure)
        cost_basis.usd_cost_basis = usd_cost_basis
        cost_basis.weighted_avg_entry_price_usd = weighted_avg_usd_per_alpha
        cost_basis.total_staked_usd = total_staked_usd
        cost_basis.total_unstaked_usd = total_unstaked_usd
        cost_basis.realized_pnl_usd = realized_pnl_usd

        # Attach book cost as transient attribute for _update_position_with_cost_basis
        # (not persisted — computed fresh each run from FIFO lots)
        cost_basis._book_cost_tao = book_cost  # type: ignore[attr-defined]

        # Track alpha purchased (remaining alpha from FIFO lots, excludes emission alpha)
        # This is critical for proper yield vs alpha price gain decomposition
        cost_basis._alpha_purchased = total_remaining_alpha  # type: ignore[attr-defined]

        logger.debug(
            "Computed cost basis",
            netuid=netuid,
            total_staked=total_staked,
            book_cost=book_cost,
            avg_price=weighted_avg_price,
            realized_pnl=realized_pnl,
            realized_yield_tao=realized_yield_tao,
            realized_yield_alpha=realized_yield_alpha,
            usd_cost_basis=usd_cost_basis,
            total_staked_usd=total_staked_usd,
            realized_pnl_usd=realized_pnl_usd,
        )

        return cost_basis

    async def _update_position_with_cost_basis(
        self,
        db: AsyncSession,
        netuid: int,
        cost_basis: PositionCostBasis
    ) -> None:
        """Update the position record with computed cost basis."""
        stmt = select(Position).where(
            Position.wallet_address == self.wallet_address,
            Position.netuid == netuid,
        )
        result = await db.execute(stmt)
        position = result.scalar_one_or_none()

        if position:
            position.entry_price_tao = cost_basis.weighted_avg_entry_price
            position.realized_pnl_tao = cost_basis.realized_pnl_tao

            if cost_basis.first_stake_at:
                position.entry_date = cost_basis.first_stake_at

            # Use FIFO book cost (cost of remaining lots) instead of net invested.
            # Book cost = Σ(lot.alpha × lot.entry_price) for remaining lots.
            # This is the correct cost basis for unrealized P&L because it represents
            # what was paid for the alpha tokens still held.
            book_cost = getattr(cost_basis, '_book_cost_tao', cost_basis.net_invested_tao)
            position.cost_basis_tao = book_cost

            # Track alpha purchased (remaining alpha from FIFO lots, excludes emission alpha)
            # This enables proper yield vs alpha price gain decomposition:
            #   emission_alpha = alpha_balance - alpha_purchased
            #   yield_tao = emission_alpha × current_alpha_price
            #   alpha_gain_tao = alpha_purchased × (current_price - entry_price)
            alpha_purchased = getattr(cost_basis, '_alpha_purchased', Decimal("0"))
            position.alpha_purchased = alpha_purchased

            # NOTE: unrealized_pnl_tao/pct are owned by yield_tracker
            # (ledger identity enforcement). Do NOT write here.

    async def compute_cost_basis_from_accounting(
        self, netuids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Compute alpha-based FIFO cost basis from accounting/tax API.

        This is the PRIMARY and AUTHORITATIVE source for cost basis because the
        accounting API captures ALL transactions including batch extrinsics that
        the dtao/trade endpoint misses.

        For each open position, fetches per-subnet accounting records (token="SN{n}")
        and builds alpha-based FIFO lots from token_swap records:
        - credit_amount = alpha tokens bought (staking TAO)
        - debit_amount = alpha tokens sold (unstaking)
        - token_price_in_tao = alpha price at time of swap
        - token_price_in_usd = alpha price in USD at time of swap

        This runs AFTER compute_all_cost_basis() and overwrites its results
        with complete data.

        Args:
            netuids: If provided, only process positions for these netuids.
                     Used for targeted recomputation after position changes.

        Returns:
            Dict with computation results
        """
        from app.services.data.taostats_client import get_taostats_client

        netuids_set = set(netuids) if netuids is not None else None
        logger.info(
            "Computing authoritative cost basis from accounting/tax API",
            targeted_netuids=list(netuids_set) if netuids_set else None,
        )

        client = get_taostats_client()
        results = {
            "positions_updated": 0,
            "positions_skipped": 0,
            "errors": [],
        }

        try:
            async with get_db_context() as db:
                # Get ALL positions (active AND inactive).
                # Inactive positions must be processed so final unstakes
                # get FIFO-processed and realized P&L is complete.
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                )
                pos_result = await db.execute(pos_stmt)
                positions = list(pos_result.scalars().all())

                logger.info("Processing positions for accounting cost basis", count=len(positions))

                now = datetime.now(timezone.utc)

                for position in positions:
                    netuid = position.netuid

                    # Skip positions not in the targeted set (when filtering)
                    if netuids_set is not None and netuid not in netuids_set:
                        continue

                    token = f"SN{netuid}"

                    try:
                        # Fetch per-subnet accounting records
                        entry_date = position.entry_date
                        if entry_date:
                            if entry_date.tzinfo is None:
                                start_date = entry_date.replace(tzinfo=timezone.utc)
                            else:
                                start_date = entry_date
                            # Go back 1 day before entry to catch any same-day transactions
                            start_date = start_date - timedelta(days=1)
                        else:
                            start_date = now - timedelta(days=365)

                        records = await client.get_all_accounting_tax(
                            coldkey=self.wallet_address,
                            token=token,
                            date_start=start_date.strftime("%Y-%m-%d"),
                            date_end=(now + timedelta(days=1)).strftime("%Y-%m-%d"),
                            max_pages=50,
                        )

                        # Extract token_swap records
                        swaps = [r for r in records if r.get("transaction_type") == "token_swap"]

                        if not swaps:
                            results["positions_skipped"] += 1
                            continue

                        # Sort chronologically. For same timestamp: buys BEFORE sells.
                        # This is critical for batch extrinsics (cross-subnet rebalances)
                        # where the buy creates a new lot before the sell consumes old lots.
                        swaps.sort(
                            key=lambda r: (
                                r.get("timestamp", ""),
                                1 if r.get("debit_amount") else 0,  # buys (credit) first
                            )
                        )

                        # Build alpha-based FIFO lots
                        lots: List[Dict] = []
                        total_staked_tao = Decimal("0")
                        total_unstaked_tao = Decimal("0")
                        total_staked_usd = Decimal("0")
                        total_unstaked_usd = Decimal("0")
                        realized_pnl_tao = Decimal("0")
                        realized_yield_tao = Decimal("0")
                        realized_yield_alpha = Decimal("0")
                        realized_pnl_usd = Decimal("0")
                        stake_count = 0
                        unstake_count = 0
                        first_stake_at = None
                        last_tx_at = None

                        for swap in swaps:
                            credit = swap.get("credit_amount")  # alpha bought
                            debit = swap.get("debit_amount")    # alpha sold
                            alpha_price_tao = Decimal(str(swap.get("token_price_in_tao") or 0))
                            alpha_price_usd = Decimal(str(swap.get("token_price_in_usd") or 0))
                            timestamp = swap.get("timestamp", "")

                            tx_time = None
                            if timestamp:
                                try:
                                    tx_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                    last_tx_at = tx_time
                                except ValueError:
                                    pass

                            if credit and not debit:
                                # BUY: staked TAO, received alpha
                                alpha_amount = Decimal(str(credit))
                                tao_cost = alpha_amount * alpha_price_tao
                                usd_cost = alpha_amount * alpha_price_usd

                                total_staked_tao += tao_cost
                                total_staked_usd += usd_cost
                                stake_count += 1

                                if first_stake_at is None and tx_time:
                                    first_stake_at = tx_time

                                lots.append({
                                    "amount": alpha_amount,
                                    "price": alpha_price_tao,
                                    "usd_value": usd_cost,
                                    "timestamp": tx_time,
                                })

                            elif debit and not credit:
                                # SELL: unstaked alpha, received TAO
                                alpha_sold = Decimal(str(debit))
                                exit_price = alpha_price_tao
                                tao_received = alpha_sold * exit_price
                                usd_received = alpha_sold * alpha_price_usd

                                total_unstaked_tao += tao_received
                                total_unstaked_usd += usd_received
                                unstake_count += 1

                                # Consume FIFO lots
                                alpha_to_sell = alpha_sold
                                usd_cost_consumed = Decimal("0")

                                while alpha_to_sell > 0 and lots:
                                    lot = lots[0]

                                    if lot["amount"] <= alpha_to_sell:
                                        sold_alpha = lot["amount"]
                                        alpha_to_sell -= sold_alpha
                                        usd_cost_consumed += lot.get("usd_value", Decimal("0"))
                                        entry_price = lot["price"]
                                        lots.pop(0)
                                    else:
                                        sold_alpha = alpha_to_sell
                                        fraction = sold_alpha / lot["amount"]
                                        lot_usd = lot.get("usd_value", Decimal("0"))
                                        usd_portion = lot_usd * fraction
                                        usd_cost_consumed += usd_portion
                                        entry_price = lot["price"]
                                        lot["amount"] -= sold_alpha
                                        lot["usd_value"] = lot_usd - usd_portion
                                        alpha_to_sell = Decimal("0")

                                    # Realized P&L on purchased alpha
                                    if entry_price > 0 and exit_price > 0:
                                        realized_pnl_tao += (exit_price - entry_price) * sold_alpha

                                # Any remaining alpha_to_sell is emission yield (zero cost basis)
                                if alpha_to_sell > 0 and exit_price > 0:
                                    yield_income = exit_price * alpha_to_sell
                                    realized_pnl_tao += yield_income
                                    realized_yield_tao += yield_income
                                    realized_yield_alpha += alpha_to_sell

                                # USD realized P&L
                                realized_pnl_usd += usd_received - usd_cost_consumed

                        # Compute remaining lot metrics
                        total_remaining_alpha = sum(lot["amount"] for lot in lots)
                        if total_remaining_alpha > 0:
                            weighted_sum = sum(lot["amount"] * lot["price"] for lot in lots)
                            weighted_avg_price = weighted_sum / total_remaining_alpha
                            book_cost = weighted_sum
                        else:
                            weighted_avg_price = Decimal("0")
                            book_cost = Decimal("0")

                        usd_cost_basis = sum(lot.get("usd_value", Decimal("0")) for lot in lots)

                        # Upsert PositionCostBasis
                        cb_stmt = select(PositionCostBasis).where(
                            PositionCostBasis.wallet_address == self.wallet_address,
                            PositionCostBasis.netuid == netuid,
                        )
                        cb_result = await db.execute(cb_stmt)
                        cost_basis = cb_result.scalar_one_or_none()

                        if cost_basis is None:
                            cost_basis = PositionCostBasis(
                                wallet_address=self.wallet_address,
                                netuid=netuid,
                            )
                            db.add(cost_basis)

                        cost_basis.total_staked_tao = total_staked_tao
                        cost_basis.total_unstaked_tao = total_unstaked_tao
                        cost_basis.net_invested_tao = total_staked_tao - total_unstaked_tao
                        cost_basis.weighted_avg_entry_price = weighted_avg_price
                        cost_basis.realized_pnl_tao = realized_pnl_tao
                        cost_basis.realized_yield_tao = realized_yield_tao
                        cost_basis.realized_yield_alpha = realized_yield_alpha
                        cost_basis.total_fees_tao = Decimal("0")
                        cost_basis.stake_count = stake_count
                        cost_basis.unstake_count = unstake_count
                        cost_basis.first_stake_at = first_stake_at
                        cost_basis.last_transaction_at = last_tx_at
                        cost_basis.computed_at = datetime.now(timezone.utc)
                        cost_basis.total_staked_usd = total_staked_usd
                        cost_basis.total_unstaked_usd = total_unstaked_usd
                        cost_basis.usd_cost_basis = usd_cost_basis
                        cost_basis.realized_pnl_usd = realized_pnl_usd

                        # Attach transient attributes for _update_position_with_cost_basis
                        cost_basis._book_cost_tao = book_cost  # type: ignore[attr-defined]
                        cost_basis._alpha_purchased = total_remaining_alpha  # type: ignore[attr-defined]

                        # Update Position record with cost_basis-owned fields ONLY.
                        # unrealized_pnl is owned by yield_tracker (identity enforcement).
                        position.entry_price_tao = weighted_avg_price
                        position.realized_pnl_tao = realized_pnl_tao
                        position.cost_basis_tao = book_cost
                        position.alpha_purchased = total_remaining_alpha

                        # Handle unindexed buy: all FIFO lots consumed but position
                        # is still active with alpha well beyond what emission explains.
                        # This happens when a recent buy (e.g., cross-subnet rebalance)
                        # hasn't been indexed by the accounting API yet.
                        # Set interim values so the decomposition works correctly.
                        # These will be overwritten by FIFO when the buy is indexed.
                        if total_remaining_alpha == 0 and position.alpha_balance > 0:
                            emission_estimate = position.total_yield_alpha or Decimal("0")
                            unindexed_alpha = position.alpha_balance - min(emission_estimate, position.alpha_balance)
                            if unindexed_alpha > 0:
                                current_price = (
                                    position.tao_value_mid / position.alpha_balance
                                    if position.alpha_balance > 0 else Decimal("0")
                                )
                                position.cost_basis_tao = unindexed_alpha * current_price
                                position.alpha_purchased = unindexed_alpha
                                position.entry_price_tao = current_price
                                logger.info(
                                    "Interim cost basis for unindexed buy",
                                    netuid=netuid,
                                    unindexed_alpha=float(unindexed_alpha),
                                    interim_cost=float(position.cost_basis_tao),
                                )

                        if first_stake_at:
                            position.entry_date = first_stake_at

                        results["positions_updated"] += 1

                        logger.debug(
                            "Computed authoritative cost basis from accounting",
                            netuid=netuid,
                            buys=stake_count,
                            sells=unstake_count,
                            alpha_purchased=float(position.alpha_purchased),
                            book_cost=float(position.cost_basis_tao),
                            avg_entry=float(position.entry_price_tao),
                            realized_pnl=float(realized_pnl_tao),
                            realized_yield=float(realized_yield_tao),
                        )

                    except Exception as e:
                        logger.error(
                            "Failed to compute accounting cost basis for position",
                            netuid=netuid,
                            error=str(e),
                        )
                        results["errors"].append(f"SN{netuid}: {str(e)}")

                    # Small delay between positions to avoid rate limiting
                    await asyncio.sleep(0.5)

                await db.commit()

            logger.info(
                "Authoritative accounting cost basis completed",
                positions_updated=results["positions_updated"],
                positions_skipped=results["positions_skipped"],
                errors=len(results["errors"]),
            )

        except Exception as e:
            logger.error("Accounting cost basis computation failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def get_cost_basis(self, netuid: int) -> Optional[PositionCostBasis]:
        """Get cost basis for a specific position."""
        async with get_db_context() as db:
            stmt = select(PositionCostBasis).where(
                PositionCostBasis.wallet_address == self.wallet_address,
                PositionCostBasis.netuid == netuid,
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def get_portfolio_pnl_summary(self) -> Dict[str, Any]:
        """Get portfolio-wide P&L summary."""
        async with get_db_context() as db:
            stmt = select(
                func.sum(PositionCostBasis.total_staked_tao),
                func.sum(PositionCostBasis.total_unstaked_tao),
                func.sum(PositionCostBasis.net_invested_tao),
                func.sum(PositionCostBasis.realized_pnl_tao),
                func.sum(PositionCostBasis.total_fees_tao),
                func.count(PositionCostBasis.id),
            ).where(PositionCostBasis.wallet_address == self.wallet_address)

            result = await db.execute(stmt)
            row = result.fetchone()

            if row and row[0] is not None:
                return {
                    "total_staked_tao": row[0],
                    "total_unstaked_tao": row[1],
                    "net_invested_tao": row[2],
                    "realized_pnl_tao": row[3],
                    "total_fees_tao": row[4],
                    "positions_with_history": row[5],
                }
            else:
                return {
                    "total_staked_tao": Decimal("0"),
                    "total_unstaked_tao": Decimal("0"),
                    "net_invested_tao": Decimal("0"),
                    "realized_pnl_tao": Decimal("0"),
                    "total_fees_tao": Decimal("0"),
                    "positions_with_history": 0,
                }


# Lazy singleton instance
_cost_basis_service: CostBasisService | None = None


def get_cost_basis_service() -> CostBasisService:
    """Get or create the cost basis service singleton."""
    global _cost_basis_service
    if _cost_basis_service is None:
        _cost_basis_service = CostBasisService()
    return _cost_basis_service


class _LazyCostBasisService:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_cost_basis_service(), name)


cost_basis_service = _LazyCostBasisService()
