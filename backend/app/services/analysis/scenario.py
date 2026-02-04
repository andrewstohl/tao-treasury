"""TAO price sensitivity & scenario analysis service – Phase 3.

Computes:
  1. Price sensitivity table – portfolio USD value at TAO ±10/20/50%
  2. Stress scenarios – predefined what-if events
  3. Portfolio TAO beta – effective exposure multiplier

Data sources:
  - PortfolioSnapshot (nav_mid, tao_price_usd)
  - Position (tao_value_mid, alpha_balance, exit_slippage_100pct)
  - Subnet (alpha_price_tao)
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.portfolio import PortfolioSnapshot
from app.models.position import Position

logger = structlog.get_logger()

_ZERO = Decimal("0")

# TAO price shock levels for the sensitivity table
SENSITIVITY_SHOCKS = [-50, -20, -10, 0, 10, 20, 50]

# Pre-built stress scenarios
STRESS_SCENARIOS = [
    {
        "id": "tao_crash_30",
        "name": "TAO Crash (-30%)",
        "description": "TAO spot price drops 30%. Alpha token TAO values assumed unchanged (no contagion).",
        "tao_price_change_pct": -30,
        "alpha_impact_pct": 0,  # conservative: no contagion
    },
    {
        "id": "tao_crash_50_contagion",
        "name": "TAO Crash + dTAO Contagion (-50%)",
        "description": "TAO drops 50% and alpha tokens lose 20% of their TAO value due to panic selling.",
        "tao_price_change_pct": -50,
        "alpha_impact_pct": -20,
    },
    {
        "id": "tao_pump_50",
        "name": "TAO Pump (+50%)",
        "description": "TAO spot price rises 50%. Alpha TAO values assumed unchanged.",
        "tao_price_change_pct": 50,
        "alpha_impact_pct": 0,
    },
    {
        "id": "dtao_rotation",
        "name": "dTAO Rotation (-15% alpha)",
        "description": "Capital rotates out of dTAO positions. Alpha prices drop 15% in TAO terms. TAO price unchanged.",
        "tao_price_change_pct": 0,
        "alpha_impact_pct": -15,
    },
    {
        "id": "full_bull",
        "name": "Full Bull (+100% TAO, +20% alpha)",
        "description": "Strong market: TAO doubles and alpha tokens gain 20% in TAO terms.",
        "tao_price_change_pct": 100,
        "alpha_impact_pct": 20,
    },
]


class ScenarioService:
    """TAO price sensitivity and scenario analysis."""

    def __init__(self):
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def compute_scenarios(
        self,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute full sensitivity table and stress scenarios.

        Returns:
            {
                current_tao_price_usd,
                nav_tao, nav_usd,
                sensitivity: [{shock_pct, tao_price, nav_tao, nav_usd, usd_change, usd_change_pct}...],
                scenarios: [{id, name, desc, nav_tao, nav_usd, tao_change, alpha_change, usd_impact, usd_impact_pct}...],
                portfolio_beta,
            }
        """
        wallet = wallet_address or self.settings.wallet_address

        async with get_db_context() as db:
            # Get latest snapshot
            snap_stmt = (
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.wallet_address == wallet)
                .order_by(PortfolioSnapshot.timestamp.desc())
                .limit(1)
            )
            snap_result = await db.execute(snap_stmt)
            snapshot = snap_result.scalar_one_or_none()

            if snapshot is None:
                return self._empty_result()

            tao_price = float(snapshot.tao_price_usd or 0)
            nav_tao = float(snapshot.nav_mid or 0)
            nav_usd = nav_tao * tao_price

            # Get positions for alpha-specific analysis
            pos_stmt = (
                select(Position)
                .where(Position.wallet_address == wallet)
                .order_by(Position.tao_value_mid.desc())
            )
            pos_result = await db.execute(pos_stmt)
            positions = pos_result.scalars().all()

            # Separate root (SN0) from dTAO positions
            root_tao = float(snapshot.root_allocation_tao or 0)
            dtao_tao = float(snapshot.dtao_allocation_tao or 0)
            unstaked_tao = float(snapshot.unstaked_buffer_tao or 0)

            # 1. Sensitivity table
            sensitivity = []
            for shock_pct in SENSITIVITY_SHOCKS:
                new_tao_price = tao_price * (1 + shock_pct / 100)
                # NAV in TAO doesn't change with TAO price (it's TAO-denominated)
                new_nav_usd = nav_tao * new_tao_price
                usd_change = new_nav_usd - nav_usd
                usd_change_pct = (usd_change / nav_usd * 100) if nav_usd > 0 else 0

                sensitivity.append({
                    "shock_pct": shock_pct,
                    "tao_price_usd": round(new_tao_price, 2),
                    "nav_tao": round(nav_tao, 4),
                    "nav_usd": round(new_nav_usd, 2),
                    "usd_change": round(usd_change, 2),
                    "usd_change_pct": round(usd_change_pct, 2),
                })

            # 2. Stress scenarios
            scenarios = []
            for sc in STRESS_SCENARIOS:
                tao_change = sc["tao_price_change_pct"]
                alpha_change = sc["alpha_impact_pct"]

                new_tao_price = tao_price * (1 + tao_change / 100)

                # Root and unstaked TAO: only affected by TAO price
                # dTAO positions: affected by both TAO price and alpha price change
                new_root_tao = root_tao  # TAO value unchanged
                new_unstaked_tao = unstaked_tao
                new_dtao_tao = dtao_tao * (1 + alpha_change / 100)

                new_nav_tao = new_root_tao + new_dtao_tao + new_unstaked_tao
                new_nav_usd = new_nav_tao * new_tao_price

                tao_impact = new_nav_tao - nav_tao
                usd_impact = new_nav_usd - nav_usd
                usd_impact_pct = (usd_impact / nav_usd * 100) if nav_usd > 0 else 0

                scenarios.append({
                    "id": sc["id"],
                    "name": sc["name"],
                    "description": sc["description"],
                    "tao_price_change_pct": tao_change,
                    "alpha_impact_pct": alpha_change,
                    "new_tao_price_usd": round(new_tao_price, 2),
                    "nav_tao": round(new_nav_tao, 4),
                    "nav_usd": round(new_nav_usd, 2),
                    "tao_impact": round(tao_impact, 4),
                    "usd_impact": round(usd_impact, 2),
                    "usd_impact_pct": round(usd_impact_pct, 2),
                })

            # 3. Portfolio beta
            # Beta = 1.0 for TAO-only portfolio (linear exposure)
            # dTAO positions have additional alpha price risk
            # Effective beta ≈ 1 + (dtao_weight * alpha_correlation_to_tao)
            # Without historical correlation data, report exposure structure
            dtao_weight = (dtao_tao / nav_tao * 100) if nav_tao > 0 else 0
            root_weight = (root_tao / nav_tao * 100) if nav_tao > 0 else 0

            # Slippage-adjusted exit value (worst-case liquidation)
            total_slippage_tao = sum(
                float(p.tao_value_mid or 0) - float(p.tao_value_exec_100pct or 0)
                for p in positions
            )
            slippage_pct = (total_slippage_tao / nav_tao * 100) if nav_tao > 0 else 0

        return {
            "current_tao_price_usd": round(tao_price, 2),
            "nav_tao": round(nav_tao, 4),
            "nav_usd": round(nav_usd, 2),
            "allocation": {
                "root_tao": round(root_tao, 4),
                "root_pct": round(root_weight, 2),
                "dtao_tao": round(dtao_tao, 4),
                "dtao_pct": round(dtao_weight, 2),
                "unstaked_tao": round(unstaked_tao, 4),
            },
            "sensitivity": sensitivity,
            "scenarios": scenarios,
            "risk_exposure": {
                "tao_beta": 1.0,  # Base exposure: 1:1 to TAO price in USD
                "dtao_weight_pct": round(dtao_weight, 2),
                "root_weight_pct": round(root_weight, 2),
                "total_exit_slippage_pct": round(slippage_pct, 2),
                "total_exit_slippage_tao": round(total_slippage_tao, 4),
                "note": "Portfolio has 1:1 TAO/USD beta. dTAO positions add alpha price risk on top.",
            },
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "current_tao_price_usd": 0,
            "nav_tao": 0,
            "nav_usd": 0,
            "allocation": {
                "root_tao": 0, "root_pct": 0,
                "dtao_tao": 0, "dtao_pct": 0,
                "unstaked_tao": 0,
            },
            "sensitivity": [],
            "scenarios": [],
            "risk_exposure": {
                "tao_beta": 1.0,
                "dtao_weight_pct": 0,
                "root_weight_pct": 0,
                "total_exit_slippage_pct": 0,
                "total_exit_slippage_tao": 0,
                "note": "No data available",
            },
        }


# Lazy singleton
_scenario_service: Optional[ScenarioService] = None


def get_scenario_service() -> ScenarioService:
    global _scenario_service
    if _scenario_service is None:
        _scenario_service = ScenarioService()
    return _scenario_service
