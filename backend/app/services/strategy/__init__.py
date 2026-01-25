"""Strategy Engine v1 for TAO Treasury Management.

This module implements the core strategy logic:
- Taoflow regime model (Risk On/Neutral/Risk Off/Quarantine/Dead)
- Eligibility gate with hard excludes
- Position sizing by exitability and concentration
- Weekly and event-driven rebalance recommendations
- Constraint enforcement with detailed explanations

All outputs are advisory only - no auto-execution per spec.
"""

from app.services.strategy.regime_calculator import (
    FlowRegime,
    RegimeCalculator,
    regime_calculator,
)
from app.services.strategy.eligibility_gate import (
    EligibilityResult,
    EligibilityGate,
    eligibility_gate,
)
from app.services.strategy.position_sizer import (
    PositionLimit,
    PositionSizer,
    position_sizer,
)
from app.services.strategy.rebalancer import (
    TriggerType,
    RebalanceResult,
    Rebalancer,
    rebalancer,
)
from app.services.strategy.constraint_enforcer import (
    ConstraintSeverity,
    ConstraintViolation,
    ConstraintStatus,
    ConstraintEnforcer,
    constraint_enforcer,
)
from app.services.strategy.strategy_engine import (
    PortfolioState,
    StrategyAnalysis,
    ConstraintCheck,
    StrategyEngine,
    strategy_engine,
)

__all__ = [
    # Regime
    "FlowRegime",
    "RegimeCalculator",
    "regime_calculator",
    # Eligibility
    "EligibilityResult",
    "EligibilityGate",
    "eligibility_gate",
    # Position sizing
    "PositionLimit",
    "PositionSizer",
    "position_sizer",
    # Rebalancing
    "TriggerType",
    "RebalanceResult",
    "Rebalancer",
    "rebalancer",
    # Constraints
    "ConstraintSeverity",
    "ConstraintViolation",
    "ConstraintStatus",
    "ConstraintEnforcer",
    "constraint_enforcer",
    # Main engine
    "PortfolioState",
    "StrategyAnalysis",
    "ConstraintCheck",
    "StrategyEngine",
    "strategy_engine",
]
