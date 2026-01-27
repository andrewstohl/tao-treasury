"""Tests for Phase 3: Decision Support Signals.

Tests cover:
- Signal framework (registry, output schema, storage)
- Signal definitions and metadata
- Guardrail checks
- Individual signal logic
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


class TestSignalOutput:
    """Test SignalOutput dataclass and methods."""

    def test_signal_output_creation(self):
        """Verify SignalOutput can be created with all fields."""
        from app.services.signals.base import SignalOutput, SignalStatus, SignalConfidence

        output = SignalOutput(
            status=SignalStatus.OK,
            summary="Test summary",
            recommended_action="Test action",
            evidence={"key": "value"},
            guardrails_triggered=["test_guardrail"],
            confidence=SignalConfidence.HIGH,
            confidence_reason="Test reason",
        )

        assert output.status == SignalStatus.OK
        assert output.summary == "Test summary"
        assert output.confidence == SignalConfidence.HIGH

    def test_signal_output_to_dict(self):
        """Verify to_dict serializes correctly."""
        from app.services.signals.base import SignalOutput, SignalStatus, SignalConfidence

        output = SignalOutput(
            status=SignalStatus.DEGRADED,
            summary="Test",
            recommended_action="Action",
            evidence={"metric": 100},
            guardrails_triggered=["g1", "g2"],
            confidence=SignalConfidence.MEDIUM,
            confidence_reason="Reason",
        )

        result = output.to_dict()

        assert result["status"] == "degraded"
        assert result["confidence"] == "medium"
        assert result["guardrails_triggered"] == ["g1", "g2"]
        assert result["evidence"] == {"metric": 100}

    def test_signal_output_blocked_factory(self):
        """Verify blocked() factory creates correct output."""
        from app.services.signals.base import SignalOutput, SignalStatus, SignalConfidence

        output = SignalOutput.blocked("Test failure reason")

        assert output.status == SignalStatus.BLOCKED
        assert output.confidence == SignalConfidence.LOW
        assert "Test failure reason" in output.summary

    def test_signal_output_degraded_factory(self):
        """Verify degraded() factory creates correct output."""
        from app.services.signals.base import SignalOutput, SignalStatus, SignalConfidence

        output = SignalOutput.degraded(
            summary="Test summary",
            action="Test action",
            reason="guardrail1",
        )

        assert output.status == SignalStatus.DEGRADED
        assert output.confidence == SignalConfidence.LOW
        assert "guardrail1" in output.guardrails_triggered


class TestSignalDefinition:
    """Test SignalDefinition schema."""

    def test_signal_definition_required_fields(self):
        """Verify SignalDefinition has all required fields."""
        from app.services.signals.base import SignalDefinition

        defn = SignalDefinition(
            id="test_signal",
            name="Test Signal",
            description="A test signal",
            actionability="How to act on this",
            actionability_score=5,
            edge_hypothesis="Why this works",
            correctness_risks=["risk1", "risk2"],
            required_datasets=["dataset1"],
            ongoing_cost="Low",
            latency_sensitivity="Medium",
            failure_behavior="Falls back to LOW confidence",
        )

        assert defn.id == "test_signal"
        assert defn.actionability_score == 5
        assert len(defn.correctness_risks) == 2


class TestSignalRegistry:
    """Test SignalRegistry functionality."""

    def test_registry_initialization(self):
        """Registry should initialize empty."""
        from app.services.signals.registry import SignalRegistry

        registry = SignalRegistry()
        assert len(registry.get_all_signals()) == 0

    def test_register_signal(self):
        """Signal registration should work."""
        from app.services.signals.registry import SignalRegistry
        from app.services.signals.base import BaseSignal, SignalDefinition, SignalOutput

        class MockSignal(BaseSignal):
            def get_definition(self):
                return SignalDefinition(
                    id="mock",
                    name="Mock",
                    description="Mock signal",
                    actionability="Mock action",
                    actionability_score=1,
                    edge_hypothesis="Mock hypothesis",
                    correctness_risks=[],
                    required_datasets=[],
                    ongoing_cost="Low",
                    latency_sensitivity="Low",
                    failure_behavior="Mock",
                )

            async def run(self):
                return SignalOutput.blocked("Mock")

        registry = SignalRegistry()
        registry.register(MockSignal())

        assert len(registry.get_all_signals()) == 1
        assert registry.get_signal("mock") is not None

    def test_get_catalog(self):
        """get_catalog should return signal definitions."""
        from app.services.signals.registry import SignalRegistry
        from app.services.signals.base import BaseSignal, SignalDefinition, SignalOutput

        class MockSignal(BaseSignal):
            def get_definition(self):
                return SignalDefinition(
                    id="catalog_test",
                    name="Catalog Test",
                    description="Test description",
                    actionability="Test action",
                    actionability_score=7,
                    edge_hypothesis="Test hypothesis",
                    correctness_risks=["risk"],
                    required_datasets=["data"],
                    ongoing_cost="Medium",
                    latency_sensitivity="High",
                    failure_behavior="Test",
                )

            async def run(self):
                return SignalOutput.blocked("Test")

        registry = SignalRegistry()
        registry.register(MockSignal())

        catalog = registry.get_catalog()

        assert len(catalog) == 1
        assert catalog[0]["id"] == "catalog_test"
        assert catalog[0]["actionability_score"] == 7


class TestGuardrailChecker:
    """Test GuardrailChecker functionality."""

    def test_check_sample_size_pass(self):
        """Sample size check should pass when sufficient."""
        from app.services.signals.guardrails import GuardrailChecker

        checker = GuardrailChecker()
        result = checker.check_sample_size(
            count=10,
            minimum=5,
            context="test_data",
        )

        assert result.passed is True

    def test_check_sample_size_fail(self):
        """Sample size check should fail when insufficient."""
        from app.services.signals.guardrails import GuardrailChecker

        checker = GuardrailChecker()
        result = checker.check_sample_size(
            count=3,
            minimum=5,
            context="test_data",
        )

        assert result.passed is False
        assert "insufficient" in result.reason.lower()

    def test_check_concentration_limit_pass(self):
        """Concentration check should pass when within limit."""
        from app.services.signals.guardrails import GuardrailChecker

        checker = GuardrailChecker()
        result = checker.check_concentration_limit(
            current_pct=Decimal("0.15"),
            limit_pct=Decimal("0.25"),
            context="test_position",
        )

        assert result.passed is True

    def test_check_concentration_limit_fail(self):
        """Concentration check should fail when exceeding limit."""
        from app.services.signals.guardrails import GuardrailChecker

        checker = GuardrailChecker()
        result = checker.check_concentration_limit(
            current_pct=Decimal("0.30"),
            limit_pct=Decimal("0.25"),
            context="test_position",
        )

        assert result.passed is False


class TestDataTrustGateSignal:
    """Test DataTrustGateSignal implementation."""

    def test_signal_definition(self):
        """Data trust gate should have proper definition."""
        from app.services.signals.implementations.data_trust_gate import DataTrustGateSignal

        signal = DataTrustGateSignal()
        defn = signal.get_definition()

        assert defn.id == "data_trust_gate"
        assert defn.actionability_score == 10  # Highest priority
        assert "trust_pack" in defn.required_datasets

    @pytest.mark.asyncio
    async def test_signal_run_ok_when_fresh(self):
        """Trust gate should be OK when data is fresh."""
        from app.services.signals.implementations.data_trust_gate import DataTrustGateSignal
        from app.services.signals.base import SignalStatus

        with patch("app.services.signals.implementations.data_trust_gate.data_sync_service") as mock_sync:
            mock_sync.is_data_stale.return_value = False
            mock_sync.last_sync = datetime.now(timezone.utc)

            with patch("app.services.signals.implementations.data_trust_gate.get_settings") as mock_settings:
                settings_obj = MagicMock()
                settings_obj.enable_reconciliation = False
                settings_obj.enable_sync_metrics = False
                settings_obj.stale_data_threshold_minutes = 30
                mock_settings.return_value = settings_obj

                signal = DataTrustGateSignal()
                output = await signal.run()

                assert output.status == SignalStatus.OK

    @pytest.mark.asyncio
    async def test_signal_run_blocked_when_stale(self):
        """Trust gate should be BLOCKED when data is stale."""
        from app.services.signals.implementations.data_trust_gate import DataTrustGateSignal
        from app.services.signals.base import SignalStatus

        with patch("app.services.signals.implementations.data_trust_gate.data_sync_service") as mock_sync:
            mock_sync.is_data_stale.return_value = True
            mock_sync.last_sync = None

            with patch("app.services.signals.implementations.data_trust_gate.get_settings") as mock_settings:
                settings_obj = MagicMock()
                settings_obj.enable_reconciliation = False
                settings_obj.enable_sync_metrics = False
                settings_obj.stale_data_threshold_minutes = 30
                mock_settings.return_value = settings_obj

                signal = DataTrustGateSignal()
                output = await signal.run()

                assert output.status == SignalStatus.BLOCKED
                assert "data_staleness" in output.guardrails_triggered


class TestEarningsLeaderboardSignal:
    """Test EarningsLeaderboardSignal implementation."""

    def test_signal_definition(self):
        """Earnings leaderboard should have proper definition."""
        from app.services.signals.implementations.earnings_leaderboard import EarningsLeaderboardSignal

        signal = EarningsLeaderboardSignal()
        defn = signal.get_definition()

        assert defn.id == "earnings_leaderboard"
        assert "position_snapshots" in defn.required_datasets


class TestSlippageCapacitySignal:
    """Test SlippageCapacitySignal implementation."""

    def test_signal_definition(self):
        """Slippage capacity should have proper definition."""
        from app.services.signals.implementations.slippage_capacity import SlippageCapacitySignal

        signal = SlippageCapacitySignal()
        defn = signal.get_definition()

        assert defn.id == "slippage_capacity"
        assert "slippage_surfaces" in defn.required_datasets


class TestConcentrationRiskSignal:
    """Test ConcentrationRiskSignal implementation."""

    def test_signal_definition(self):
        """Concentration risk should have proper definition."""
        from app.services.signals.implementations.concentration_risk import ConcentrationRiskSignal

        signal = ConcentrationRiskSignal()
        defn = signal.get_definition()

        assert defn.id == "concentration_risk"
        assert "positions" in defn.required_datasets


class TestSignalRunModel:
    """Test SignalRun storage model."""

    def test_model_exists(self):
        """Verify SignalRun model is importable."""
        from app.models.signal import SignalRun

        assert SignalRun is not None

    def test_model_has_required_fields(self):
        """Verify model has all required fields."""
        from app.models.signal import SignalRun

        required_attrs = [
            "run_id",
            "created_at",
            "signal_id",
            "signal_name",
            "status",
            "confidence",
            "confidence_reason",
            "summary",
            "recommended_action",
            "evidence",
            "guardrails_triggered",
            "full_output",
        ]

        for attr in required_attrs:
            assert hasattr(SignalRun, attr), f"Missing attribute: {attr}"


class TestSignalEndpointConfig:
    """Test signal endpoint configuration."""

    def test_feature_flag_exists(self):
        """Verify signal feature flag exists in settings."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "enable_signal_endpoints")

    def test_slippage_threshold_exists(self):
        """Verify slippage threshold exists in settings."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "slippage_threshold_pct")
        assert settings.slippage_threshold_pct <= Decimal("5.0")


class TestSignalStatus:
    """Test SignalStatus enum values."""

    def test_status_values(self):
        """Verify expected status values exist."""
        from app.services.signals.base import SignalStatus

        assert SignalStatus.OK.value == "ok"
        assert SignalStatus.DEGRADED.value == "degraded"
        assert SignalStatus.BLOCKED.value == "blocked"


class TestSignalConfidence:
    """Test SignalConfidence enum values."""

    def test_confidence_values(self):
        """Verify expected confidence values exist."""
        from app.services.signals.base import SignalConfidence

        assert SignalConfidence.HIGH.value == "high"
        assert SignalConfidence.MEDIUM.value == "medium"
        assert SignalConfidence.LOW.value == "low"


class TestSignalRegistrySingleton:
    """Test signal registry singleton behavior."""

    def test_registry_singleton(self):
        """Verify registry is a singleton."""
        from app.services.signals.registry import get_signal_registry

        r1 = get_signal_registry()
        r2 = get_signal_registry()
        assert r1 is r2

    def test_registry_has_all_signals(self):
        """Verify all 4 signals are registered."""
        from app.services.signals.registry import get_signal_registry

        registry = get_signal_registry()
        signals = registry.get_all_signals()

        # Should have at least 4 signals
        assert len(signals) >= 4

        # Check specific signals exist
        signal_ids = [s.get_definition().id for s in signals]
        assert "data_trust_gate" in signal_ids
        assert "earnings_leaderboard" in signal_ids
        assert "slippage_capacity" in signal_ids
        assert "concentration_risk" in signal_ids
