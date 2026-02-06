"""Accounting validation service.

Compares our internal calculations with TaoStats to flag discrepancies.
Used for data quality assurance and debugging accounting issues.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, func

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.models.transaction import PositionCostBasis
from app.services.data.taostats_client import get_taostats_client
from app.services.analysis.yield_calculator import get_yield_calculator

logger = structlog.get_logger()


class AccountingValidatorService:
    """Service for validating accounting data against TaoStats.

    Compares:
    1. Yield calculations (our emission method vs TaoStats balance history method)
    2. Unrealized P&L (our calculation vs position value changes)
    3. Cost basis (our FIFO tracking vs TaoStats accounting data)
    """

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address
        self.discrepancy_threshold_pct = Decimal("5.0")  # 5% threshold for warnings

    async def validate_all(self) -> Dict[str, Any]:
        """Run all validation checks.

        Returns:
            Dict with validation results:
                - is_valid: Overall validation status
                - warnings: List of warning messages
                - details: Per-metric validation details
        """
        results = {
            "is_valid": True,
            "warnings": [],
            "details": {},
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Validate yield calculation
            yield_result = await self.validate_yield()
            results["details"]["yield"] = yield_result
            if yield_result.get("has_warning"):
                results["is_valid"] = False
                results["warnings"].append(yield_result.get("warning"))

            # Validate unrealized P&L
            pnl_result = await self.validate_unrealized_pnl()
            results["details"]["unrealized_pnl"] = pnl_result
            if pnl_result.get("has_warning"):
                results["is_valid"] = False
                results["warnings"].append(pnl_result.get("warning"))

            # Validate cost basis completeness
            cb_result = await self.validate_cost_basis()
            results["details"]["cost_basis"] = cb_result
            if cb_result.get("has_warning"):
                results["is_valid"] = False
                results["warnings"].append(cb_result.get("warning"))

        except Exception as e:
            logger.error("Validation failed", error=str(e))
            results["is_valid"] = False
            results["warnings"].append(f"Validation error: {str(e)}")

        return results

    async def validate_yield(self) -> Dict[str, Any]:
        """Validate yield calculation against TaoStats method.

        Compares our emission-based yield with TaoStats balance history method.
        """
        result = {
            "has_warning": False,
            "warning": None,
            "our_yield_tao": Decimal("0"),
            "taostats_yield_tao": Decimal("0"),
            "discrepancy_tao": Decimal("0"),
            "discrepancy_pct": Decimal("0"),
        }

        try:
            # Get our calculated yield
            async with get_db_context() as db:
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.alpha_balance > 0,
                )
                pos_result = await db.execute(pos_stmt)
                positions = list(pos_result.scalars().all())

            our_yield = Decimal("0")
            for pos in positions:
                if not pos.alpha_balance or pos.alpha_balance <= 0:
                    continue
                if not pos.tao_value_mid or pos.tao_value_mid <= 0:
                    continue

                alpha_purchased = pos.alpha_purchased or Decimal("0")
                if alpha_purchased <= 0 and pos.entry_price_tao and pos.entry_price_tao > 0 and pos.cost_basis_tao:
                    alpha_purchased = pos.cost_basis_tao / pos.entry_price_tao

                emission_alpha = pos.alpha_balance - alpha_purchased
                if emission_alpha > 0:
                    current_alpha_price = pos.tao_value_mid / pos.alpha_balance
                    our_yield += emission_alpha * current_alpha_price

            result["our_yield_tao"] = our_yield

            # Get TaoStats-method yield
            yield_calc = get_yield_calculator()
            taostats_yield_result = await yield_calc.compute_portfolio_yield(days=30)

            taostats_yield = taostats_yield_result.get("total_yield_tao", Decimal("0"))
            if isinstance(taostats_yield, (int, float)):
                taostats_yield = Decimal(str(taostats_yield))

            result["taostats_yield_tao"] = taostats_yield

            # Calculate discrepancy
            if taostats_yield > 0:
                discrepancy = abs(our_yield - taostats_yield)
                discrepancy_pct = (discrepancy / taostats_yield) * 100

                result["discrepancy_tao"] = discrepancy
                result["discrepancy_pct"] = discrepancy_pct

                if discrepancy_pct > self.discrepancy_threshold_pct:
                    result["has_warning"] = True
                    result["warning"] = (
                        f"Yield differs by {float(discrepancy):.2f}τ ({float(discrepancy_pct):.1f}%) "
                        f"vs TaoStats method"
                    )

        except Exception as e:
            logger.error("Yield validation failed", error=str(e))
            result["has_warning"] = True
            result["warning"] = f"Yield validation error: {str(e)}"

        return result

    async def validate_unrealized_pnl(self) -> Dict[str, Any]:
        """Validate unrealized P&L calculation.

        Compares our calculated unrealized P&L with the sum of position-level values.
        """
        result = {
            "has_warning": False,
            "warning": None,
            "calculated_pnl_tao": Decimal("0"),
            "sum_position_pnl_tao": Decimal("0"),
            "discrepancy_tao": Decimal("0"),
        }

        try:
            async with get_db_context() as db:
                # Get sum of position-level unrealized P&L
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.alpha_balance > 0,
                )
                pos_result = await db.execute(pos_stmt)
                positions = list(pos_result.scalars().all())

            sum_pnl = Decimal("0")
            calculated_pnl = Decimal("0")

            for pos in positions:
                # Sum from position records
                sum_pnl += pos.unrealized_pnl_tao or Decimal("0")

                # Recalculate: current value - cost basis
                current_value = pos.tao_value_mid or Decimal("0")
                cost_basis = pos.cost_basis_tao or Decimal("0")
                calculated_pnl += current_value - cost_basis

            result["sum_position_pnl_tao"] = sum_pnl
            result["calculated_pnl_tao"] = calculated_pnl

            discrepancy = abs(sum_pnl - calculated_pnl)
            result["discrepancy_tao"] = discrepancy

            # Check if stored values match calculated
            if discrepancy > Decimal("0.01"):  # More than 0.01 TAO difference
                result["has_warning"] = True
                result["warning"] = (
                    f"Unrealized P&L mismatch: stored {float(sum_pnl):.4f}τ "
                    f"vs calculated {float(calculated_pnl):.4f}τ"
                )

        except Exception as e:
            logger.error("P&L validation failed", error=str(e))
            result["has_warning"] = True
            result["warning"] = f"P&L validation error: {str(e)}"

        return result

    async def validate_cost_basis(self) -> Dict[str, Any]:
        """Validate cost basis data completeness.

        Checks that all open positions have cost basis records and that
        alpha_purchased values are populated.
        """
        result = {
            "has_warning": False,
            "warning": None,
            "total_positions": 0,
            "positions_with_cost_basis": 0,
            "positions_with_alpha_purchased": 0,
            "missing_cost_basis": [],
            "missing_alpha_purchased": [],
        }

        try:
            async with get_db_context() as db:
                # Get all open positions
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.alpha_balance > 0,
                )
                pos_result = await db.execute(pos_stmt)
                positions = list(pos_result.scalars().all())

                result["total_positions"] = len(positions)

                # Get cost basis records
                cb_stmt = select(PositionCostBasis).where(
                    PositionCostBasis.wallet_address == self.wallet_address,
                )
                cb_result = await db.execute(cb_stmt)
                cb_by_netuid = {cb.netuid: cb for cb in cb_result.scalars().all()}

            for pos in positions:
                # Check cost basis record exists
                cb = cb_by_netuid.get(pos.netuid)
                if cb and cb.total_staked_tao > 0:
                    result["positions_with_cost_basis"] += 1
                else:
                    result["missing_cost_basis"].append(pos.netuid)

                # Check alpha_purchased is populated
                if pos.alpha_purchased and pos.alpha_purchased > 0:
                    result["positions_with_alpha_purchased"] += 1
                else:
                    result["missing_alpha_purchased"].append(pos.netuid)

            # Generate warnings
            warnings = []
            if result["missing_cost_basis"]:
                warnings.append(
                    f"Missing cost basis for netuids: {result['missing_cost_basis']}"
                )
            if result["missing_alpha_purchased"]:
                warnings.append(
                    f"Missing alpha_purchased for netuids: {result['missing_alpha_purchased']}"
                )

            if warnings:
                result["has_warning"] = True
                result["warning"] = "; ".join(warnings)

        except Exception as e:
            logger.error("Cost basis validation failed", error=str(e))
            result["has_warning"] = True
            result["warning"] = f"Cost basis validation error: {str(e)}"

        return result

    async def get_validation_summary(self) -> Dict[str, Any]:
        """Get a summary suitable for display in the UI.

        Returns simplified validation status for frontend display.
        """
        full_result = await self.validate_all()

        return {
            "is_valid": full_result["is_valid"],
            "has_warning": not full_result["is_valid"],
            "warning_count": len(full_result["warnings"]),
            "warning": full_result["warnings"][0] if full_result["warnings"] else None,
            "validated_at": full_result["validated_at"],
        }


# Lazy singleton instance
_validator: Optional[AccountingValidatorService] = None


def get_accounting_validator() -> AccountingValidatorService:
    """Get or create the accounting validator service singleton."""
    global _validator
    if _validator is None:
        _validator = AccountingValidatorService()
    return _validator
