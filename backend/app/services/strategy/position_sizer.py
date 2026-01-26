"""Position sizer for computing maximum position sizes.

Implements three-tier cap enforcement per spec:
1. Exitability cap - Max size that can exit at acceptable slippage
2. Concentration cap - Max 15% of portfolio per position
3. Category cap - Max 30% to any category within sleeve

The binding (smallest) cap determines the position limit.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.subnet import Subnet
from app.models.position import Position
from app.models.slippage import SlippageSurface

logger = structlog.get_logger()


@dataclass
class PositionLimit:
    """Computed position size limit for a subnet."""
    netuid: int
    subnet_name: str

    # Individual caps (all in TAO)
    exitability_cap_tao: Decimal
    concentration_cap_tao: Decimal
    category_cap_tao: Decimal

    # Binding cap (minimum of the three)
    max_position_tao: Decimal
    binding_constraint: str  # 'exitability', 'concentration', or 'category'

    # Current position for comparison
    current_position_tao: Decimal

    # Headroom
    available_headroom_tao: Decimal

    # Explanation
    explanation: str


class PositionSizer:
    """Computes position size limits based on three-tier cap system."""

    def __init__(self):
        settings = get_settings()
        # Slippage thresholds
        self.max_slip_50pct = settings.max_exit_slippage_50pct
        self.max_slip_100pct = settings.max_exit_slippage_100pct

        # Concentration limits
        self.max_position_pct = settings.max_position_concentration
        self.default_position_pct = settings.default_position_concentration

        # Category limits (within sleeve)
        self.max_category_pct = settings.max_category_concentration_sleeve

        # Store wallet address for queries
        self._wallet_address = settings.wallet_address

    async def compute_position_limit(
        self,
        netuid: int,
        portfolio_nav_tao: Decimal,
        sleeve_nav_tao: Decimal,
        category_allocations: Dict[str, Decimal],
        db: Optional[AsyncSession] = None,
    ) -> PositionLimit:
        """Compute position limit for a subnet using three-tier caps.

        Args:
            netuid: Subnet to compute limit for
            portfolio_nav_tao: Total portfolio NAV in TAO
            sleeve_nav_tao: dTAO sleeve NAV in TAO
            category_allocations: Current TAO allocation by category
            db: Optional database session

        Returns:
            PositionLimit with binding cap and explanation
        """
        async def _compute(session: AsyncSession) -> PositionLimit:
            # Get subnet info
            stmt = select(Subnet).where(Subnet.netuid == netuid)
            result = await session.execute(stmt)
            subnet = result.scalar_one_or_none()

            if not subnet:
                return self._create_zero_limit(netuid, "Subnet not found")

            # Get current position
            pos_stmt = select(Position).where(
                Position.netuid == netuid,
                Position.wallet_address == self._wallet_address,
            )
            pos_result = await session.execute(pos_stmt)
            position = pos_result.scalar_one_or_none()
            current_pos_tao = position.tao_value_mid if position else Decimal("0")

            # 1. Exitability cap - max size that can exit at acceptable slippage
            exitability_cap = await self._compute_exitability_cap(
                session, netuid, current_pos_tao
            )

            # 2. Concentration cap - max % of portfolio
            concentration_cap = portfolio_nav_tao * self.max_position_pct

            # 3. Category cap - max % of sleeve to any category
            category = subnet.category or "uncategorized"
            current_category_alloc = category_allocations.get(category, Decimal("0"))
            # Available category headroom = (max_category_pct * sleeve) - current_category - current_position
            # Because current_position is already in category allocation
            max_category_tao = sleeve_nav_tao * self.max_category_pct
            category_headroom = max_category_tao - current_category_alloc + current_pos_tao
            category_cap = max(Decimal("0"), category_headroom)

            # Find binding cap (minimum)
            caps = {
                "exitability": exitability_cap,
                "concentration": concentration_cap,
                "category": category_cap,
            }
            binding_constraint = min(caps, key=caps.get)
            max_position = caps[binding_constraint]

            # Calculate headroom
            headroom = max(Decimal("0"), max_position - current_pos_tao)

            # Build explanation
            explanation = self._build_explanation(
                subnet_name=subnet.name,
                exitability_cap=exitability_cap,
                concentration_cap=concentration_cap,
                category_cap=category_cap,
                category=category,
                binding=binding_constraint,
                current_pos=current_pos_tao,
                max_pos=max_position,
            )

            return PositionLimit(
                netuid=netuid,
                subnet_name=subnet.name,
                exitability_cap_tao=exitability_cap,
                concentration_cap_tao=concentration_cap,
                category_cap_tao=category_cap,
                max_position_tao=max_position,
                binding_constraint=binding_constraint,
                current_position_tao=current_pos_tao,
                available_headroom_tao=headroom,
                explanation=explanation,
            )

        if db:
            return await _compute(db)
        else:
            async with get_db_context() as session:
                return await _compute(session)

    async def _compute_exitability_cap(
        self,
        db: AsyncSession,
        netuid: int,
        current_position_tao: Decimal,
    ) -> Decimal:
        """Compute max position size based on exit slippage constraints.

        Returns the maximum position size where:
        - 50% exit slippage <= 5%
        - 100% exit slippage <= 10%
        """
        # Get slippage surfaces for unstake
        stmt = select(SlippageSurface).where(
            SlippageSurface.netuid == netuid,
            SlippageSurface.action == "unstake",
        ).order_by(SlippageSurface.size_tao)

        result = await db.execute(stmt)
        surfaces = list(result.scalars().all())

        if not surfaces:
            # No slippage data - use conservative default based on liquidity
            stmt = select(Subnet.pool_tao_reserve).where(Subnet.netuid == netuid)
            result = await db.execute(stmt)
            liquidity = result.scalar() or Decimal("0")
            # Conservative: cap at 2% of pool liquidity if no slippage data
            return liquidity * Decimal("0.02")

        # Find max size where both constraints hold:
        # - slip(50% of size) <= 5%
        # - slip(100% of size) <= 10%

        # Binary search for the max acceptable size
        low = Decimal("0")
        high = surfaces[-1].size_tao * 2  # Upper bound

        for _ in range(20):  # ~20 iterations for good precision
            mid = (low + high) / 2

            # Check slippage at 50% and 100% of this size
            slip_50 = self._interpolate_slippage(surfaces, mid * Decimal("0.5"))
            slip_100 = self._interpolate_slippage(surfaces, mid)

            if slip_50 <= self.max_slip_50pct and slip_100 <= self.max_slip_100pct:
                low = mid  # Can go higher
            else:
                high = mid  # Need to go lower

        return low

    def _interpolate_slippage(
        self,
        surfaces: List[SlippageSurface],
        size_tao: Decimal
    ) -> Decimal:
        """Interpolate slippage for a given size from cached surfaces."""
        if not surfaces:
            return Decimal("0.10")  # Default high if no data

        # Find bracketing surfaces
        lower = None
        upper = None

        for s in surfaces:
            if s.size_tao <= size_tao:
                lower = s
            if s.size_tao >= size_tao and upper is None:
                upper = s

        if lower is None:
            return surfaces[0].slippage_pct

        if upper is None:
            # Extrapolate - slippage grows faster for larger sizes
            # Use last two points to estimate slope
            if len(surfaces) >= 2:
                s1, s2 = surfaces[-2], surfaces[-1]
                if s2.size_tao > s1.size_tao:
                    slope = (s2.slippage_pct - s1.slippage_pct) / (s2.size_tao - s1.size_tao)
                    extra = size_tao - s2.size_tao
                    return s2.slippage_pct + slope * extra * Decimal("1.5")  # 1.5x for safety
            return surfaces[-1].slippage_pct * Decimal("1.5")

        if lower.size_tao == upper.size_tao:
            return lower.slippage_pct

        # Linear interpolation
        ratio = (size_tao - lower.size_tao) / (upper.size_tao - lower.size_tao)
        return lower.slippage_pct + ratio * (upper.slippage_pct - lower.slippage_pct)

    def _build_explanation(
        self,
        subnet_name: str,
        exitability_cap: Decimal,
        concentration_cap: Decimal,
        category_cap: Decimal,
        category: str,
        binding: str,
        current_pos: Decimal,
        max_pos: Decimal,
    ) -> str:
        """Build human-readable explanation of the position limit."""
        lines = [f"Position limit for {subnet_name}:"]

        def fmt(val: Decimal) -> str:
            return f"{float(val):,.1f} TAO"

        # Show all caps
        markers = {
            "exitability": "→" if binding == "exitability" else " ",
            "concentration": "→" if binding == "concentration" else " ",
            "category": "→" if binding == "category" else " ",
        }

        lines.append(f"{markers['exitability']} Exitability cap: {fmt(exitability_cap)} (5%/10% slip limits)")
        lines.append(f"{markers['concentration']} Concentration cap: {fmt(concentration_cap)} (15% of portfolio)")
        lines.append(f"{markers['category']} Category cap ({category}): {fmt(category_cap)} (30% of sleeve)")
        lines.append(f"Current: {fmt(current_pos)} | Max: {fmt(max_pos)} | Headroom: {fmt(max_pos - current_pos)}")

        return "\n".join(lines)

    async def compute_all_limits(
        self,
        portfolio_nav_tao: Decimal,
        sleeve_nav_tao: Decimal,
    ) -> List[PositionLimit]:
        """Compute position limits for all eligible subnets.

        Returns:
            List of PositionLimit for all eligible subnets
        """
        limits = []

        async with get_db_context() as db:
            # Get all eligible subnets
            stmt = select(Subnet).where(Subnet.is_eligible == True)
            result = await db.execute(stmt)
            subnets = list(result.scalars().all())

            # Get current positions for category allocation calculation
            pos_stmt = select(Position).where(
                Position.wallet_address == self._wallet_address
            )
            pos_result = await db.execute(pos_stmt)
            positions = list(pos_result.scalars().all())

            # Build category allocations
            category_allocations: Dict[str, Decimal] = {}
            for pos in positions:
                # Find subnet to get category
                subnet = next((s for s in subnets if s.netuid == pos.netuid), None)
                if subnet:
                    category = subnet.category or "uncategorized"
                    category_allocations[category] = (
                        category_allocations.get(category, Decimal("0")) + pos.tao_value_mid
                    )

            # Compute limits for each eligible subnet
            for subnet in subnets:
                limit = await self.compute_position_limit(
                    netuid=subnet.netuid,
                    portfolio_nav_tao=portfolio_nav_tao,
                    sleeve_nav_tao=sleeve_nav_tao,
                    category_allocations=category_allocations,
                    db=db,
                )
                limits.append(limit)

        # Sort by available headroom (most room first)
        limits.sort(key=lambda x: x.available_headroom_tao, reverse=True)

        return limits

    async def get_target_position_size(
        self,
        netuid: int,
        portfolio_nav_tao: Decimal,
        sleeve_nav_tao: Decimal,
        category_allocations: Dict[str, Decimal],
    ) -> Tuple[Decimal, str]:
        """Get target position size respecting all constraints.

        Returns:
            Tuple of (target_size_tao, explanation)
        """
        limit = await self.compute_position_limit(
            netuid=netuid,
            portfolio_nav_tao=portfolio_nav_tao,
            sleeve_nav_tao=sleeve_nav_tao,
            category_allocations=category_allocations,
        )

        # Target is the default concentration, capped by the binding limit
        default_target = portfolio_nav_tao * self.default_position_pct
        target = min(default_target, limit.max_position_tao)

        explanation = (
            f"Target: {float(target):,.1f} TAO "
            f"(default {float(self.default_position_pct)*100:.0f}% = {float(default_target):,.1f} TAO, "
            f"capped by {limit.binding_constraint} at {float(limit.max_position_tao):,.1f} TAO)"
        )

        return target, explanation


# Lazy singleton instance
_position_sizer: Optional[PositionSizer] = None


def get_position_sizer() -> PositionSizer:
    """Get or create the PositionSizer singleton.

    Instance is created on first access, not at import time.
    """
    global _position_sizer
    if _position_sizer is None:
        _position_sizer = PositionSizer()
    return _position_sizer


class _LazyPositionSizer:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_position_sizer(), name)


position_sizer = _LazyPositionSizer()
