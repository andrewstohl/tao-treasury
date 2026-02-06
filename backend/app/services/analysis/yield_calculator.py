"""Yield calculator service using TaoStats method.

Computes actual yield earned using the TaoStats methodology:
  yield = balance_change - net_delegations

This matches TaoStats' "Earned TAO" calculation and provides the ground truth
for yield decomposition separate from alpha price appreciation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.position import Position
from app.services.data.taostats_client import get_taostats_client

logger = structlog.get_logger()


class YieldCalculatorService:
    """Service for computing actual yield using TaoStats balance history method.

    Key insight: TaoStats calculates yield as:
      yield = (balance_end - balance_start) - net_delegations

    Where:
      - balance_end/start: TAO value of position at end/start of period
      - net_delegations: sum of stakes minus sum of unstakes during period

    This gives the actual TAO earned from emissions/yield, separate from:
      - Alpha price appreciation (captured in alpha_purchased × price_change)
      - Realized P&L from trading
    """

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address

    async def compute_position_yield(
        self,
        netuid: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Compute actual yield for a position using TaoStats method.

        Args:
            netuid: Subnet ID
            days: Number of days to look back (default 30)

        Returns:
            Dict with yield breakdown:
                - total_yield_tao: Total yield earned (TAO)
                - unrealized_yield_tao: Currently held yield (not yet unstaked)
                - realized_yield_tao: Yield that was sold/unstaked
                - daily_breakdown: Per-day yield values
                - data_quality: Indicator of data completeness
        """
        client = get_taostats_client()

        # Time range for history
        now = datetime.now(timezone.utc)
        ts_end = int(now.timestamp())
        ts_start = int((now - timedelta(days=days)).timestamp())

        result = {
            "netuid": netuid,
            "total_yield_tao": Decimal("0"),
            "unrealized_yield_tao": Decimal("0"),
            "realized_yield_tao": Decimal("0"),
            "daily_breakdown": [],
            "data_quality": "complete",
            "period_days": days,
        }

        try:
            # Get current position for hotkey
            async with get_db_context() as db:
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.netuid == netuid,
                )
                pos_result = await db.execute(pos_stmt)
                position = pos_result.scalar_one_or_none()

            if not position or not position.validator_hotkey:
                result["data_quality"] = "no_position"
                return result

            hotkey = position.validator_hotkey

            # Fetch stake balance history (daily snapshots)
            history_response = await client.get_stake_balance_history(
                coldkey=self.wallet_address,
                hotkey=hotkey,
                netuid=netuid,
                timestamp_start=ts_start,
                timestamp_end=ts_end,
                limit=days + 5,  # Extra buffer
            )
            history_data = history_response.get("data", [])

            if not history_data:
                result["data_quality"] = "no_history"
                return result

            # Fetch delegation events for the period
            all_events = await client.get_all_delegation_events(
                coldkey=self.wallet_address,
            )

            # Filter to this subnet and time period
            delegation_events = [
                e for e in all_events
                if e.get("netuid") == netuid
                and self._parse_timestamp(e.get("timestamp")) >= (now - timedelta(days=days))
            ]

            # Sort history by timestamp ascending
            history_data.sort(key=lambda x: x.get("timestamp", 0))

            # Compute yield day by day
            total_yield = Decimal("0")
            daily_breakdown = []

            for i in range(1, len(history_data)):
                prev_snapshot = history_data[i - 1]
                curr_snapshot = history_data[i]

                prev_ts = self._parse_timestamp(prev_snapshot.get("timestamp"))
                curr_ts = self._parse_timestamp(curr_snapshot.get("timestamp"))

                if prev_ts is None or curr_ts is None:
                    continue

                # TAO value at start and end of day
                tao_start = self._to_decimal(prev_snapshot.get("balance_as_tao", 0))
                tao_end = self._to_decimal(curr_snapshot.get("balance_as_tao", 0))

                # Net delegations during this period
                net_delegation = self._compute_net_delegations(
                    delegation_events, prev_ts, curr_ts
                )

                # Yield = balance change - net delegation
                daily_yield = tao_end - tao_start - net_delegation

                total_yield += daily_yield
                daily_breakdown.append({
                    "date": curr_ts.strftime("%Y-%m-%d"),
                    "tao_start": float(tao_start),
                    "tao_end": float(tao_end),
                    "net_delegation": float(net_delegation),
                    "yield": float(daily_yield),
                })

            result["total_yield_tao"] = total_yield
            result["daily_breakdown"] = daily_breakdown

            # For unrealized yield, we attribute all positive yield to unrealized
            # since we're tracking positions that are still open
            # Realized yield is tracked separately in cost_basis.py from actual unstakes
            result["unrealized_yield_tao"] = max(Decimal("0"), total_yield)

            logger.debug(
                "Computed position yield",
                netuid=netuid,
                total_yield=float(total_yield),
                days_with_data=len(daily_breakdown),
            )

        except Exception as e:
            logger.error("Failed to compute position yield", netuid=netuid, error=str(e))
            result["data_quality"] = "error"
            result["error"] = str(e)

        return result

    async def compute_portfolio_yield(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Compute total portfolio yield across all positions.

        Args:
            days: Number of days to look back

        Returns:
            Dict with:
                - total_yield_tao: Sum of yield across all positions
                - unrealized_yield_tao: Total unrealized yield
                - realized_yield_tao: Total realized yield
                - by_position: Per-position breakdown
                - data_quality: Overall data quality indicator
        """
        result = {
            "total_yield_tao": Decimal("0"),
            "unrealized_yield_tao": Decimal("0"),
            "realized_yield_tao": Decimal("0"),
            "by_position": {},
            "data_quality": "complete",
            "positions_with_data": 0,
            "positions_without_data": 0,
        }

        try:
            # Get all open positions
            async with get_db_context() as db:
                pos_stmt = select(Position).where(
                    Position.wallet_address == self.wallet_address,
                    Position.alpha_balance > 0,
                )
                pos_result = await db.execute(pos_stmt)
                positions = list(pos_result.scalars().all())

            for position in positions:
                netuid = position.netuid

                pos_yield = await self.compute_position_yield(
                    netuid=netuid,
                    days=days,
                )

                result["by_position"][netuid] = {
                    "total_yield_tao": float(pos_yield["total_yield_tao"]),
                    "unrealized_yield_tao": float(pos_yield["unrealized_yield_tao"]),
                    "data_quality": pos_yield["data_quality"],
                }

                if pos_yield["data_quality"] == "complete":
                    result["positions_with_data"] += 1
                    result["total_yield_tao"] += pos_yield["total_yield_tao"]
                    result["unrealized_yield_tao"] += pos_yield["unrealized_yield_tao"]
                else:
                    result["positions_without_data"] += 1

            # Determine overall data quality
            total_positions = result["positions_with_data"] + result["positions_without_data"]
            if result["positions_without_data"] > 0:
                if result["positions_with_data"] == 0:
                    result["data_quality"] = "no_data"
                else:
                    result["data_quality"] = "partial"

            logger.info(
                "Computed portfolio yield",
                total_yield=float(result["total_yield_tao"]),
                positions_with_data=result["positions_with_data"],
                positions_without_data=result["positions_without_data"],
            )

        except Exception as e:
            logger.error("Failed to compute portfolio yield", error=str(e))
            result["data_quality"] = "error"
            result["error"] = str(e)

        return result

    def _compute_net_delegations(
        self,
        events: List[Dict],
        start_time: datetime,
        end_time: datetime,
    ) -> Decimal:
        """Compute net delegation amount (stakes - unstakes) in a time period.

        Args:
            events: List of delegation events
            start_time: Period start (exclusive)
            end_time: Period end (inclusive)

        Returns:
            Net delegation in TAO (positive = net stake, negative = net unstake)
        """
        net = Decimal("0")

        for event in events:
            event_time = self._parse_timestamp(event.get("timestamp"))
            if event_time is None:
                continue

            # Event must be in (start_time, end_time]
            if event_time <= start_time or event_time > end_time:
                continue

            action = event.get("action", "").lower()
            # Amount is in rao, convert to TAO
            amount_rao = self._to_decimal(event.get("amount", 0))
            amount_tao = amount_rao / Decimal("1000000000")

            if "add_stake" in action or action == "stake":
                net += amount_tao
            elif "remove_stake" in action or "unstake" in action:
                net -= amount_tao

        return net

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if ts is None:
            return None

        if isinstance(ts, datetime):
            return ts

        if isinstance(ts, (int, float)):
            # Unix timestamp
            return datetime.fromtimestamp(ts, tz=timezone.utc)

        if isinstance(ts, str):
            try:
                # ISO format
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass

        return None

    def _to_decimal(self, value: Any) -> Decimal:
        """Convert value to Decimal safely."""
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")


# Lazy singleton instance
_yield_calculator: Optional[YieldCalculatorService] = None


def get_yield_calculator() -> YieldCalculatorService:
    """Get or create the yield calculator service singleton."""
    global _yield_calculator
    if _yield_calculator is None:
        _yield_calculator = YieldCalculatorService()
    return _yield_calculator
