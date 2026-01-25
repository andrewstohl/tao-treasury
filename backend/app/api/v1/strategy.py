"""Strategy engine endpoints.

Provides access to the Phase 3 strategy engine:
- Portfolio analysis and state
- Constraint checking
- Rebalance recommendation generation
- Position sizing
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.strategy import (
    strategy_engine,
    rebalancer,
    constraint_enforcer,
    eligibility_gate,
    position_sizer,
    FlowRegime,
    TriggerType,
)

router = APIRouter()


# Response schemas

class ConstraintCheckResponse(BaseModel):
    """Single constraint check result."""
    name: str
    passed: bool
    current_value: str
    limit_value: str
    explanation: str


class ConstraintStatusResponse(BaseModel):
    """Full constraint status response."""
    checked_at: datetime
    all_constraints_ok: bool
    total_checked: int
    violation_count: int
    warning_count: int
    summary: str
    violations: List[dict]
    warnings: List[dict]


class EligibilityResponse(BaseModel):
    """Eligible subnet response."""
    netuid: int
    name: str
    is_eligible: bool
    reasons: List[str]
    score: Optional[int] = None


class PositionLimitResponse(BaseModel):
    """Position limit response."""
    netuid: int
    subnet_name: str
    exitability_cap_tao: float
    concentration_cap_tao: float
    category_cap_tao: float
    max_position_tao: float
    binding_constraint: str
    current_position_tao: float
    available_headroom_tao: float
    explanation: str


class StrategyAnalysisResponse(BaseModel):
    """Full strategy analysis response."""
    analyzed_at: datetime
    data_as_of: Optional[datetime]
    portfolio_state: str
    state_reason: str
    regime_summary: dict
    portfolio_regime: str
    total_subnets: int
    eligible_subnets: int
    positions_analyzed: int
    overweight_count: int
    underweight_count: int
    positions_to_exit: int
    concentration_ok: bool
    category_caps_ok: bool
    turnover_budget_remaining_pct: float
    pending_recommendations: int
    urgent_recommendations: int
    explanation: str


class RebalanceResponse(BaseModel):
    """Rebalance generation response."""
    recommendation_count: int
    total_buys_tao: float
    total_sells_tao: float
    turnover_pct: float
    constrained_by_turnover: bool
    summary: str


class TradeCheckResponse(BaseModel):
    """Trade allowance check response."""
    allowed: bool
    explanation: str
    available_capacity: Optional[dict] = None


# Endpoints

@router.get("/analysis", response_model=StrategyAnalysisResponse)
async def get_strategy_analysis(
    db: AsyncSession = Depends(get_db),
) -> StrategyAnalysisResponse:
    """Run full strategy analysis on current portfolio.

    Returns comprehensive analysis including:
    - Portfolio state (healthy/caution/risk_off/emergency)
    - Regime distribution across positions
    - Position weight analysis
    - Constraint status
    - Recommendation counts
    """
    analysis = await strategy_engine.run_full_analysis()

    return StrategyAnalysisResponse(
        analyzed_at=analysis.analyzed_at,
        data_as_of=analysis.data_as_of,
        portfolio_state=analysis.portfolio_state.value,
        state_reason=analysis.state_reason,
        regime_summary=analysis.regime_summary,
        portfolio_regime=analysis.portfolio_regime,
        total_subnets=analysis.total_subnets,
        eligible_subnets=analysis.eligible_subnets,
        positions_analyzed=analysis.positions_analyzed,
        overweight_count=len(analysis.overweight_positions),
        underweight_count=len(analysis.underweight_positions),
        positions_to_exit=len(analysis.positions_to_exit),
        concentration_ok=analysis.concentration_ok,
        category_caps_ok=analysis.category_caps_ok,
        turnover_budget_remaining_pct=float(analysis.turnover_budget_remaining_pct),
        pending_recommendations=analysis.pending_recommendations,
        urgent_recommendations=analysis.urgent_recommendations,
        explanation=analysis.explanation,
    )


@router.get("/constraints", response_model=ConstraintStatusResponse)
async def check_constraints(
    db: AsyncSession = Depends(get_db),
) -> ConstraintStatusResponse:
    """Check all portfolio constraints.

    Returns detailed status of:
    - Position concentration limits
    - Category concentration limits
    - Drawdown limits
    - Turnover limits
    - Slippage exposure
    """
    status = await constraint_enforcer.check_all_constraints()

    return ConstraintStatusResponse(
        checked_at=status.checked_at,
        all_constraints_ok=status.all_constraints_ok,
        total_checked=status.total_checked,
        violation_count=len(status.violations),
        warning_count=len(status.warnings),
        summary=status.summary,
        violations=[
            {
                "constraint": v.constraint_name,
                "severity": v.severity.value,
                "current": str(v.current_value),
                "limit": str(v.limit_value),
                "utilization_pct": float(v.utilization_pct),
                "explanation": v.explanation,
                "action_required": v.action_required,
                "netuid": v.netuid,
                "category": v.category,
            }
            for v in status.violations
        ],
        warnings=[
            {
                "constraint": w.constraint_name,
                "severity": w.severity.value,
                "current": str(w.current_value),
                "limit": str(w.limit_value),
                "utilization_pct": float(w.utilization_pct),
                "explanation": w.explanation,
                "action_required": w.action_required,
                "netuid": w.netuid,
                "category": w.category,
            }
            for w in status.warnings
        ],
    )


@router.get("/eligible", response_model=List[EligibilityResponse])
async def get_eligible_universe(
    db: AsyncSession = Depends(get_db),
) -> List[EligibilityResponse]:
    """Get current eligible investment universe.

    Returns all subnets that pass eligibility checks,
    sorted by attractiveness score.
    """
    eligible = await eligibility_gate.get_eligible_universe()

    return [
        EligibilityResponse(
            netuid=e.netuid,
            name=e.name,
            is_eligible=e.is_eligible,
            reasons=e.reasons,
            score=e.score,
        )
        for e in eligible
    ]


@router.get("/position-limits", response_model=List[PositionLimitResponse])
async def get_position_limits(
    db: AsyncSession = Depends(get_db),
) -> List[PositionLimitResponse]:
    """Get position limits for all eligible subnets.

    Returns the three-tier cap analysis:
    - Exitability cap (based on slippage)
    - Concentration cap (15% of portfolio)
    - Category cap (30% of sleeve)
    """
    limits = await strategy_engine.get_position_limits()

    return [
        PositionLimitResponse(
            netuid=l.netuid,
            subnet_name=l.subnet_name,
            exitability_cap_tao=float(l.exitability_cap_tao),
            concentration_cap_tao=float(l.concentration_cap_tao),
            category_cap_tao=float(l.category_cap_tao),
            max_position_tao=float(l.max_position_tao),
            binding_constraint=l.binding_constraint,
            current_position_tao=float(l.current_position_tao),
            available_headroom_tao=float(l.available_headroom_tao),
            explanation=l.explanation,
        )
        for l in limits
    ]


@router.post("/rebalance/weekly", response_model=RebalanceResponse)
async def trigger_weekly_rebalance(
    db: AsyncSession = Depends(get_db),
) -> RebalanceResponse:
    """Trigger weekly rebalance recommendation generation.

    Generates recommendations for:
    - Exiting ineligible positions
    - Trimming overweight positions
    - Entering new attractive positions

    All recommendations are advisory only.
    """
    result = await strategy_engine.trigger_weekly_rebalance()

    return RebalanceResponse(
        recommendation_count=len(result.recommendations),
        total_buys_tao=float(result.total_buys_tao),
        total_sells_tao=float(result.total_sells_tao),
        turnover_pct=float(result.turnover_pct),
        constrained_by_turnover=result.constrained_by_turnover,
        summary=result.summary,
    )


@router.post("/rebalance/event", response_model=RebalanceResponse)
async def trigger_event_rebalance(
    event_type: str = Query(
        ...,
        description="Event type: quarantine, dead, risk_reduction, concentration, regime_shift"
    ),
    netuids: Optional[str] = Query(
        None,
        description="Comma-separated list of affected netuids"
    ),
    db: AsyncSession = Depends(get_db),
) -> RebalanceResponse:
    """Trigger event-driven rebalance recommendation generation.

    Called when significant events occur:
    - quarantine: Trim quarantined positions by 50%
    - dead: Full exit from dead subnet positions
    - risk_reduction: Portfolio-wide 25% reduction
    - concentration: Trim specific over-concentrated positions
    - regime_shift: React to regime changes
    """
    valid_events = ["quarantine", "dead", "risk_reduction", "concentration", "regime_shift"]
    if event_type not in valid_events:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type. Must be one of: {', '.join(valid_events)}"
        )

    affected_netuids = None
    if netuids:
        try:
            affected_netuids = [int(n.strip()) for n in netuids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid netuid format")

    result = await strategy_engine.trigger_event_rebalance(event_type, affected_netuids)

    return RebalanceResponse(
        recommendation_count=len(result.recommendations),
        total_buys_tao=float(result.total_buys_tao),
        total_sells_tao=float(result.total_sells_tao),
        turnover_pct=float(result.turnover_pct),
        constrained_by_turnover=result.constrained_by_turnover,
        summary=result.summary,
    )


@router.get("/check-trade", response_model=TradeCheckResponse)
async def check_trade_allowed(
    netuid: int = Query(..., description="Target subnet netuid"),
    direction: str = Query(..., regex="^(buy|sell)$", description="Trade direction"),
    size_tao: float = Query(..., gt=0, description="Trade size in TAO"),
    db: AsyncSession = Depends(get_db),
) -> TradeCheckResponse:
    """Check if a proposed trade is allowed by constraints.

    Returns whether the trade is allowed and detailed explanation.
    Also returns available capacity if trade is blocked.
    """
    allowed, explanation = await constraint_enforcer.check_trade_allowed(
        netuid=netuid,
        direction=direction,
        size_tao=Decimal(str(size_tao)),
    )

    capacity = None
    if not allowed:
        capacity = await constraint_enforcer.get_available_capacity(netuid)
        capacity = {k: float(v) for k, v in capacity.items()}

    return TradeCheckResponse(
        allowed=allowed,
        explanation=explanation,
        available_capacity=capacity,
    )


@router.get("/recommendation-summary")
async def get_recommendation_summary(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get summary of pending recommendations.

    Returns counts, totals, and top recommendations.
    """
    return await strategy_engine.get_recommendation_summary()
