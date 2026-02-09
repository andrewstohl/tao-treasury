"""Risk Monitor service for drawdown tracking and alerts.

Per spec: Enforce max 15% drawdown in executable TAO NAV.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_context
from app.models.portfolio import NAVHistory
from app.models.alert import Alert
from app.models.position import Position

logger = structlog.get_logger()

# Risk thresholds
MAX_DRAWDOWN_PCT = Decimal("15.0")  # 15% max drawdown
WARNING_DRAWDOWN_PCT = Decimal("10.0")  # 10% warning threshold
CRITICAL_DRAWDOWN_PCT = Decimal("12.5")  # 12.5% critical threshold

# Position concentration limits
MAX_POSITION_PCT = Decimal("25.0")  # No single position > 25%
WARNING_POSITION_PCT = Decimal("20.0")  # Warn at 20%


def _sanitize_for_json(data):
    """Convert Decimal values to float for JSONB storage."""
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [_sanitize_for_json(item) for item in data]
    elif isinstance(data, Decimal):
        return float(data)
    return data


class RiskMonitor:
    """Monitors portfolio risk metrics and generates alerts."""

    def __init__(self):
        settings = get_settings()
        self.wallet_address = settings.wallet_address

    async def compute_drawdown(self) -> Dict[str, Any]:
        """Compute current drawdown from peak NAV.

        Returns:
            Dict with drawdown metrics
        """
        async with get_db_context() as db:
            # Get peak NAV (highest ATH ever recorded)
            stmt = select(func.max(NAVHistory.nav_exec_ath)).where(
                NAVHistory.wallet_address == self.wallet_address
            )
            result = await db.execute(stmt)
            peak_nav = result.scalar() or Decimal("0")

            # Get current NAV (most recent close)
            stmt = (
                select(NAVHistory)
                .where(NAVHistory.wallet_address == self.wallet_address)
                .order_by(NAVHistory.date.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            latest = result.scalar_one_or_none()

            current_nav = latest.nav_exec_close if latest else Decimal("0")

            # Compute drawdown
            if peak_nav > 0:
                drawdown_tao = peak_nav - current_nav
                drawdown_pct = (drawdown_tao / peak_nav) * 100
            else:
                drawdown_tao = Decimal("0")
                drawdown_pct = Decimal("0")

            # Determine severity
            if drawdown_pct >= MAX_DRAWDOWN_PCT:
                severity = "critical"
            elif drawdown_pct >= CRITICAL_DRAWDOWN_PCT:
                severity = "high"
            elif drawdown_pct >= WARNING_DRAWDOWN_PCT:
                severity = "medium"
            else:
                severity = "low"

            return {
                "peak_nav_tao": peak_nav,
                "current_nav_tao": current_nav,
                "drawdown_tao": drawdown_tao,
                "drawdown_pct": drawdown_pct,
                "severity": severity,
                "max_allowed_pct": MAX_DRAWDOWN_PCT,
                "threshold_breach": drawdown_pct >= MAX_DRAWDOWN_PCT,
            }

    async def compute_concentration_risk(self) -> Dict[str, Any]:
        """Compute position concentration metrics.

        Returns:
            Dict with concentration analysis
        """
        async with get_db_context() as db:
            # Get all positions
            stmt = select(Position).where(
                Position.wallet_address == self.wallet_address,
                Position.tao_value_mid > 0,
            )
            result = await db.execute(stmt)
            positions = list(result.scalars().all())

            if not positions:
                return {
                    "total_nav_tao": Decimal("0"),
                    "position_count": 0,
                    "largest_position_pct": Decimal("0"),
                    "hhi": Decimal("0"),  # Herfindahl-Hirschman Index
                    "warnings": [],
                }

            # Compute total NAV
            total_nav = sum(p.tao_value_mid or Decimal("0") for p in positions)

            # Compute weights and metrics
            position_weights = []
            warnings = []

            for p in positions:
                weight = (p.tao_value_mid / total_nav * 100) if total_nav > 0 else Decimal("0")
                position_weights.append({
                    "netuid": p.netuid,
                    "subnet_name": p.subnet_name,
                    "tao_value": p.tao_value_mid,
                    "weight_pct": weight,
                })

                if weight >= MAX_POSITION_PCT:
                    warnings.append({
                        "type": "concentration_critical",
                        "netuid": p.netuid,
                        "subnet_name": p.subnet_name,
                        "weight_pct": weight,
                        "max_allowed_pct": MAX_POSITION_PCT,
                    })
                elif weight >= WARNING_POSITION_PCT:
                    warnings.append({
                        "type": "concentration_warning",
                        "netuid": p.netuid,
                        "subnet_name": p.subnet_name,
                        "weight_pct": weight,
                        "threshold_pct": WARNING_POSITION_PCT,
                    })

            # Sort by weight descending
            position_weights.sort(key=lambda x: x["weight_pct"], reverse=True)

            # Compute HHI (sum of squared weights, normalized to 0-10000)
            hhi = sum((w["weight_pct"] ** 2) for w in position_weights)

            return {
                "total_nav_tao": total_nav,
                "position_count": len(positions),
                "largest_position_pct": position_weights[0]["weight_pct"] if position_weights else Decimal("0"),
                "hhi": hhi,
                "position_weights": position_weights[:10],  # Top 10
                "warnings": warnings,
            }

    async def run_risk_check(self) -> Dict[str, Any]:
        """Run full risk analysis and generate alerts.

        Returns:
            Complete risk assessment
        """
        logger.info("Running risk check")

        # Compute metrics
        drawdown = await self.compute_drawdown()
        concentration = await self.compute_concentration_risk()

        # Generate alerts
        alerts = []

        # Drawdown alerts
        if drawdown["threshold_breach"]:
            alerts.append(await self._create_alert(
                alert_type="drawdown_breach",
                severity="critical",
                title=f"Max Drawdown Exceeded: {drawdown['drawdown_pct']:.1f}%",
                message=f"Portfolio drawdown of {drawdown['drawdown_pct']:.1f}% exceeds the {MAX_DRAWDOWN_PCT}% limit. "
                        f"Current NAV: {drawdown['current_nav_tao']:.2f} TAO, Peak: {drawdown['peak_nav_tao']:.2f} TAO",
                data=drawdown,
            ))
        elif drawdown["severity"] in ("high", "critical"):
            alerts.append(await self._create_alert(
                alert_type="drawdown_warning",
                severity="high",
                title=f"Drawdown Warning: {drawdown['drawdown_pct']:.1f}%",
                message=f"Portfolio drawdown approaching limit. Current: {drawdown['drawdown_pct']:.1f}%, Max: {MAX_DRAWDOWN_PCT}%",
                data=drawdown,
            ))
        elif drawdown["severity"] == "medium":
            alerts.append(await self._create_alert(
                alert_type="drawdown_info",
                severity="medium",
                title=f"Drawdown Notice: {drawdown['drawdown_pct']:.1f}%",
                message=f"Portfolio drawdown at {drawdown['drawdown_pct']:.1f}%. Monitoring.",
                data=drawdown,
            ))

        # Concentration alerts
        for warning in concentration.get("warnings", []):
            if warning["type"] == "concentration_critical":
                alerts.append(await self._create_alert(
                    alert_type="concentration_breach",
                    severity="high",
                    title=f"Position Concentration: SN{warning['netuid']}",
                    message=f"{warning['subnet_name']} at {warning['weight_pct']:.1f}% exceeds {warning['max_allowed_pct']}% limit",
                    data=warning,
                ))
            else:
                alerts.append(await self._create_alert(
                    alert_type="concentration_warning",
                    severity="medium",
                    title=f"Concentration Warning: SN{warning['netuid']}",
                    message=f"{warning['subnet_name']} at {warning['weight_pct']:.1f}% approaching limit",
                    data=warning,
                ))

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "drawdown": drawdown,
            "concentration": concentration,
            "alerts": alerts,
            "risk_score": self._compute_risk_score(drawdown, concentration),
        }

        logger.info(
            "Risk check completed",
            drawdown_pct=drawdown["drawdown_pct"],
            alert_count=len(alerts),
        )

        return result

    def _compute_risk_score(
        self,
        drawdown: Dict[str, Any],
        concentration: Dict[str, Any]
    ) -> int:
        """Compute overall risk score (0-100, higher = more risk).

        Args:
            drawdown: Drawdown metrics
            concentration: Concentration metrics

        Returns:
            Risk score 0-100
        """
        score = 0

        # Drawdown component (0-50 points)
        dd_pct = float(drawdown["drawdown_pct"])
        if dd_pct >= 15:
            score += 50
        elif dd_pct >= 10:
            score += 35
        elif dd_pct >= 5:
            score += 20
        else:
            score += int(dd_pct * 4)

        # Concentration component (0-30 points)
        largest = float(concentration["largest_position_pct"])
        if largest >= 25:
            score += 30
        elif largest >= 20:
            score += 20
        elif largest >= 15:
            score += 10
        else:
            score += int(largest * 0.5)

        # HHI component (0-20 points) - higher HHI = less diversified
        hhi = float(concentration["hhi"])
        if hhi >= 3000:  # Very concentrated
            score += 20
        elif hhi >= 2000:
            score += 15
        elif hhi >= 1500:
            score += 10
        else:
            score += int(hhi / 200)

        return min(100, score)

    async def _create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create and optionally persist an alert.

        Args:
            alert_type: Category of alert (maps to Alert.category)
            severity: critical, warning, info
            title: Alert title
            message: Alert message
            data: Optional metrics snapshot

        Returns:
            Alert dict
        """
        now = datetime.now(timezone.utc)

        alert_dict = {
            "type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "timestamp": now.isoformat(),
            "data": data,
        }

        # Check if similar alert exists recently (avoid spam)
        async with get_db_context() as db:
            recent_cutoff = now - timedelta(hours=1)
            stmt = select(Alert).where(
                Alert.wallet_address == self.wallet_address,
                Alert.category == alert_type,
                Alert.created_at >= recent_cutoff,
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if not existing:
                # Create new alert
                alert = Alert(
                    wallet_address=self.wallet_address,
                    category=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    metrics_snapshot=_sanitize_for_json(data) if data else None,
                )
                db.add(alert)
                await db.commit()

                alert_dict["id"] = alert.id
                logger.info("Created alert", category=alert_type, severity=severity)
            else:
                alert_dict["id"] = existing.id
                alert_dict["note"] = "Similar alert exists"

        return alert_dict

    async def get_recent_alerts(
        self,
        limit: int = 20,
        include_acknowledged: bool = False
    ) -> List[Dict[str, Any]]:
        """Get recent alerts.

        Args:
            limit: Max alerts to return
            include_acknowledged: Include acknowledged alerts

        Returns:
            List of alerts
        """
        async with get_db_context() as db:
            stmt = select(Alert).where(
                Alert.wallet_address == self.wallet_address
            )

            if not include_acknowledged:
                stmt = stmt.where(Alert.is_acknowledged == False)

            stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)

            result = await db.execute(stmt)
            alerts = result.scalars().all()

            return [
                {
                    "id": a.id,
                    "category": a.category,
                    "severity": a.severity,
                    "title": a.title,
                    "message": a.message,
                    "timestamp": a.created_at.isoformat() if a.created_at else None,
                    "acknowledged": a.is_acknowledged,
                }
                for a in alerts
            ]

    async def acknowledge_alert(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged.

        Args:
            alert_id: Alert ID

        Returns:
            True if acknowledged
        """
        async with get_db_context() as db:
            stmt = select(Alert).where(
                Alert.id == alert_id,
                Alert.wallet_address == self.wallet_address,
            )
            result = await db.execute(stmt)
            alert = result.scalar_one_or_none()

            if alert:
                alert.is_acknowledged = True
                alert.acknowledged_at = datetime.now(timezone.utc)
                await db.commit()
                return True

            return False


# Lazy singleton instance
_risk_monitor: RiskMonitor | None = None


def get_risk_monitor() -> RiskMonitor:
    """Get or create the risk monitor singleton."""
    global _risk_monitor
    if _risk_monitor is None:
        _risk_monitor = RiskMonitor()
    return _risk_monitor


class _LazyRiskMonitor:
    """Lazy proxy for backwards compatibility."""

    def __getattr__(self, name):
        return getattr(get_risk_monitor(), name)


risk_monitor = _LazyRiskMonitor()
