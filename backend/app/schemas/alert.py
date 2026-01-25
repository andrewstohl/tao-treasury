"""Alert schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    """Alert response with full details."""
    id: int
    severity: str
    category: str
    title: str
    message: str

    wallet_address: Optional[str] = None
    netuid: Optional[int] = None

    metrics_snapshot: Optional[Dict[str, Any]] = None
    threshold_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None

    is_active: bool = True
    is_acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None

    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    """Alert list response."""
    alerts: List[AlertResponse]
    total: int
    active_count: int
    by_severity: Dict[str, int]


class AlertAcknowledge(BaseModel):
    """Request to acknowledge an alert."""
    action: str = "acknowledged"  # acknowledged, dismissed, resolved
    notes: Optional[str] = None
    acknowledged_by: str = "user"
