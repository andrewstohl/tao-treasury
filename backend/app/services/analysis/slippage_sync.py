"""Slippage surface sync service.

Fetches and caches slippage estimates for all positions at standard sizes.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any

import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.slippage import SlippageSurface
from app.models.position import Position
from app.services.data.taostats_client import taostats_client

logger = structlog.get_logger()

# Standard trade sizes to cache slippage for (in TAO)
SLIPPAGE_SIZES = [Decimal("2"), Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")]

# Actions to compute slippage for
SLIPPAGE_ACTIONS = ["stake", "unstake"]


class SlippageSyncService:
    """Service for syncing slippage surfaces from TaoStats."""

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address

    async def sync_slippage_surfaces(self) -> Dict[str, Any]:
        """Sync slippage surfaces for all positions with stakes.

        Returns:
            Dict with sync results
        """
        logger.info("Starting slippage surface sync")

        results = {
            "positions_processed": 0,
            "surfaces_updated": 0,
            "errors": [],
        }

        try:
            async with get_db_context() as db:
                # Get all positions with alpha balance
                stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.alpha_balance > 0,
                )
                result = await db.execute(stmt)
                positions = list(result.scalars().all())

                for position in positions:
                    try:
                        count = await self._sync_position_slippage(db, position.netuid)
                        results["surfaces_updated"] += count
                        results["positions_processed"] += 1
                    except Exception as e:
                        logger.error("Failed to sync slippage", netuid=position.netuid, error=str(e))
                        results["errors"].append(f"SN{position.netuid}: {str(e)}")

                await db.commit()

            logger.info("Slippage sync completed", results=results)

        except Exception as e:
            logger.error("Slippage sync failed", error=str(e))
            results["errors"].append(str(e))

        return results

    async def _sync_position_slippage(self, db: AsyncSession, netuid: int) -> int:
        """Sync slippage surfaces for a single position.

        Returns:
            Number of surfaces updated
        """
        count = 0
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=5)  # Slippage expires quickly

        for action in SLIPPAGE_ACTIONS:
            for size in SLIPPAGE_SIZES:
                try:
                    # Fetch slippage from TaoStats
                    response = await taostats_client.get_slippage(
                        netuid=netuid,
                        amount=size,
                        action=action,
                    )

                    data = response.get("data", [{}])
                    if isinstance(data, list) and data:
                        slippage_data = data[0]
                    else:
                        slippage_data = data if isinstance(data, dict) else {}

                    # Extract slippage values
                    slippage_pct = Decimal(str(slippage_data.get("slippage_percentage", 0) or 0))
                    expected_output = Decimal(str(slippage_data.get("expected_output", 0) or 0))
                    tao_reserve = Decimal(str(slippage_data.get("tao_reserve", 0) or 0))
                    alpha_reserve = Decimal(str(slippage_data.get("alpha_reserve", 0) or 0))

                    # Upsert slippage surface
                    stmt = select(SlippageSurface).where(
                        SlippageSurface.netuid == netuid,
                        SlippageSurface.action == action,
                        SlippageSurface.size_tao == size,
                    )
                    result = await db.execute(stmt)
                    surface = result.scalar_one_or_none()

                    if surface is None:
                        surface = SlippageSurface(
                            netuid=netuid,
                            action=action,
                            size_tao=size,
                        )
                        db.add(surface)

                    surface.slippage_pct = slippage_pct
                    surface.expected_output = expected_output
                    surface.pool_tao_reserve = tao_reserve
                    surface.pool_alpha_reserve = alpha_reserve
                    surface.computed_at = now
                    surface.expires_at = expires_at

                    count += 1

                except Exception as e:
                    logger.warning(
                        "Failed to fetch slippage",
                        netuid=netuid,
                        action=action,
                        size=size,
                        error=str(e),
                    )

        logger.debug("Synced slippage surfaces", netuid=netuid, count=count)
        return count

    async def get_slippage(
        self,
        netuid: int,
        action: str,
        size_tao: Decimal
    ) -> Dict[str, Any]:
        """Get cached slippage for a position.

        Args:
            netuid: Subnet ID
            action: 'stake' or 'unstake'
            size_tao: Trade size in TAO

        Returns:
            Dict with slippage data or None if not found
        """
        async with get_db_context() as db:
            # Find closest size
            stmt = (
                select(SlippageSurface)
                .where(
                    SlippageSurface.netuid == netuid,
                    SlippageSurface.action == action,
                    SlippageSurface.size_tao >= size_tao,
                )
                .order_by(SlippageSurface.size_tao)
                .limit(1)
            )
            result = await db.execute(stmt)
            surface = result.scalar_one_or_none()

            if surface:
                return {
                    "netuid": netuid,
                    "action": action,
                    "size_tao": float(surface.size_tao),
                    "slippage_pct": float(surface.slippage_pct),
                    "expected_output": float(surface.expected_output),
                    "computed_at": surface.computed_at.isoformat() if surface.computed_at else None,
                    "expired": surface.expires_at and surface.expires_at < datetime.now(timezone.utc),
                }

            return None

    async def interpolate_slippage(
        self,
        netuid: int,
        action: str,
        size_tao: Decimal
    ) -> Decimal:
        """Interpolate slippage percentage for a given size.

        Uses linear interpolation between cached sizes.

        Args:
            netuid: Subnet ID
            action: 'stake' or 'unstake'
            size_tao: Trade size in TAO

        Returns:
            Estimated slippage percentage
        """
        async with get_db_context() as db:
            # Get all surfaces for this position/action
            stmt = (
                select(SlippageSurface)
                .where(
                    SlippageSurface.netuid == netuid,
                    SlippageSurface.action == action,
                )
                .order_by(SlippageSurface.size_tao)
            )
            result = await db.execute(stmt)
            surfaces = list(result.scalars().all())

            if not surfaces:
                return Decimal("0")

            # Find bracketing surfaces
            lower = None
            upper = None

            for s in surfaces:
                if s.size_tao <= size_tao:
                    lower = s
                if s.size_tao >= size_tao and upper is None:
                    upper = s

            if lower is None:
                # Size is below smallest cached size
                return surfaces[0].slippage_pct

            if upper is None:
                # Size is above largest cached size - extrapolate
                return surfaces[-1].slippage_pct

            if lower.size_tao == upper.size_tao:
                return lower.slippage_pct

            # Linear interpolation
            ratio = (size_tao - lower.size_tao) / (upper.size_tao - lower.size_tao)
            slippage = lower.slippage_pct + ratio * (upper.slippage_pct - lower.slippage_pct)

            return slippage

    async def cleanup_expired(self) -> int:
        """Remove expired slippage surfaces.

        Returns:
            Number of surfaces removed
        """
        async with get_db_context() as db:
            now = datetime.now(timezone.utc)
            stmt = delete(SlippageSurface).where(SlippageSurface.expires_at < now)
            result = await db.execute(stmt)
            await db.commit()

            deleted = result.rowcount
            if deleted > 0:
                logger.info("Cleaned up expired slippage surfaces", count=deleted)

            return deleted


# Lazy singleton instance
_slippage_sync_service: SlippageSyncService | None = None


def get_slippage_sync_service() -> SlippageSyncService:
    """Get or create the slippage sync service singleton."""
    global _slippage_sync_service
    if _slippage_sync_service is None:
        _slippage_sync_service = SlippageSyncService()
    return _slippage_sync_service


class _LazySlippageSyncService:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_slippage_sync_service(), name)


slippage_sync_service = _LazySlippageSyncService()
