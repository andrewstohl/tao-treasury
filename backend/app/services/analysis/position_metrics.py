"""Position metrics service.

Single source of truth for position-level yield and alpha P&L calculations.
All derived metrics are computed here and stored on the Position model.

This ensures the ledger identity holds:
- Portfolio.yield = Sum(Position.yield)
- Portfolio.alpha_pnl = Sum(Position.alpha_pnl)
- Portfolio.total_pnl = Portfolio.yield + Portfolio.alpha_pnl
"""

from decimal import Decimal
from typing import Dict, Any, Optional, List

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.models.transaction import PositionCostBasis
from app.models.subnet import Subnet

logger = structlog.get_logger()


class PositionMetricsService:
    """Service for computing decomposed yield and alpha P&L metrics.

    Computes and stores all derived position metrics in a single pass,
    ensuring consistency between position-level and portfolio-level aggregations.
    """

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address

    async def compute_all_position_metrics(self) -> Dict[str, Any]:
        """Compute metrics for all open positions.

        This should be called after:
        1. sync_positions() - to have current alpha balances
        2. compute_all_cost_basis() - to have FIFO cost basis and alpha_purchased

        Returns:
            Dict with computation results
        """
        logger.info("Computing position metrics for all positions")

        results = {
            "positions_processed": 0,
            "total_unrealized_yield_tao": Decimal("0"),
            "total_unrealized_alpha_pnl_tao": Decimal("0"),
            "total_realized_yield_tao": Decimal("0"),
            "total_realized_alpha_pnl_tao": Decimal("0"),
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

                # Get current alpha prices from Subnet model
                alpha_prices = await self._get_alpha_prices(db)

                # Get all cost basis records
                cost_basis_map = await self._get_cost_basis_map(db)

                for position in positions:
                    try:
                        alpha_price = alpha_prices.get(position.netuid, Decimal("0"))
                        cost_basis = cost_basis_map.get(position.netuid)

                        await self._compute_position_metrics(
                            db, position, alpha_price, cost_basis
                        )

                        results["positions_processed"] += 1
                        results["total_unrealized_yield_tao"] += position.unrealized_yield_tao
                        results["total_unrealized_alpha_pnl_tao"] += position.unrealized_alpha_pnl_tao
                        results["total_realized_yield_tao"] += position.realized_yield_tao
                        results["total_realized_alpha_pnl_tao"] += position.realized_alpha_pnl_tao

                    except Exception as e:
                        logger.error(
                            "Failed to compute position metrics",
                            netuid=position.netuid,
                            error=str(e),
                        )
                        results["errors"].append(f"SN{position.netuid}: {str(e)}")

                await db.commit()

            logger.info("Position metrics computation completed", results=results)

        except Exception as e:
            logger.error("Position metrics computation failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def _get_alpha_prices(self, db: AsyncSession) -> Dict[int, Decimal]:
        """Get current alpha prices for all subnets.

        Alpha price is derived from position.tao_value_mid / position.alpha_balance.
        Falls back to Subnet.alpha_price_tao if available.
        """
        prices = {}

        # Get from positions (most accurate - from TaoStats balance_as_tao)
        stmt = select(Position).where(
            Position.wallet_address == self.wallet_address,
            Position.alpha_balance > 0,
        )
        result = await db.execute(stmt)
        for position in result.scalars().all():
            if position.alpha_balance > 0:
                prices[position.netuid] = position.tao_value_mid / position.alpha_balance

        # Fill in from Subnet table for any missing
        subnet_stmt = select(Subnet)
        subnet_result = await db.execute(subnet_stmt)
        for subnet in subnet_result.scalars().all():
            if subnet.netuid not in prices and subnet.alpha_price_tao:
                prices[subnet.netuid] = subnet.alpha_price_tao

        return prices

    async def _get_cost_basis_map(self, db: AsyncSession) -> Dict[int, PositionCostBasis]:
        """Get all cost basis records for the wallet."""
        stmt = select(PositionCostBasis).where(
            PositionCostBasis.wallet_address == self.wallet_address
        )
        result = await db.execute(stmt)
        return {cb.netuid: cb for cb in result.scalars().all()}

    async def _compute_position_metrics(
        self,
        db: AsyncSession,
        position: Position,
        alpha_price: Decimal,
        cost_basis: Optional[PositionCostBasis],
    ) -> None:
        """Compute and store all derived metrics for a single position.

        Formulas:
        - emission_alpha = alpha_balance - alpha_purchased
        - unrealized_yield_tao = emission_alpha × alpha_price (clamped >= 0)
        - unrealized_alpha_pnl_tao = alpha_purchased × (alpha_price - entry_price)
        - realized_yield_tao = from PositionCostBasis
        - realized_alpha_pnl_tao = realized_pnl_tao - realized_yield_tao
        - totals = yield + alpha_pnl (for verification)

        Args:
            db: Database session
            position: Position to update
            alpha_price: Current alpha price in TAO
            cost_basis: PositionCostBasis record (may be None for new positions)
        """
        # Get alpha_purchased from position (set by cost_basis service)
        alpha_purchased = position.alpha_purchased or Decimal("0")

        # 1. Compute emission alpha (yield component)
        # emission_alpha = tokens that grew from emissions, not purchased
        emission_alpha = position.alpha_balance - alpha_purchased
        if emission_alpha < 0:
            # Can happen if cost basis data is incomplete
            emission_alpha = Decimal("0")

        # 2. Compute unrealized yield
        # Yield = TAO value of emission alpha
        position.unrealized_yield_tao = emission_alpha * alpha_price

        # 3. Compute unrealized alpha P&L
        # Alpha P&L = price movement on purchased alpha
        entry_price = position.entry_price_tao or Decimal("0")
        if alpha_purchased > 0 and entry_price > 0 and alpha_price > 0:
            position.unrealized_alpha_pnl_tao = alpha_purchased * (alpha_price - entry_price)
        else:
            position.unrealized_alpha_pnl_tao = Decimal("0")

        # 4. Get realized values from cost basis
        if cost_basis:
            position.realized_yield_tao = cost_basis.realized_yield_tao or Decimal("0")
            # realized_alpha_pnl = total realized - yield portion
            total_realized = cost_basis.realized_pnl_tao or Decimal("0")
            position.realized_alpha_pnl_tao = total_realized - position.realized_yield_tao
        else:
            position.realized_yield_tao = Decimal("0")
            position.realized_alpha_pnl_tao = Decimal("0")

        # 5. Compute totals (for verification and backward compatibility)
        position.total_unrealized_pnl_tao = (
            position.unrealized_yield_tao + position.unrealized_alpha_pnl_tao
        )
        position.total_realized_pnl_tao = (
            position.realized_yield_tao + position.realized_alpha_pnl_tao
        )

        # 6. Update legacy fields for backward compatibility
        # These should match the totals
        position.unrealized_pnl_tao = position.total_unrealized_pnl_tao
        position.realized_pnl_tao = position.total_realized_pnl_tao

        # Compute percentage
        if position.cost_basis_tao and position.cost_basis_tao > 0:
            position.unrealized_pnl_pct = (
                position.unrealized_pnl_tao / position.cost_basis_tao
            ) * Decimal("100")
        else:
            position.unrealized_pnl_pct = Decimal("0")

        logger.debug(
            "Computed position metrics",
            netuid=position.netuid,
            alpha_balance=float(position.alpha_balance),
            alpha_purchased=float(alpha_purchased),
            emission_alpha=float(emission_alpha),
            alpha_price=float(alpha_price),
            unrealized_yield_tao=float(position.unrealized_yield_tao),
            unrealized_alpha_pnl_tao=float(position.unrealized_alpha_pnl_tao),
            realized_yield_tao=float(position.realized_yield_tao),
            realized_alpha_pnl_tao=float(position.realized_alpha_pnl_tao),
        )


# Module-level instance for convenience
position_metrics_service = PositionMetricsService()
