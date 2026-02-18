"""Position metrics service.

Computes position-level yield and alpha P&L using authoritative data from
TaoStats accounting/tax API (via yield_tracker_service).

NO DERIVATIONS. All values come directly from API fields:
- total_yield_alpha: sum of daily_income from accounting/tax API
- alpha_purchased: sum of token_swap credits - debits

This ensures the ledger identity holds:
- Portfolio.yield = Sum(Position.yield)
- Portfolio.alpha_pnl = Sum(Position.alpha_pnl)
- Portfolio.total_pnl = Portfolio.yield + Portfolio.alpha_pnl
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional

import structlog
from sqlalchemy import select

from app.core.database import get_db_context
from app.models.position import Position
from app.models.transaction import PositionCostBasis
from app.services.analysis.yield_tracker import yield_tracker_service

logger = structlog.get_logger()


class PositionMetricsService:
    """Service for computing position metrics using authoritative API data.

    Uses yield_tracker_service to fetch data from TaoStats accounting/tax API.
    No derivations or estimations - all values come directly from API fields.
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

    async def compute_all_position_metrics(self, wallet_address: Optional[str] = None) -> Dict[str, Any]:
        """Compute metrics for all open positions using authoritative API data.

        Args:
            wallet_address: Specific wallet to process. If None, processes all active wallets.

        This should be called after:
        1. sync_positions() - to have current alpha balances

        Steps:
        1. Call yield_tracker to fetch data from accounting/tax API
        2. Aggregate the results

        Returns:
            Dict with computation results
        """
        logger.info("Computing position metrics from accounting/tax API", wallet=wallet_address)

        # Use yield_tracker to fetch authoritative data from accounting/tax API
        yield_results = await yield_tracker_service.compute_all_position_yields(wallet_address=wallet_address)

        # Get realized values from cost basis records
        realized_results = await self._compute_realized_metrics(wallet_address=wallet_address)

        # Combine results
        results = {
            "positions_processed": yield_results.get("positions_processed", 0),
            "total_unrealized_yield_tao": yield_results.get("total_yield_tao", Decimal("0")),
            "total_unrealized_alpha_pnl_tao": Decimal("0"),  # Will be computed by yield_tracker
            "total_realized_yield_tao": realized_results.get("total_realized_yield_tao", Decimal("0")),
            "total_realized_alpha_pnl_tao": realized_results.get("total_realized_alpha_pnl_tao", Decimal("0")),
            "errors": yield_results.get("errors", []) + realized_results.get("errors", []),
        }

        # Sum up unrealized alpha P&L from positions
        async with get_db_context() as db:
            stmt = select(Position)
            if wallet_address:
                stmt = stmt.where(Position.wallet_address == wallet_address)
            result = await db.execute(stmt)
            positions = result.scalars().all()

            for position in positions:
                results["total_unrealized_alpha_pnl_tao"] += (
                    position.unrealized_alpha_pnl_tao or Decimal("0")
                )

        logger.info("Position metrics computation completed", results=results)
        return results

    async def _compute_realized_metrics(self, wallet_address: Optional[str] = None) -> Dict[str, Any]:
        """Get realized yield and alpha P&L from cost basis records.

        Args:
            wallet_address: Specific wallet. If None, processes all active wallets.

        Realized values come from PositionCostBasis, which includes
        closed positions.
        """
        # Resolve wallets to process
        if wallet_address:
            wallets = [wallet_address]
        else:
            wallets = await self._get_active_wallets()

        results = {
            "total_realized_yield_tao": Decimal("0"),
            "total_realized_alpha_pnl_tao": Decimal("0"),
            "errors": [],
        }

        for wallet in wallets:
            try:
                async with get_db_context() as db:
                    # Get all cost basis records
                    stmt = select(PositionCostBasis).where(
                        PositionCostBasis.wallet_address == wallet
                    )
                    result = await db.execute(stmt)
                    cost_basis_records = result.scalars().all()

                    # Get positions to update realized values
                    pos_stmt = select(Position).where(
                        Position.wallet_address == wallet
                    )
                    pos_result = await db.execute(pos_stmt)
                    positions = {p.netuid: p for p in pos_result.scalars().all()}

                    for cb in cost_basis_records:
                        realized_yield = cb.realized_yield_tao or Decimal("0")
                        total_realized = cb.realized_pnl_tao or Decimal("0")
                        realized_alpha_pnl = total_realized - realized_yield

                        results["total_realized_yield_tao"] += realized_yield
                        results["total_realized_alpha_pnl_tao"] += realized_alpha_pnl

                        # Update position, creating if missing (backfill orphaned subnets)
                        if cb.netuid in positions:
                            position = positions[cb.netuid]
                        else:
                            # PositionCostBasis exists without a Position record.
                            # Create an inactive Position to hold realized values.
                            position = Position(
                                wallet_address=wallet,
                                netuid=cb.netuid,
                                subnet_name=f"Subnet {cb.netuid}",
                                alpha_balance=Decimal("0"),
                                tao_value_mid=Decimal("0"),
                                entry_date=cb.first_stake_at,
                            )
                            db.add(position)
                            positions[cb.netuid] = position
                            logger.info(
                                "Created Position for orphaned PositionCostBasis",
                                netuid=cb.netuid,
                            )

                        position.realized_yield_tao = realized_yield
                        position.realized_alpha_pnl_tao = realized_alpha_pnl
                        position.total_realized_pnl_tao = total_realized

                    await db.commit()

            except Exception as e:
                logger.error("Failed to compute realized metrics", wallet=wallet, error=str(e))
                results["errors"].append(str(e))

        return results


# Module-level instance for convenience
position_metrics_service = PositionMetricsService()
