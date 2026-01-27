"""Base signal classes and schemas for Phase 3.

Defines the standard output schema and base class for all signals.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import json


class SignalStatus(str, Enum):
    """Status of a signal execution."""
    OK = "ok"              # Signal ran successfully, output is trustworthy
    DEGRADED = "degraded"  # Signal ran but with reduced confidence
    BLOCKED = "blocked"    # Signal cannot produce trustworthy output


class SignalConfidence(str, Enum):
    """Confidence level of signal output."""
    HIGH = "high"      # Strong evidence, clear action
    MEDIUM = "medium"  # Reasonable evidence, some uncertainty
    LOW = "low"        # Weak evidence, high uncertainty


@dataclass
class SignalOutput:
    """Standard output schema for all signals.

    Every signal must produce output in this format.
    """
    # Status
    status: SignalStatus

    # Human-readable summary
    summary: str

    # Recommended action (human readable, no auto-execution)
    recommended_action: str

    # Evidence supporting the recommendation
    evidence: Dict[str, Any] = field(default_factory=dict)

    # Guardrails that were triggered
    guardrails_triggered: List[str] = field(default_factory=list)

    # Confidence level with explicit reason
    confidence: SignalConfidence = SignalConfidence.LOW
    confidence_reason: str = ""

    # Error message if status is blocked
    error_message: Optional[str] = None

    # Timestamp
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "summary": self.summary,
            "recommended_action": self.recommended_action,
            "evidence": self.evidence,
            "guardrails_triggered": self.guardrails_triggered,
            "confidence": self.confidence.value,
            "confidence_reason": self.confidence_reason,
            "error_message": self.error_message,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def blocked(cls, reason: str, guardrails: List[str] = None) -> "SignalOutput":
        """Create a blocked output."""
        return cls(
            status=SignalStatus.BLOCKED,
            summary=f"Signal blocked: {reason}",
            recommended_action="Resolve blocking issues before acting on this signal.",
            guardrails_triggered=guardrails or [reason],
            confidence=SignalConfidence.LOW,
            confidence_reason=reason,
            error_message=reason,
        )

    @classmethod
    def degraded(cls, summary: str, action: str, reason: str, evidence: Dict[str, Any] = None) -> "SignalOutput":
        """Create a degraded output."""
        return cls(
            status=SignalStatus.DEGRADED,
            summary=summary,
            recommended_action=action,
            evidence=evidence or {},
            guardrails_triggered=[reason],
            confidence=SignalConfidence.LOW,
            confidence_reason=f"Degraded: {reason}",
        )


@dataclass
class SignalDefinition:
    """Metadata definition for a signal.

    Per spec: each signal must have clear documentation of its
    purpose, edge hypothesis, and correctness risks.
    """
    id: str
    name: str
    description: str

    # What action does this signal support?
    actionability: str
    actionability_score: int  # 1-10, higher = more actionable

    # Why might this signal provide edge?
    edge_hypothesis: str

    # What could go wrong?
    correctness_risks: List[str]

    # What data does it need?
    required_datasets: List[str]

    # Cost and performance
    ongoing_cost: str  # e.g., "1 API call per run"
    latency_sensitivity: str  # e.g., "low - can be stale 1h"

    # Failure behavior
    failure_behavior: str


class BaseSignal(ABC):
    """Base class for all signals.

    Signals must:
    1. Define their metadata via get_definition()
    2. Implement run() to produce SignalOutput
    3. Use guardrails for data quality checks
    """

    @abstractmethod
    def get_definition(self) -> SignalDefinition:
        """Return the signal's metadata definition."""
        pass

    @abstractmethod
    async def run(self) -> SignalOutput:
        """Execute the signal and return output.

        Must handle errors gracefully and return blocked/degraded
        status when appropriate.
        """
        pass

    def compute_inputs_hash(self, inputs: Dict[str, Any]) -> str:
        """Compute a hash of inputs for versioning."""
        # Sort keys for consistent hashing
        serialized = json.dumps(inputs, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    @property
    def signal_id(self) -> str:
        """Shortcut to get signal ID."""
        return self.get_definition().id

    @property
    def signal_name(self) -> str:
        """Shortcut to get signal name."""
        return self.get_definition().name
