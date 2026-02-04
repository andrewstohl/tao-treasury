"""Performance attribution service – Phase 2.

Decomposes portfolio returns into:
  1. Yield Income     – TAO earned from validator emissions (alpha balance growth)
  2. Price Effect     – change in TAO value due to alpha token price movement
  3. Fees & Slippage  – transaction costs incurred in the period
  4. Total Return     – flow-adjusted total (earnings.py methodology)

Per-position contribution shows each position's share of total return.

Data sources:
  - PositionYieldHistory  → actual daily yield per position
  - PositionSnapshot      → start/end alpha prices for price decomposition
  - StakeTransaction      → fees paid
  - EarningsService       → flow-adjusted total return (proven methodology)
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position, PositionSnapshot
from app.models.portfolio import NAVHistory
from app.models.transaction import PositionYieldHistory, StakeTransaction
from app.services.analysis.earnings import get_earnings_service

logger = structlog.get_logger()

_ZERO = Decimal("0")


class AttributionService:
    """Decompose portfolio returns into yield, price, and fee components."""

    def __init__(self):
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def compute_attribution(
        self,
        days: int = 7,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute full portfolio attribution for the given look-back period.

        Returns:
            {
                period_days, start, end,
                nav_start, nav_end,
                total_return_tao, total_return_pct,
                yield_income_tao, yield_income_pct,
                price_effect_tao, price_effect_pct,
                fees_tao, fees_pct,
                net_flows_tao,
                waterfall: [{label, value_tao}...],
                position_contributions: [{netuid, name, return_tao, contribution_pct, weight_pct}...],
                income_statement: {yield, realized_gains, fees, net_income},
            }
        """
        wallet = wallet_address or self.settings.wallet_address
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        logger.info(
            "Computing attribution",
            wallet=wallet,
            days=days,
            start=start.isoformat(),
        )

        async with get_db_context() as db:
            # 1. Get flow-adjusted total return from earnings service
            earnings_svc = get_earnings_service()
            earnings = await earnings_svc.get_earnings_summary(
                start=start, end=now, wallet_address=wallet
            )

            total_return_tao = Decimal(earnings["total_earnings_tao"])
            nav_start = Decimal(earnings["total_start_value_tao"])
            nav_end = Decimal(earnings["total_end_value_tao"])
            net_flows = Decimal(earnings["total_net_flows_tao"])
            total_return_pct = Decimal(earnings["total_earnings_pct"])

            # 2. Sum actual yield income from PositionYieldHistory
            yield_tao = await self._sum_yield(db, wallet, start, now)

            # 3. Sum fees from StakeTransactions in period
            fees_tao = await self._sum_fees(db, wallet, start, now)

            # 4. Price effect = residual after yield and fees
            # Earnings service: total_return = end_value - start_value - net_flows
            # Fees are already embedded in end_value (lower balance), so:
            #   total_return = yield + price_effect - fees
            #   price_effect = total_return - yield + fees
            price_effect_tao = total_return_tao - yield_tao + fees_tao

            # Percentages relative to nav_start
            yield_pct = (yield_tao / nav_start * 100) if nav_start > 0 else _ZERO
            price_pct = (price_effect_tao / nav_start * 100) if nav_start > 0 else _ZERO
            fees_pct = (fees_tao / nav_start * 100) if nav_start > 0 else _ZERO

            # 5. Waterfall: Starting NAV → + Yield → +/- Price → - Fees → Ending NAV
            waterfall = [
                {"label": "Starting NAV", "value_tao": str(nav_start), "is_total": True},
                {"label": "Yield Income", "value_tao": str(yield_tao), "is_total": False},
                {"label": "Price Effect", "value_tao": str(price_effect_tao), "is_total": False},
                {"label": "Fees & Costs", "value_tao": str(-fees_tao), "is_total": False},
                {"label": "Net Flows", "value_tao": str(net_flows), "is_total": False},
                {"label": "Ending NAV", "value_tao": str(nav_end), "is_total": True},
            ]

            # 6. Per-position contribution
            contributions = await self._compute_position_contributions(
                db, wallet, start, now, earnings, nav_start
            )

            # 7. Income statement
            realized_pnl = await self._sum_realized_pnl(db, wallet, start, now)
            income_statement = {
                "yield_income_tao": str(yield_tao),
                "realized_gains_tao": str(realized_pnl),
                "fees_tao": str(fees_tao),
                "net_income_tao": str(yield_tao + realized_pnl - fees_tao),
            }

        return {
            "period_days": days,
            "start": start.isoformat(),
            "end": now.isoformat(),
            "nav_start_tao": str(nav_start),
            "nav_end_tao": str(nav_end),
            "total_return_tao": str(total_return_tao),
            "total_return_pct": str(_q2(total_return_pct)),
            "yield_income_tao": str(yield_tao),
            "yield_income_pct": str(_q2(yield_pct)),
            "price_effect_tao": str(price_effect_tao),
            "price_effect_pct": str(_q2(price_pct)),
            "fees_tao": str(fees_tao),
            "fees_pct": str(_q2(fees_pct)),
            "net_flows_tao": str(net_flows),
            "waterfall": waterfall,
            "position_contributions": contributions,
            "income_statement": income_statement,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sum_yield(
        self,
        db: AsyncSession,
        wallet: str,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        """Sum actual yield from PositionYieldHistory for the period."""
        stmt = select(func.coalesce(func.sum(PositionYieldHistory.yield_tao), 0)).where(
            and_(
                PositionYieldHistory.wallet_address == wallet,
                PositionYieldHistory.date >= start,
                PositionYieldHistory.date <= end,
            )
        )
        result = await db.execute(stmt)
        return result.scalar() or _ZERO

    async def _sum_fees(
        self,
        db: AsyncSession,
        wallet: str,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        """Sum transaction fees from StakeTransactions for the period."""
        stmt = select(func.coalesce(func.sum(StakeTransaction.fee_tao), 0)).where(
            and_(
                StakeTransaction.wallet_address == wallet,
                StakeTransaction.timestamp >= start,
                StakeTransaction.timestamp <= end,
                StakeTransaction.success == True,
            )
        )
        result = await db.execute(stmt)
        return result.scalar() or _ZERO

    async def _sum_realized_pnl(
        self,
        db: AsyncSession,
        wallet: str,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        """Sum realized P&L from unstake transactions in the period.

        Realized gain per unstake = amount_tao received - cost basis of lots sold.
        We approximate from StakeTransaction records where tx_type = 'unstake'.
        The cost_basis service tracks exact FIFO lots; here we use the
        execution_price vs entry_price differential.
        """
        stmt = select(StakeTransaction).where(
            and_(
                StakeTransaction.wallet_address == wallet,
                StakeTransaction.timestamp >= start,
                StakeTransaction.timestamp <= end,
                StakeTransaction.success == True,
                StakeTransaction.tx_type.in_(["unstake", "unstake_all"]),
            )
        )
        result = await db.execute(stmt)
        txns = result.scalars().all()

        realized = _ZERO
        for tx in txns:
            # Approximate realized P&L per unstake:
            # proceeds (amount_tao) minus estimated cost (alpha * limit_price).
            # limit_price ≈ entry price at time of stake for this lot.
            # This is an approximation; accurate FIFO-based P&L requires
            # PositionCostBasis snapshots (future enhancement).
            if tx.amount_tao and tx.alpha_amount and tx.limit_price:
                cost = tx.alpha_amount * tx.limit_price
                realized += tx.amount_tao - cost

        return realized

    async def _compute_position_contributions(
        self,
        db: AsyncSession,
        wallet: str,
        start: datetime,
        end: datetime,
        earnings: Dict[str, Any],
        nav_start: Decimal,
    ) -> List[Dict[str, Any]]:
        """Compute each position's contribution to total portfolio return."""
        by_netuid = earnings.get("by_netuid", [])
        if not by_netuid:
            return []

        # Get subnet names from current positions
        pos_stmt = select(Position.netuid, Position.subnet_name).where(
            Position.wallet_address == wallet
        )
        pos_result = await db.execute(pos_stmt)
        name_lookup = {row[0]: row[1] for row in pos_result.fetchall()}

        # Get per-position yield
        yield_stmt = (
            select(
                PositionYieldHistory.netuid,
                func.coalesce(func.sum(PositionYieldHistory.yield_tao), 0),
            )
            .where(
                and_(
                    PositionYieldHistory.wallet_address == wallet,
                    PositionYieldHistory.date >= start,
                    PositionYieldHistory.date <= end,
                )
            )
            .group_by(PositionYieldHistory.netuid)
        )
        yield_result = await db.execute(yield_stmt)
        yield_by_netuid = {row[0]: row[1] for row in yield_result.fetchall()}

        contributions = []
        for entry in by_netuid:
            netuid = entry["netuid"]
            pos_return = entry["earnings_tao"]
            pos_start = entry["start_value_tao"]
            pos_yield = yield_by_netuid.get(netuid, _ZERO)
            pos_price = pos_return - pos_yield  # residual

            # Weight at start of period
            weight_pct = (pos_start / nav_start * 100) if nav_start > 0 else _ZERO

            # Contribution to portfolio return
            contribution_pct = (pos_return / nav_start * 100) if nav_start > 0 else _ZERO

            contributions.append({
                "netuid": netuid,
                "subnet_name": name_lookup.get(netuid, f"SN{netuid}"),
                "start_value_tao": str(pos_start),
                "return_tao": str(pos_return),
                "return_pct": entry["earnings_pct"],
                "yield_tao": str(pos_yield),
                "price_effect_tao": str(pos_price),
                "weight_pct": str(_q2(weight_pct)),
                "contribution_pct": str(_q2(contribution_pct)),
            })

        # Sort by absolute contribution descending
        contributions.sort(key=lambda x: abs(Decimal(x["contribution_pct"])), reverse=True)
        return contributions


def _q2(d: Decimal) -> Decimal:
    """Quantize to 2 decimal places."""
    try:
        return d.quantize(Decimal("0.01"))
    except Exception:
        return d


# Lazy singleton
_attribution_service: Optional[AttributionService] = None


def get_attribution_service() -> AttributionService:
    global _attribution_service
    if _attribution_service is None:
        _attribution_service = AttributionService()
    return _attribution_service
