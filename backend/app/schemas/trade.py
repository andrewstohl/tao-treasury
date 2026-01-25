"""Trade recommendation schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class TradeRecommendationResponse(BaseModel):
    """Trade recommendation response."""
    id: int
    wallet_address: str
    netuid: int
    subnet_name: Optional[str] = None

    direction: str
    size_alpha: Decimal
    size_tao: Decimal
    size_pct_of_position: Decimal

    estimated_slippage_pct: Decimal
    estimated_slippage_tao: Decimal
    total_estimated_cost_tao: Decimal
    expected_nav_impact_tao: Decimal

    trigger_type: str
    reason: str

    priority: int
    is_urgent: bool

    tranche_number: Optional[int] = None
    total_tranches: Optional[int] = None

    status: str
    expires_at: Optional[datetime] = None

    created_at: datetime

    class Config:
        from_attributes = True


class RecommendationListResponse(BaseModel):
    """Recommendation list response."""
    recommendations: List[TradeRecommendationResponse]
    total: int
    pending_count: int
    total_estimated_cost_tao: Decimal


class MarkExecutedRequest(BaseModel):
    """Request to mark a recommendation as executed."""
    actual_slippage_pct: Optional[Decimal] = None
    notes: Optional[str] = None
