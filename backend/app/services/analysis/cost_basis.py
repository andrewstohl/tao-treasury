"""Cost basis computation service.

Computes weighted average entry prices and realized P&L from transaction history.

Two P&L sources:
1. Alpha-based FIFO from stake_transactions — gives per-position entry prices,
   cost basis, and alpha lot tracking needed for yield decomposition.
2. TAO-based FIFO from TaoStats accounting/tax API — gives accurate total
   realized P&L that matches TaoStats' own calculation.  This is authoritative
   because the accounting endpoint captures batch extrinsics that the dtao/trade
   endpoint misses.
"""

import re
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
        """Compute cost basis for all positions with transactions.

        Returns:
            Dict with computation results
        """
        logger.info("Computing cost basis for all positions")

        results = {
            "positions_computed": 0,
            "total_invested": Decimal("0"),
            "total_realized_pnl": Decimal("0"),
            "errors": [],
        }

        try:
            async with get_db_context() as db:
                # Get all unique netuids with transactions
                stmt = select(func.distinct(StakeTransaction.netuid)).where(
                    StakeTransaction.wallet_address == self.wallet_address
                )
                result = await db.execute(stmt)
                netuids = [row[0] for row in result.fetchall()]

                for netuid in netuids:
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

                await db.commit()

            logger.info("Cost basis computation completed", results=results)

        except Exception as e:
            logger.error("Cost basis computation failed", error=str(e))
            results["errors"].append(str(e))

        return results

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

        for tx in transactions:
            last_tx_at = tx.timestamp

            if tx.tx_type == "stake":
                stake_count += 1
                total_staked += tx.amount_tao
                total_fees += tx.fee_tao

                if first_stake_at is None:
                    first_stake_at = tx.timestamp

                # Add lot to FIFO queue – keyed by ALPHA quantity
                entry_price = tx.limit_price if tx.limit_price else Decimal("0")
                alpha_qty = tx.alpha_amount if tx.alpha_amount else Decimal("0")
                if alpha_qty > 0:
                    lots.append({
                        "amount": alpha_qty,       # alpha tokens purchased
                        "price": entry_price,      # TAO per alpha at purchase
                        "timestamp": tx.timestamp,
                    })

            elif tx.tx_type == "unstake":
                unstake_count += 1
                total_unstaked += tx.amount_tao
                total_fees += tx.fee_tao

                # Calculate realized P&L using FIFO on alpha quantities
                exit_price = tx.limit_price if tx.limit_price else Decimal("0")
                alpha_to_sell = tx.alpha_amount if tx.alpha_amount else Decimal("0")

                # Process FIFO lots
                while alpha_to_sell > 0 and lots:
                    lot = lots[0]

                    if lot["amount"] <= alpha_to_sell:
                        # Consume entire lot
                        sold_alpha = lot["amount"]
                        alpha_to_sell -= sold_alpha
                        lots.pop(0)
                    else:
                        # Partial lot
                        sold_alpha = alpha_to_sell
                        lot["amount"] -= sold_alpha
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

        # Attach book cost as transient attribute for _update_position_with_cost_basis
        # (not persisted — computed fresh each run from FIFO lots)
        cost_basis._book_cost_tao = book_cost  # type: ignore[attr-defined]

        logger.debug(
            "Computed cost basis",
            netuid=netuid,
            total_staked=total_staked,
            book_cost=book_cost,
            avg_price=weighted_avg_price,
            realized_pnl=realized_pnl,
            realized_yield_tao=realized_yield_tao,
            realized_yield_alpha=realized_yield_alpha,
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

            # Compute unrealized P&L against book cost
            if position.tao_value_mid > 0 and book_cost > 0:
                position.unrealized_pnl_tao = position.tao_value_mid - book_cost
                position.unrealized_pnl_pct = (
                    (position.unrealized_pnl_tao / book_cost) * 100
                )
            else:
                position.unrealized_pnl_tao = Decimal("0")
                position.unrealized_pnl_pct = Decimal("0")

    async def compute_realized_pnl_from_accounting(self) -> Dict[str, Any]:
        """Compute realized P&L from TaoStats accounting/tax API using TAO-based FIFO.

        This is the authoritative source for realized P&L because the accounting
        endpoint captures all trades including batch extrinsics that the dtao/trade
        endpoint misses.

        Algorithm per subnet:
          - Buys (debit_amount set): add TAO amount as a FIFO cost lot
          - Sells (credit_amount set): consume FIFO lots, P&L = proceeds - cost

        Returns:
            Dict with per-subnet and total realized P&L
        """
        from app.services.data.taostats_client import get_taostats_client

        logger.info("Computing realized P&L from accounting/tax data")

        client = get_taostats_client()

        # The API enforces a max 12-month date range.
        # Use a rolling window ending today.
        now = datetime.now(timezone.utc)
        date_end = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        date_start = (now - timedelta(days=364)).strftime("%Y-%m-%d")

        records = await client.get_all_accounting_tax(
            coldkey=self.wallet_address,
            token="TAO",
            date_start=date_start,
            date_end=date_end,
        )

        # Filter to token_swap records and group by subnet
        swaps_by_subnet: Dict[int, List[Dict]] = {}
        for rec in records:
            if rec.get("transaction_type") != "token_swap":
                continue

            # Parse subnet from additional_data (e.g. "SN64", "SN3")
            subnet_str = rec.get("additional_data", "") or ""
            match = re.match(r"SN(\d+)", subnet_str)
            if not match:
                continue
            netuid = int(match.group(1))

            swaps_by_subnet.setdefault(netuid, []).append(rec)

        # Sort each subnet's trades by timestamp.
        # CRITICAL: within the same timestamp, sells MUST come before buys.
        # Exit-and-reenter trades (sell then immediate rebuy) share a timestamp;
        # if the buy sorts first, the subsequent sell would incorrectly consume
        # the fresh buy lot alongside the old lots.
        for netuid in swaps_by_subnet:
            swaps_by_subnet[netuid].sort(
                key=lambda r: (
                    r.get("timestamp", ""),
                    0 if r.get("credit_amount") else 1,  # sells (credit) before buys (debit)
                )
            )

        # Run TAO-based FIFO per subnet
        total_realized = Decimal("0")
        per_subnet: Dict[int, Decimal] = {}

        for netuid, trades in swaps_by_subnet.items():
            lots: List[Decimal] = []  # FIFO queue of TAO cost lots
            realized = Decimal("0")

            for trade in trades:
                debit = trade.get("debit_amount")
                credit = trade.get("credit_amount")

                if debit and not credit:
                    # Buy: TAO spent → add cost lot
                    lots.append(Decimal(str(debit)))
                elif credit and not debit:
                    # Sell: TAO received → consume ALL remaining FIFO lots.
                    # Each sell is a full or partial exit; consuming all lots
                    # gives the correct per-subnet total because:
                    #  - Full exits: obviously consume everything
                    #  - Exit-and-reenter (sell then immediate rebuy at same timestamp):
                    #    the subsequent buy re-establishes a fresh cost lot at market price,
                    #    so the total P&L is identical to consuming all lots on the sell.
                    proceeds = Decimal(str(credit))
                    cost = sum(lots)
                    lots.clear()
                    realized += proceeds - cost

            per_subnet[netuid] = realized
            total_realized += realized

        logger.info(
            "Accounting-based realized P&L computed",
            total_realized=float(total_realized),
            subnets=len(per_subnet),
        )

        # Update PositionCostBasis AND Position records with accounting-derived realized P&L
        async with get_db_context() as db:
            for netuid, realized in per_subnet.items():
                stmt = select(PositionCostBasis).where(
                    PositionCostBasis.wallet_address == self.wallet_address,
                    PositionCostBasis.netuid == netuid,
                )
                result = await db.execute(stmt)
                cost_basis = result.scalar_one_or_none()

                if cost_basis is None:
                    # Create record for subnets that only exist in accounting data
                    cost_basis = PositionCostBasis(
                        wallet_address=self.wallet_address,
                        netuid=netuid,
                        total_staked_tao=Decimal("0"),
                        total_unstaked_tao=Decimal("0"),
                        net_invested_tao=Decimal("0"),
                        weighted_avg_entry_price=Decimal("0"),
                        total_fees_tao=Decimal("0"),
                        stake_count=0,
                        unstake_count=0,
                        computed_at=datetime.now(timezone.utc),
                    )
                    db.add(cost_basis)

                cost_basis.realized_pnl_tao = realized
                cost_basis.computed_at = datetime.now(timezone.utc)

                # Propagate to the Position record so per-position P&L
                # matches the portfolio aggregate.
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.netuid == netuid,
                )
                pos_result = await db.execute(pos_stmt)
                position = pos_result.scalar_one_or_none()
                if position:
                    position.realized_pnl_tao = realized

            await db.commit()

        return {
            "total_realized_pnl": total_realized,
            "per_subnet": {k: float(v) for k, v in per_subnet.items()},
            "subnets_processed": len(per_subnet),
        }

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
