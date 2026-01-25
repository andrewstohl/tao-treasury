"""Alerts endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert, AlertAcknowledgement
from app.schemas.alert import AlertResponse, AlertListResponse, AlertAcknowledge

router = APIRouter()


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(default=True),
    severity: Optional[str] = Query(default=None, regex="^(critical|warning|info)$"),
) -> AlertListResponse:
    """List alerts."""
    stmt = select(Alert)

    if active_only:
        stmt = stmt.where(Alert.is_active == True)

    if severity:
        stmt = stmt.where(Alert.severity == severity)

    stmt = stmt.order_by(
        Alert.severity.desc(),  # critical first
        Alert.created_at.desc(),
    )

    result = await db.execute(stmt)
    alerts = result.scalars().all()

    # Count by severity
    by_severity = {}
    active_count = 0
    for a in alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
        if a.is_active:
            active_count += 1

    responses = [
        AlertResponse(
            id=a.id,
            severity=a.severity,
            category=a.category,
            title=a.title,
            message=a.message,
            wallet_address=a.wallet_address,
            netuid=a.netuid,
            metrics_snapshot=a.metrics_snapshot,
            threshold_value=a.threshold_value,
            actual_value=a.actual_value,
            is_active=a.is_active,
            is_acknowledged=a.is_acknowledged,
            acknowledged_at=a.acknowledged_at,
            acknowledged_by=a.acknowledged_by,
            resolved_at=a.resolved_at,
            resolution_notes=a.resolution_notes,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in alerts
    ]

    return AlertListResponse(
        alerts=responses,
        total=len(responses),
        active_count=active_count,
        by_severity=by_severity,
    )


@router.post("/{alert_id}/ack", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    ack: AlertAcknowledge,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """Acknowledge an alert."""
    stmt = select(Alert).where(Alert.id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    now = datetime.now(timezone.utc)

    # Update alert
    alert.is_acknowledged = True
    alert.acknowledged_at = now
    alert.acknowledged_by = ack.acknowledged_by

    if ack.action == "resolved":
        alert.is_active = False
        alert.resolved_at = now
        alert.resolution_notes = ack.notes

    # Create acknowledgement record
    ack_record = AlertAcknowledgement(
        alert_id=alert_id,
        action=ack.action,
        notes=ack.notes,
        acknowledged_by=ack.acknowledged_by,
        acknowledged_at=now,
    )
    db.add(ack_record)

    await db.commit()
    await db.refresh(alert)

    return AlertResponse(
        id=alert.id,
        severity=alert.severity,
        category=alert.category,
        title=alert.title,
        message=alert.message,
        wallet_address=alert.wallet_address,
        netuid=alert.netuid,
        metrics_snapshot=alert.metrics_snapshot,
        threshold_value=alert.threshold_value,
        actual_value=alert.actual_value,
        is_active=alert.is_active,
        is_acknowledged=alert.is_acknowledged,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        resolved_at=alert.resolved_at,
        resolution_notes=alert.resolution_notes,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )
