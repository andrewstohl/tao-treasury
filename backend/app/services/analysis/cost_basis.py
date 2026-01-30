"""Cost basis computation service.

Computes weighted average entry prices and realized P&L from transaction history.
"""

from datetime import datetime, timezone
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

        # Use FIFO lot tracking for cost basis
        # Each lot: (amount_tao, price_per_alpha, timestamp)
        lots: List[Dict] = []

        total_staked = Decimal("0")
        total_unstaked = Decimal("0")
        total_fees = Decimal("0")
        realized_pnl = Decimal("0")
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

                # Add lot to FIFO queue
                # Use limit_price as entry price if available
                entry_price = tx.limit_price if tx.limit_price else Decimal("0")
                lots.append({
                    "amount": tx.amount_tao,
                    "price": entry_price,
                    "timestamp": tx.timestamp,
                })

            elif tx.tx_type == "unstake":
                unstake_count += 1
                total_unstaked += tx.amount_tao
                total_fees += tx.fee_tao

                # Calculate realized P&L using FIFO
                exit_price = tx.limit_price if tx.limit_price else Decimal("0")
                amount_to_sell = tx.amount_tao

                # Process FIFO lots
                while amount_to_sell > 0 and lots:
                    lot = lots[0]

                    if lot["amount"] <= amount_to_sell:
                        # Use entire lot
                        sold_amount = lot["amount"]
                        amount_to_sell -= sold_amount
                        lots.pop(0)
                    else:
                        # Partial lot
                        sold_amount = amount_to_sell
                        lot["amount"] -= sold_amount
                        amount_to_sell = Decimal("0")

                    # Calculate realized P&L for this portion
                    if lot["price"] > 0 and exit_price > 0:
                        # P&L = (exit_price - entry_price) * amount
                        # Note: prices are alpha per TAO, so higher = better for selling
                        pnl = (exit_price - lot["price"]) * sold_amount
                        realized_pnl += pnl

        # Compute weighted average entry price from remaining lots
        total_remaining = sum(lot["amount"] for lot in lots)
        if total_remaining > 0:
            weighted_sum = sum(lot["amount"] * lot["price"] for lot in lots)
            weighted_avg_price = weighted_sum / total_remaining
        else:
            weighted_avg_price = Decimal("0")

        # Net invested = total staked - cost basis of unstaked
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
        cost_basis.total_fees_tao = total_fees
        cost_basis.stake_count = stake_count
        cost_basis.unstake_count = unstake_count
        cost_basis.first_stake_at = first_stake_at
        cost_basis.last_transaction_at = last_tx_at
        cost_basis.computed_at = datetime.now(timezone.utc)

        logger.debug(
            "Computed cost basis",
            netuid=netuid,
            total_staked=total_staked,
            avg_price=weighted_avg_price,
            realized_pnl=realized_pnl,
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
            position.cost_basis_tao = cost_basis.net_invested_tao
            position.realized_pnl_tao = cost_basis.realized_pnl_tao

            if cost_basis.first_stake_at:
                position.entry_date = cost_basis.first_stake_at

            # Compute unrealized P&L
            if position.tao_value_mid > 0 and cost_basis.net_invested_tao > 0:
                position.unrealized_pnl_tao = position.tao_value_mid - cost_basis.net_invested_tao
                position.unrealized_pnl_pct = (
                    (position.unrealized_pnl_tao / cost_basis.net_invested_tao) * 100
                )
            else:
                # Reset P&L when cost basis is zero/negative (e.g. fully unstaked then re-staked
                # before the new stake is detected by balance history sync)
                position.unrealized_pnl_tao = Decimal("0")
                position.unrealized_pnl_pct = Decimal("0")

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
