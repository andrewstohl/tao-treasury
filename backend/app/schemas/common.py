"""Common schemas used across the API."""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=200)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    data: List[T]
    total: int
    page: int
    limit: int
    total_pages: int


class SchedulerLastSync(BaseModel):
    """Last sync result from scheduler."""
    success: Optional[bool] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None
    consecutive_failures: int = 0
    rate_limited: bool = False


class SchedulerStatus(BaseModel):
    """Scheduler status for health check."""
    running: bool
    next_sync: Optional[str] = None
    job_count: int = 0
    last_sync: Optional[SchedulerLastSync] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str
    database: str
    redis: str
    taostats_api: str
    last_sync: Optional[datetime] = None
    data_stale: bool = False
    scheduler: Optional[SchedulerStatus] = None


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SyncResponse(BaseModel):
    """Data sync response."""
    success: bool
    timestamp: datetime
    mode: str = "full"
    subnets: int = 0
    pools: int = 0
    positions: int = 0
    validators: int = 0
    # Phase 2: Analysis results
    transactions: int = 0
    slippage_surfaces: int = 0
    cost_basis_computed: bool = False
    nav_computed: bool = False
    nav_executable_tao: Optional[float] = None
    risk_check: bool = False
    risk_score: Optional[int] = None
    alerts: int = 0
    errors: List[str] = []
