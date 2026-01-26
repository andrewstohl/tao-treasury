"""NAV Calculator with executable pricing.

Computes Net Asset Value using exit slippage to get "executable" prices.
Per spec: NAV must be computed with slippage at exit, not mid prices.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.models.portfolio import PortfolioSnapshot, NAVHistory
from app.models.slippage import SlippageSurface
from app.services.analysis.slippage_sync import get_slippage_sync_service

logger = structlog.get_logger()

# Default slippage assumption when not available
DEFAULT_SLIPPAGE_PCT = Decimal("0.02")  # 2% conservative default


class NAVCalculator:
    """Calculates Net Asset Value with executable pricing."""

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address

    async def compute_portfolio_nav(
        self,
        save_snapshot: bool = True
    ) -> Dict[str, Any]:
        """Compute portfolio NAV with executable pricing.

        Args:
            save_snapshot: Whether to save a portfolio snapshot

        Returns:
            Dict with NAV breakdown
        """
        logger.info("Computing portfolio NAV")

        async with get_db_context() as db:
            # Get all positions
            stmt = select(Position).where(
                Position.wallet_address == self.wallet_address
            )
            result = await db.execute(stmt)
            positions = list(result.scalars().all())

            # Compute NAV for each position
            nav_breakdown = []
            total_nav_mid = Decimal("0")
            total_nav_executable = Decimal("0")
            total_cost_basis = Decimal("0")
            position_count = 0

            for position in positions:
                if position.alpha_balance <= 0:
                    continue

                position_count += 1
                pos_nav = await self._compute_position_nav(db, position)
                nav_breakdown.append(pos_nav)

                total_nav_mid += pos_nav["nav_mid_tao"]
                total_nav_executable += pos_nav["nav_executable_tao"]
                total_cost_basis += pos_nav["cost_basis_tao"]

            # Compute totals
            total_slippage = total_nav_mid - total_nav_executable
            total_slippage_pct = (
                (total_slippage / total_nav_mid * 100) if total_nav_mid > 0 else Decimal("0")
            )

            # Compute P&L
            total_unrealized_pnl = total_nav_executable - total_cost_basis
            total_unrealized_pnl_pct = (
                (total_unrealized_pnl / total_cost_basis * 100)
                if total_cost_basis > 0 else Decimal("0")
            )

            nav_result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "position_count": position_count,
                "nav_mid_tao": total_nav_mid,
                "nav_executable_tao": total_nav_executable,
                "total_slippage_tao": total_slippage,
                "total_slippage_pct": total_slippage_pct,
                "cost_basis_tao": total_cost_basis,
                "unrealized_pnl_tao": total_unrealized_pnl,
                "unrealized_pnl_pct": total_unrealized_pnl_pct,
                "positions": nav_breakdown,
            }

            if save_snapshot:
                await self._save_nav_snapshot(db, nav_result)
                await db.commit()

            logger.info(
                "NAV computed",
                nav_mid=total_nav_mid,
                nav_executable=total_nav_executable,
                slippage_pct=total_slippage_pct,
            )

            return nav_result

    async def _compute_position_nav(
        self,
        db: AsyncSession,
        position: Position
    ) -> Dict[str, Any]:
        """Compute NAV for a single position.

        Args:
            position: Position to compute NAV for

        Returns:
            Dict with position NAV breakdown
        """
        # Mid valuation (no slippage)
        nav_mid = position.tao_value_mid or Decimal("0")

        # Get slippage for unstaking full position
        # Use the position's TAO value as the trade size
        slippage_pct = await self._get_exit_slippage(
            db, position.netuid, nav_mid
        )

        # Executable NAV = mid NAV * (1 - slippage)
        nav_executable = nav_mid * (Decimal("1") - slippage_pct)

        # Cost basis
        cost_basis = position.cost_basis_tao or Decimal("0")

        # Unrealized P&L
        unrealized_pnl = nav_executable - cost_basis
        unrealized_pnl_pct = (
            (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else Decimal("0")
        )

        return {
            "netuid": position.netuid,
            "subnet_name": position.subnet_name,
            "alpha_balance": position.alpha_balance,
            "nav_mid_tao": nav_mid,
            "slippage_pct": slippage_pct * 100,  # As percentage
            "nav_executable_tao": nav_executable,
            "cost_basis_tao": cost_basis,
            "unrealized_pnl_tao": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
        }

    async def _get_exit_slippage(
        self,
        db: AsyncSession,
        netuid: int,
        amount_tao: Decimal
    ) -> Decimal:
        """Get exit slippage for a position.

        Interpolates from cached slippage surface.

        Args:
            netuid: Subnet ID
            amount_tao: Amount to exit in TAO

        Returns:
            Slippage as decimal (0.02 = 2%)
        """
        # Root network has no slippage
        if netuid == 0:
            return Decimal("0")

        # Try to get from cached surface
        try:
            slippage_pct = await get_slippage_sync_service().interpolate_slippage(
                netuid=netuid,
                action="unstake",
                size_tao=amount_tao,
            )

            if slippage_pct > 0:
                return slippage_pct / 100  # Convert from percentage to decimal

        except Exception as e:
            logger.warning(
                "Failed to get cached slippage, using default",
                netuid=netuid,
                error=str(e),
            )

        # Default conservative slippage
        return DEFAULT_SLIPPAGE_PCT

    async def _save_nav_snapshot(
        self,
        db: AsyncSession,
        nav_result: Dict[str, Any]
    ) -> None:
        """Save NAV snapshot to history table (OHLC format)."""
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        nav_mid = nav_result["nav_mid_tao"]
        nav_exec = nav_result["nav_executable_tao"]

        # Check if we have an entry for today
        stmt = select(NAVHistory).where(
            NAVHistory.wallet_address == self.wallet_address,
            NAVHistory.date >= today,
            NAVHistory.date < today + timedelta(days=1),
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing entry with OHLC logic
            existing.nav_mid_high = max(existing.nav_mid_high, nav_mid)
            existing.nav_mid_low = min(existing.nav_mid_low, nav_mid)
            existing.nav_mid_close = nav_mid

            existing.nav_exec_high = max(existing.nav_exec_high, nav_exec)
            existing.nav_exec_low = min(existing.nav_exec_low, nav_exec)
            existing.nav_exec_close = nav_exec

            # Update ATH if needed
            existing.nav_exec_ath = max(existing.nav_exec_ath, nav_exec)
        else:
            # Get previous day's close for return calculation
            stmt = select(NAVHistory).where(
                NAVHistory.wallet_address == self.wallet_address,
            ).order_by(NAVHistory.date.desc()).limit(1)
            result = await db.execute(stmt)
            prev_day = result.scalar_one_or_none()

            prev_nav = prev_day.nav_exec_close if prev_day else nav_exec
            prev_ath = prev_day.nav_exec_ath if prev_day else Decimal("0")

            daily_return_tao = nav_exec - prev_nav
            daily_return_pct = (daily_return_tao / prev_nav * 100) if prev_nav > 0 else Decimal("0")

            nav_history = NAVHistory(
                wallet_address=self.wallet_address,
                date=now,
                nav_mid_open=nav_mid,
                nav_mid_high=nav_mid,
                nav_mid_low=nav_mid,
                nav_mid_close=nav_mid,
                nav_exec_open=nav_exec,
                nav_exec_high=nav_exec,
                nav_exec_low=nav_exec,
                nav_exec_close=nav_exec,
                nav_exec_ath=max(prev_ath, nav_exec),
                daily_return_tao=daily_return_tao,
                daily_return_pct=daily_return_pct,
            )
            db.add(nav_history)

        logger.debug("Saved NAV snapshot", nav_exec=nav_exec)

    async def get_nav_history(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get NAV history for the portfolio.

        Args:
            days: Number of days of history to fetch

        Returns:
            List of NAV snapshots
        """
        async with get_db_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            stmt = (
                select(NAVHistory)
                .where(
                    NAVHistory.wallet_address == self.wallet_address,
                    NAVHistory.date >= cutoff,
                )
                .order_by(NAVHistory.date)
            )
            result = await db.execute(stmt)
            history = result.scalars().all()

            return [
                {
                    "date": h.date.isoformat(),
                    "nav_mid_close": float(h.nav_mid_close),
                    "nav_exec_close": float(h.nav_exec_close),
                    "nav_exec_ath": float(h.nav_exec_ath),
                    "daily_return_pct": float(h.daily_return_pct),
                }
                for h in history
            ]

    async def get_latest_nav(self) -> Optional[Dict[str, Any]]:
        """Get the most recent NAV snapshot.

        Returns:
            Latest NAV data or None
        """
        async with get_db_context() as db:
            stmt = (
                select(NAVHistory)
                .where(NAVHistory.wallet_address == self.wallet_address)
                .order_by(NAVHistory.date.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            latest = result.scalar_one_or_none()

            if latest:
                return {
                    "date": latest.date.isoformat(),
                    "nav_mid_close": float(latest.nav_mid_close),
                    "nav_exec_close": float(latest.nav_exec_close),
                    "nav_exec_ath": float(latest.nav_exec_ath),
                    "daily_return_pct": float(latest.daily_return_pct),
                }

            return None


# Lazy singleton instance
_nav_calculator: NAVCalculator | None = None


def get_nav_calculator() -> NAVCalculator:
    """Get or create the NAV calculator singleton."""
    global _nav_calculator
    if _nav_calculator is None:
        _nav_calculator = NAVCalculator()
    return _nav_calculator


class _LazyNAVCalculator:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_nav_calculator(), name)


nav_calculator = _LazyNAVCalculator()
