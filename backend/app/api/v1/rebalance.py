"""Rebalance Advisor API endpoints.

Computes target portfolios and required trades based on viability scoring.
Uses frontend-provided configuration (from localStorage) rather than backend settings.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.position import Position
from app.models.subnet import Subnet

logger = structlog.get_logger()
router = APIRouter()


# ==================== Request/Response Schemas ====================

class ViabilityConfigRequest(BaseModel):
    """Viability filtering and scoring configuration (from frontend settings)."""
    # Hard failure thresholds
    min_age_days: int = Field(default=60, ge=0, le=365)
    min_reserve_tao: float = Field(default=500.0, ge=0, le=10000)
    max_outflow_7d_pct: float = Field(default=50.0, ge=0, le=100)
    max_drawdown_pct: float = Field(default=50.0, ge=0, le=100)
    # Viability scoring weights (should sum to 1.0)
    fai_weight: float = Field(default=0.35, ge=0, le=1)
    reserve_weight: float = Field(default=0.25, ge=0, le=1)
    emission_weight: float = Field(default=0.25, ge=0, le=1)
    stability_weight: float = Field(default=0.15, ge=0, le=1)


class RebalanceConfigRequest(BaseModel):
    """Full rebalance configuration (from frontend localStorage)."""
    # Strategy
    strategy: str = Field(default="equal_weight", description="'equal_weight' or 'fai_weighted'")
    top_percentile: float = Field(default=50.0, ge=10, le=100, description="Select top N% of viable subnets")
    max_position_pct: float = Field(default=12.5, ge=1, le=50, description="Maximum weight per position")
    # Thresholds
    position_threshold_pct: float = Field(default=3.0, ge=0, le=20, description="Skip trades if position delta < this %")
    portfolio_threshold_pct: float = Field(default=5.0, ge=0, le=30, description="Skip rebalance if total drift < this %")
    # Viability config (can use backend or override)
    use_backend_viability_config: bool = Field(default=True)
    viability_config: Optional[ViabilityConfigRequest] = None


class PositionSnapshot(BaseModel):
    """Current or target position snapshot."""
    netuid: int
    name: str
    tao_value: float
    weight_pct: float
    viability_score: Optional[float] = None
    is_viable: bool = True
    failure_reasons: List[str] = []


class TradeRecommendation(BaseModel):
    """Recommended trade to rebalance."""
    netuid: int
    name: str
    action: str  # "buy", "sell", "exit"
    tao_amount: float
    current_weight_pct: float
    target_weight_pct: float
    delta_pct: float
    reason: str
    priority: int  # 1=highest (exits first), 2=sells, 3=buys


class RebalanceSummary(BaseModel):
    """Summary statistics for the rebalance."""
    current_portfolio_value: float
    total_drift_pct: float
    needs_rebalance: bool
    trades_count: int
    total_buy_tao: float
    total_sell_tao: float
    net_turnover_pct: float


class ComputeTargetResponse(BaseModel):
    """Response for compute-target endpoint."""
    computed_at: datetime
    summary: RebalanceSummary
    current_portfolio: List[PositionSnapshot]
    target_portfolio: List[PositionSnapshot]
    trades: List[TradeRecommendation]
    viable_subnets_count: int
    filtered_out_count: int
    config_used: Dict[str, Any]


# ==================== Helper Functions ====================

@dataclass
class SubnetData:
    """Subnet data for viability scoring."""
    netuid: int
    name: str
    pool_tao_reserve: float
    emission_share: float
    age_days: int
    alpha_price_tao: float
    taoflow_7d: float
    max_drawdown_30d: float


def _percentile_rank(values: List[float], target: float) -> float:
    """Compute percentile rank of target within values (0-100)."""
    if len(values) <= 1:
        return 50.0
    sorted_vals = sorted(values)
    rank = bisect_left(sorted_vals, target)
    return (rank / (len(sorted_vals) - 1)) * 100.0


def _apply_viability_filter(
    subnets: List[SubnetData],
    min_age_days: int,
    min_reserve_tao: float,
    max_outflow_7d_pct: float,
    max_drawdown_pct: float,
) -> Tuple[List[SubnetData], List[Tuple[SubnetData, List[str]]]]:
    """Apply hard failure thresholds.

    Returns (viable_subnets, [(failed_subnet, failure_reasons), ...])
    """
    viable: List[SubnetData] = []
    failed: List[Tuple[SubnetData, List[str]]] = []

    for sn in subnets:
        reasons: List[str] = []

        # Check age
        if sn.age_days < min_age_days:
            reasons.append(f"Age {sn.age_days}d < {min_age_days}d")

        # Check reserve
        if sn.pool_tao_reserve < min_reserve_tao:
            reasons.append(f"Reserve {sn.pool_tao_reserve:.0f} TAO < {min_reserve_tao:.0f}")

        # Check 7d outflow (as % of reserve)
        if sn.pool_tao_reserve > 0:
            outflow_pct = abs(min(sn.taoflow_7d, 0)) / sn.pool_tao_reserve * 100
            if outflow_pct > max_outflow_7d_pct:
                reasons.append(f"Outflow {outflow_pct:.1f}% > {max_outflow_7d_pct:.0f}%")

        # Check drawdown
        if sn.max_drawdown_30d * 100 > max_drawdown_pct:
            reasons.append(f"Drawdown {sn.max_drawdown_30d*100:.1f}% > {max_drawdown_pct:.0f}%")

        if reasons:
            failed.append((sn, reasons))
        else:
            viable.append(sn)

    return viable, failed


def _score_viability(
    subnets: List[SubnetData],
    fai_weight: float,
    reserve_weight: float,
    emission_weight: float,
    stability_weight: float,
) -> List[Tuple[SubnetData, float]]:
    """Score subnets using 4-factor viability scoring.

    Returns list of (subnet, score) tuples sorted by score descending.
    """
    if not subnets:
        return []

    # Collect raw values for percentile ranking
    fai_values = []
    reserve_values = []
    emission_values = []
    stability_values = []

    for sn in subnets:
        # FAI: flow relative to reserve (positive = inflow)
        fai = sn.taoflow_7d / max(sn.pool_tao_reserve, 1) if sn.pool_tao_reserve > 0 else 0
        fai_values.append(fai)
        reserve_values.append(sn.pool_tao_reserve)
        emission_values.append(sn.emission_share)
        # Stability: inverse of drawdown (lower drawdown = higher stability)
        stability_values.append(1.0 - sn.max_drawdown_30d)

    # Score each subnet
    scored: List[Tuple[SubnetData, float]] = []
    for i, sn in enumerate(subnets):
        # Percentile rank for each factor (0-100)
        fai_pctile = _percentile_rank(fai_values, fai_values[i])
        reserve_pctile = _percentile_rank(reserve_values, reserve_values[i])
        emission_pctile = _percentile_rank(emission_values, emission_values[i])
        stability_pctile = _percentile_rank(stability_values, stability_values[i])

        # Weighted composite score
        score = (
            fai_weight * fai_pctile +
            reserve_weight * reserve_pctile +
            emission_weight * emission_pctile +
            stability_weight * stability_pctile
        )

        scored.append((sn, score))

    # Sort by score descending
    return sorted(scored, key=lambda x: x[1], reverse=True)


def _compute_target_weights(
    selected: List[Tuple[SubnetData, float]],
    strategy: str,
    max_position_pct: float,
) -> Dict[int, float]:
    """Compute target weights for selected subnets.

    Returns dict of {netuid: weight_pct}
    """
    if not selected:
        return {}

    max_weight = max_position_pct / 100

    if strategy == "fai_weighted":
        # Use scores as weights (normalized)
        total_score = sum(score for _, score in selected)
        if total_score <= 0:
            # Fall back to equal weight
            base_weight = min(1.0 / len(selected), max_weight)
            return {sn.netuid: base_weight * 100 for sn, _ in selected}

        weights: Dict[int, float] = {}
        for sn, score in selected:
            raw_weight = score / total_score
            weights[sn.netuid] = min(raw_weight, max_weight)

        # Normalize to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            for netuid in weights:
                weights[netuid] = (weights[netuid] / total_weight) * 100

        return weights
    else:
        # Equal weight, capped by max_position_pct
        base_weight = 100.0 / len(selected)
        capped_weight = min(base_weight, max_position_pct)
        weights = {sn.netuid: capped_weight for sn, _ in selected}

        # Normalize if capping reduced total
        total_weight = sum(weights.values())
        if total_weight < 100.0:
            for netuid in weights:
                weights[netuid] = (weights[netuid] / total_weight) * 100

        return weights


# ==================== Endpoints ====================

@router.post("/compute-target", response_model=ComputeTargetResponse)
async def compute_target_portfolio(
    config: RebalanceConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> ComputeTargetResponse:
    """Compute target portfolio and required trades.

    Takes rebalance configuration from frontend (localStorage) and computes:
    1. Current portfolio from positions
    2. Viable subnets using viability filtering
    3. Target portfolio allocation
    4. Required trades with TAO amounts

    Returns full comparison for display in UI.
    """
    settings = get_settings()
    wallet = settings.wallet_address

    # Get viability config (from backend or request override)
    if config.use_backend_viability_config:
        # Use backend settings
        viability = ViabilityConfigRequest(
            min_age_days=settings.viability_min_age_days,
            min_reserve_tao=float(settings.viability_min_tao_reserve),
            max_outflow_7d_pct=float(settings.viability_max_negative_flow_ratio) * 100,
            max_drawdown_pct=float(settings.viability_max_drawdown_30d) * 100,
            fai_weight=float(settings.viability_weight_net_flow_7d),
            reserve_weight=float(settings.viability_weight_tao_reserve),
            emission_weight=float(settings.viability_weight_emission_share),
            stability_weight=float(settings.viability_weight_max_drawdown_30d),
        )
    else:
        viability = config.viability_config or ViabilityConfigRequest()

    # 1. Get current positions
    stmt = select(Position).where(Position.wallet_address == wallet)
    result = await db.execute(stmt)
    positions = list(result.scalars().all())

    # Calculate total portfolio value
    total_portfolio_value = sum(float(p.tao_value_mid or 0) for p in positions)

    # Build current portfolio snapshots
    current_portfolio: List[PositionSnapshot] = []
    current_weights: Dict[int, float] = {}

    for pos in positions:
        tao_value = float(pos.tao_value_mid or 0)
        weight_pct = (tao_value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0

        # Get subnet name
        subnet_stmt = select(Subnet.name).where(Subnet.netuid == pos.netuid)
        name_result = await db.execute(subnet_stmt)
        name = name_result.scalar() or f"Subnet {pos.netuid}"

        current_portfolio.append(PositionSnapshot(
            netuid=pos.netuid,
            name=name,
            tao_value=round(tao_value, 4),
            weight_pct=round(weight_pct, 2),
        ))
        current_weights[pos.netuid] = weight_pct

    # 2. Get all subnets for viability scoring
    stmt = select(Subnet).where(Subnet.netuid != 0)  # Exclude root
    result = await db.execute(stmt)
    all_subnets = list(result.scalars().all())

    # Convert to SubnetData for scoring
    subnet_data: List[SubnetData] = []
    now = datetime.now(timezone.utc)

    for sn in all_subnets:
        # Compute age
        age_days = 0
        if sn.registered_at:
            age_days = max(0, (now - sn.registered_at).days)

        # Get flow and drawdown data
        # Note: These fields may not exist on all subnet records
        taoflow_7d = float(getattr(sn, 'taoflow_7d', 0) or 0)
        max_drawdown = float(getattr(sn, 'max_drawdown_30d', 0) or 0)

        subnet_data.append(SubnetData(
            netuid=sn.netuid,
            name=sn.name,
            pool_tao_reserve=float(sn.pool_tao_reserve or 0),
            emission_share=float(sn.emission_share or 0),
            age_days=age_days,
            alpha_price_tao=float(sn.alpha_price_tao or 0),
            taoflow_7d=taoflow_7d,
            max_drawdown_30d=max_drawdown,
        ))

    # 3. Apply viability filtering
    viable_subnets, failed_subnets = _apply_viability_filter(
        subnet_data,
        min_age_days=viability.min_age_days,
        min_reserve_tao=viability.min_reserve_tao,
        max_outflow_7d_pct=viability.max_outflow_7d_pct,
        max_drawdown_pct=viability.max_drawdown_pct,
    )

    # 4. Score viable subnets
    scored_subnets = _score_viability(
        viable_subnets,
        fai_weight=viability.fai_weight,
        reserve_weight=viability.reserve_weight,
        emission_weight=viability.emission_weight,
        stability_weight=viability.stability_weight,
    )

    # 5. Select top percentile
    num_to_select = max(1, int(len(scored_subnets) * config.top_percentile / 100))
    selected = scored_subnets[:num_to_select]

    # 6. Compute target weights
    target_weights = _compute_target_weights(
        selected,
        strategy=config.strategy,
        max_position_pct=config.max_position_pct,
    )

    # Build target portfolio snapshots
    target_portfolio: List[PositionSnapshot] = []
    for sn, score in selected:
        target_weight = target_weights.get(sn.netuid, 0)
        target_tao = total_portfolio_value * target_weight / 100

        target_portfolio.append(PositionSnapshot(
            netuid=sn.netuid,
            name=sn.name,
            tao_value=round(target_tao, 4),
            weight_pct=round(target_weight, 2),
            viability_score=round(score, 1),
            is_viable=True,
        ))

    # 7. Compute total drift
    all_netuids = set(current_weights.keys()) | set(target_weights.keys())
    total_drift = 0.0
    for netuid in all_netuids:
        current_w = current_weights.get(netuid, 0)
        target_w = target_weights.get(netuid, 0)
        total_drift += abs(current_w - target_w)
    total_drift_pct = total_drift / 2  # Divide by 2 to avoid double-counting

    # 8. Check if rebalance needed
    needs_rebalance = total_drift_pct >= config.portfolio_threshold_pct

    # 9. Compute required trades
    trades: List[TradeRecommendation] = []
    total_buy_tao = 0.0
    total_sell_tao = 0.0

    # Map netuids to names
    netuid_names: Dict[int, str] = {}
    for sn in subnet_data:
        netuid_names[sn.netuid] = sn.name
    for pos in current_portfolio:
        netuid_names[pos.netuid] = pos.name

    for netuid in all_netuids:
        current_w = current_weights.get(netuid, 0)
        target_w = target_weights.get(netuid, 0)
        delta_pct = target_w - current_w

        # Skip small trades below position threshold
        if abs(delta_pct) < config.position_threshold_pct:
            continue

        tao_amount = abs(total_portfolio_value * delta_pct / 100)
        name = netuid_names.get(netuid, f"Subnet {netuid}")

        if delta_pct > 0:
            # Buy
            trades.append(TradeRecommendation(
                netuid=netuid,
                name=name,
                action="buy",
                tao_amount=round(tao_amount, 4),
                current_weight_pct=round(current_w, 2),
                target_weight_pct=round(target_w, 2),
                delta_pct=round(delta_pct, 2),
                reason=f"Increase allocation to target {target_w:.1f}%",
                priority=3,
            ))
            total_buy_tao += tao_amount
        elif delta_pct < 0:
            if target_w == 0:
                # Full exit
                trades.append(TradeRecommendation(
                    netuid=netuid,
                    name=name,
                    action="exit",
                    tao_amount=round(tao_amount, 4),
                    current_weight_pct=round(current_w, 2),
                    target_weight_pct=0,
                    delta_pct=round(delta_pct, 2),
                    reason="Exit: not in target portfolio",
                    priority=1,
                ))
            else:
                # Partial sell
                trades.append(TradeRecommendation(
                    netuid=netuid,
                    name=name,
                    action="sell",
                    tao_amount=round(tao_amount, 4),
                    current_weight_pct=round(current_w, 2),
                    target_weight_pct=round(target_w, 2),
                    delta_pct=round(delta_pct, 2),
                    reason=f"Reduce to target {target_w:.1f}%",
                    priority=2,
                ))
            total_sell_tao += tao_amount

    # Sort trades by priority (exits first, then sells, then buys)
    trades.sort(key=lambda t: t.priority)

    # 10. Build response
    net_turnover_pct = (total_buy_tao + total_sell_tao) / max(total_portfolio_value, 1) * 100

    summary = RebalanceSummary(
        current_portfolio_value=round(total_portfolio_value, 4),
        total_drift_pct=round(total_drift_pct, 2),
        needs_rebalance=needs_rebalance,
        trades_count=len(trades),
        total_buy_tao=round(total_buy_tao, 4),
        total_sell_tao=round(total_sell_tao, 4),
        net_turnover_pct=round(net_turnover_pct, 2),
    )

    config_used = {
        "strategy": config.strategy,
        "top_percentile": config.top_percentile,
        "max_position_pct": config.max_position_pct,
        "position_threshold_pct": config.position_threshold_pct,
        "portfolio_threshold_pct": config.portfolio_threshold_pct,
        "viability": {
            "min_age_days": viability.min_age_days,
            "min_reserve_tao": viability.min_reserve_tao,
            "max_outflow_7d_pct": viability.max_outflow_7d_pct,
            "max_drawdown_pct": viability.max_drawdown_pct,
            "weights": {
                "fai": viability.fai_weight,
                "reserve": viability.reserve_weight,
                "emission": viability.emission_weight,
                "stability": viability.stability_weight,
            },
        },
    }

    logger.info(
        "Computed target portfolio",
        portfolio_value=total_portfolio_value,
        current_positions=len(current_portfolio),
        viable_subnets=len(viable_subnets),
        target_positions=len(target_portfolio),
        trades=len(trades),
        total_drift=f"{total_drift_pct:.1f}%",
        needs_rebalance=needs_rebalance,
    )

    return ComputeTargetResponse(
        computed_at=datetime.now(timezone.utc),
        summary=summary,
        current_portfolio=current_portfolio,
        target_portfolio=target_portfolio,
        trades=trades,
        viable_subnets_count=len(viable_subnets),
        filtered_out_count=len(failed_subnets),
        config_used=config_used,
    )


@router.get("/viable-subnets")
async def get_viable_subnets(
    min_age_days: int = Query(default=60, ge=0, le=365),
    min_reserve_tao: float = Query(default=500.0, ge=0, le=10000),
    max_outflow_7d_pct: float = Query(default=50.0, ge=0, le=100),
    max_drawdown_pct: float = Query(default=50.0, ge=0, le=100),
    fai_weight: float = Query(default=0.35, ge=0, le=1),
    reserve_weight: float = Query(default=0.25, ge=0, le=1),
    emission_weight: float = Query(default=0.25, ge=0, le=1),
    stability_weight: float = Query(default=0.15, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get list of viable subnets with their viability scores.

    Useful for understanding which subnets pass viability checks
    and their relative scores before computing a target portfolio.
    """
    # Get all subnets
    stmt = select(Subnet).where(Subnet.netuid != 0)
    result = await db.execute(stmt)
    all_subnets = list(result.scalars().all())

    # Convert to SubnetData
    subnet_data: List[SubnetData] = []
    now = datetime.now(timezone.utc)

    for sn in all_subnets:
        age_days = 0
        if sn.registered_at:
            age_days = max(0, (now - sn.registered_at).days)

        taoflow_7d = float(getattr(sn, 'taoflow_7d', 0) or 0)
        max_drawdown = float(getattr(sn, 'max_drawdown_30d', 0) or 0)

        subnet_data.append(SubnetData(
            netuid=sn.netuid,
            name=sn.name,
            pool_tao_reserve=float(sn.pool_tao_reserve or 0),
            emission_share=float(sn.emission_share or 0),
            age_days=age_days,
            alpha_price_tao=float(sn.alpha_price_tao or 0),
            taoflow_7d=taoflow_7d,
            max_drawdown_30d=max_drawdown,
        ))

    # Apply filtering
    viable, failed = _apply_viability_filter(
        subnet_data,
        min_age_days=min_age_days,
        min_reserve_tao=min_reserve_tao,
        max_outflow_7d_pct=max_outflow_7d_pct,
        max_drawdown_pct=max_drawdown_pct,
    )

    # Score viable subnets
    scored = _score_viability(
        viable,
        fai_weight=fai_weight,
        reserve_weight=reserve_weight,
        emission_weight=emission_weight,
        stability_weight=stability_weight,
    )

    return {
        "total_subnets": len(subnet_data),
        "viable_count": len(viable),
        "filtered_out_count": len(failed),
        "viable_subnets": [
            {
                "netuid": sn.netuid,
                "name": sn.name,
                "viability_score": round(score, 1),
                "pool_tao_reserve": round(sn.pool_tao_reserve, 2),
                "emission_share": round(sn.emission_share, 6),
                "age_days": sn.age_days,
                "taoflow_7d": round(sn.taoflow_7d, 2),
                "max_drawdown_30d": round(sn.max_drawdown_30d * 100, 1),
            }
            for sn, score in scored
        ],
        "failed_subnets": [
            {
                "netuid": sn.netuid,
                "name": sn.name,
                "failure_reasons": reasons,
            }
            for sn, reasons in failed
        ],
    }
