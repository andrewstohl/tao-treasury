"""Reconciliation service for Phase 2.

Compares stored position data vs live TaoStats API data to detect drift.
Records results for audit trail and integrates with Trust Pack.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.models.reconciliation import ReconciliationRun
from app.services.data.taostats_client import taostats_client

logger = structlog.get_logger()


class ReconciliationService:
    """Service for reconciling stored data vs live API data."""

    def __init__(self):
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def run_reconciliation(
        self,
        wallet_address: Optional[str] = None,
    ) -> ReconciliationRun:
        """Run a full reconciliation check.

        Compares stored positions vs live TaoStats stake balances.

        Args:
            wallet_address: Wallet to check (defaults to configured wallet)

        Returns:
            ReconciliationRun record with results
        """
        wallet = wallet_address or self.settings.wallet_address
        run_id = f"recon_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        logger.info("Starting reconciliation run", run_id=run_id, wallet=wallet)

        absolute_tolerance = self.settings.reconciliation_absolute_tolerance_tao
        relative_tolerance = self.settings.reconciliation_relative_tolerance_pct

        try:
            # Get stored positions
            async with get_db_context() as db:
                stored_positions = await self._get_stored_positions(db, wallet)

            # Get live data from TaoStats
            live_positions = await self._get_live_positions(wallet)

            # Run checks
            checks = []
            passed_checks = 0
            failed_checks = 0
            total_stored_value = Decimal("0")
            total_live_value = Decimal("0")

            # Collect all netuids from both sources
            all_netuids = set(stored_positions.keys()) | set(live_positions.keys())

            for netuid in sorted(all_netuids):
                stored = stored_positions.get(netuid, {})
                live = live_positions.get(netuid, {})

                check_result = self._compare_position(
                    netuid,
                    stored,
                    live,
                    absolute_tolerance,
                    relative_tolerance,
                )
                checks.append(check_result)

                if check_result["passed"]:
                    passed_checks += 1
                else:
                    failed_checks += 1

                total_stored_value += Decimal(str(stored.get("tao_value", 0)))
                total_live_value += Decimal(str(live.get("tao_value", 0)))

            # Compute total diff
            total_diff = total_live_value - total_stored_value
            total_diff_pct = Decimal("0")
            if total_stored_value > 0:
                total_diff_pct = (abs(total_diff) / total_stored_value) * Decimal("100")

            # Overall pass/fail
            overall_passed = failed_checks == 0

            # Create and store the run
            async with get_db_context() as db:
                run = ReconciliationRun(
                    run_id=run_id,
                    wallet_address=wallet,
                    netuids_checked=list(all_netuids),
                    passed=overall_passed,
                    total_checks=len(checks),
                    passed_checks=passed_checks,
                    failed_checks=failed_checks,
                    total_stored_value_tao=total_stored_value,
                    total_live_value_tao=total_live_value,
                    total_diff_tao=total_diff,
                    total_diff_pct=total_diff_pct,
                    checks=checks,
                    absolute_tolerance_tao=absolute_tolerance,
                    relative_tolerance_pct=relative_tolerance,
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)

            logger.info(
                "Reconciliation complete",
                run_id=run_id,
                passed=overall_passed,
                total_checks=len(checks),
                failed_checks=failed_checks,
            )

            # Update metrics if reconciliation failed
            if not overall_passed:
                await self._record_drift_detected(failed_checks)

            return run

        except Exception as e:
            logger.error("Reconciliation failed", run_id=run_id, error=str(e))

            # Store failed run
            async with get_db_context() as db:
                run = ReconciliationRun(
                    run_id=run_id,
                    wallet_address=wallet,
                    netuids_checked=[],
                    passed=False,
                    total_checks=0,
                    passed_checks=0,
                    failed_checks=0,
                    total_stored_value_tao=Decimal("0"),
                    total_live_value_tao=Decimal("0"),
                    total_diff_tao=Decimal("0"),
                    total_diff_pct=Decimal("0"),
                    checks=[],
                    error_message=str(e),
                    absolute_tolerance_tao=absolute_tolerance,
                    relative_tolerance_pct=relative_tolerance,
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)

            return run

    async def get_latest_run(
        self,
        wallet_address: Optional[str] = None,
    ) -> Optional[ReconciliationRun]:
        """Get the most recent reconciliation run.

        Args:
            wallet_address: Wallet to check (defaults to configured wallet)

        Returns:
            Most recent ReconciliationRun or None
        """
        wallet = wallet_address or self.settings.wallet_address

        async with get_db_context() as db:
            stmt = (
                select(ReconciliationRun)
                .where(ReconciliationRun.wallet_address == wallet)
                .order_by(desc(ReconciliationRun.created_at))
                .limit(1)
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def get_trust_pack_summary(self) -> Dict[str, Any]:
        """Get reconciliation summary for Trust Pack.

        Returns:
            Summary dict with latest run status
        """
        latest = await self.get_latest_run()

        if latest is None:
            return {
                "last_run_at": None,
                "last_run_passed": None,
                "failed_checks": 0,
                "has_drift": False,
            }

        return {
            "last_run_at": latest.created_at.isoformat() if latest.created_at else None,
            "last_run_passed": latest.passed,
            "failed_checks": latest.failed_checks,
            "total_diff_pct": str(latest.total_diff_pct),
            "has_drift": not latest.passed,
        }

    async def _get_stored_positions(
        self,
        db: AsyncSession,
        wallet: str,
    ) -> Dict[int, Dict[str, Any]]:
        """Get stored positions from database."""
        stmt = select(Position).where(Position.wallet_address == wallet)
        result = await db.execute(stmt)
        positions = result.scalars().all()

        return {
            p.netuid: {
                "alpha_balance": float(p.alpha_balance),
                "tao_value": float(p.tao_value_mid),
                "validator_hotkey": p.validator_hotkey,
            }
            for p in positions
        }

    async def _get_live_positions(
        self,
        wallet: str,
    ) -> Dict[int, Dict[str, Any]]:
        """Get live positions from TaoStats API."""
        response = await taostats_client.get_stake_balance(coldkey=wallet)
        stakes_data = response.get("data", [])

        # Deduplicate by netuid (keep first/most recent)
        positions = {}
        for stake in stakes_data:
            netuid = stake.get("netuid")
            if netuid is None or netuid in positions:
                continue

            # Convert from rao to TAO
            balance_rao = int(stake.get("balance", 0) or 0)
            balance_as_tao_rao = int(stake.get("balance_as_tao", 0) or 0)

            alpha_balance = balance_rao / 1e9
            tao_value = balance_as_tao_rao / 1e9

            # Extract hotkey
            hotkey_data = stake.get("hotkey")
            if isinstance(hotkey_data, dict):
                hotkey = hotkey_data.get("ss58")
            else:
                hotkey = hotkey_data

            positions[netuid] = {
                "alpha_balance": alpha_balance,
                "tao_value": tao_value,
                "validator_hotkey": hotkey,
            }

        return positions

    def _compare_position(
        self,
        netuid: int,
        stored: Dict[str, Any],
        live: Dict[str, Any],
        absolute_tolerance: Decimal,
        relative_tolerance: Decimal,
    ) -> Dict[str, Any]:
        """Compare stored vs live position data.

        Returns check result with pass/fail status.
        """
        stored_value = Decimal(str(stored.get("tao_value", 0)))
        live_value = Decimal(str(live.get("tao_value", 0)))

        stored_alpha = Decimal(str(stored.get("alpha_balance", 0)))
        live_alpha = Decimal(str(live.get("alpha_balance", 0)))

        # Calculate diffs
        value_diff = live_value - stored_value
        value_diff_abs = abs(value_diff)
        alpha_diff = live_alpha - stored_alpha

        # Calculate relative diff
        relative_diff_pct = Decimal("0")
        if stored_value > 0:
            relative_diff_pct = (value_diff_abs / stored_value) * Decimal("100")

        # Determine if within tolerance
        within_absolute = value_diff_abs <= absolute_tolerance
        within_relative = relative_diff_pct <= relative_tolerance

        # Pass if within either tolerance (for small values, use absolute; for large, use relative)
        passed = within_absolute or within_relative

        # Special case: if position exists in one but not other, always fail
        if (stored_value > 0 and live_value == 0) or (stored_value == 0 and live_value > 0):
            # Only fail if the value is significant
            if stored_value > absolute_tolerance or live_value > absolute_tolerance:
                passed = False

        return {
            "netuid": netuid,
            "passed": passed,
            "stored_value_tao": str(stored_value),
            "live_value_tao": str(live_value),
            "value_diff_tao": str(value_diff),
            "value_diff_pct": str(round(relative_diff_pct, 4)),
            "stored_alpha": str(stored_alpha),
            "live_alpha": str(live_alpha),
            "alpha_diff": str(alpha_diff),
            "within_absolute_tolerance": within_absolute,
            "within_relative_tolerance": within_relative,
            "stored_hotkey": stored.get("validator_hotkey"),
            "live_hotkey": live.get("validator_hotkey"),
        }

    async def _record_drift_detected(self, failed_checks: int) -> None:
        """Record drift detection in metrics."""
        try:
            from app.core.metrics import get_metrics
            metrics = get_metrics()
            await metrics.record_drift_detected(
                dataset_name="positions",
                drift_details=f"Reconciliation failed with {failed_checks} check(s)",
            )
        except Exception:
            pass  # Don't fail reconciliation due to metrics


# Lazy singleton
_reconciliation_service: Optional[ReconciliationService] = None


def get_reconciliation_service() -> ReconciliationService:
    """Get or create the ReconciliationService singleton."""
    global _reconciliation_service
    if _reconciliation_service is None:
        _reconciliation_service = ReconciliationService()
    return _reconciliation_service
