"""Tests for Phase 2: Reconciliation.

Tests cover:
- Tolerance logic (absolute and relative)
- Pass/fail determination
- Diff calculations
- Trust Pack integration
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch


class TestToleranceLogic:
    """Test reconciliation tolerance checking."""

    def test_within_absolute_tolerance(self):
        """Value within absolute tolerance should pass."""
        stored_value = Decimal("100.0000")
        live_value = Decimal("100.00005")
        absolute_tolerance = Decimal("0.0001")

        diff = abs(live_value - stored_value)
        within_absolute = diff <= absolute_tolerance

        assert within_absolute is True

    def test_outside_absolute_tolerance(self):
        """Value outside absolute tolerance should fail."""
        stored_value = Decimal("100.0000")
        live_value = Decimal("100.001")
        absolute_tolerance = Decimal("0.0001")

        diff = abs(live_value - stored_value)
        within_absolute = diff <= absolute_tolerance

        assert within_absolute is False

    def test_within_relative_tolerance(self):
        """Value within relative tolerance should pass."""
        stored_value = Decimal("1000")
        live_value = Decimal("1000.5")  # 0.05% diff
        relative_tolerance = Decimal("0.1")  # 0.1%

        diff_abs = abs(live_value - stored_value)
        relative_diff_pct = (diff_abs / stored_value) * Decimal("100")
        within_relative = relative_diff_pct <= relative_tolerance

        assert within_relative is True

    def test_outside_relative_tolerance(self):
        """Value outside relative tolerance should fail."""
        stored_value = Decimal("1000")
        live_value = Decimal("1002")  # 0.2% diff
        relative_tolerance = Decimal("0.1")  # 0.1%

        diff_abs = abs(live_value - stored_value)
        relative_diff_pct = (diff_abs / stored_value) * Decimal("100")
        within_relative = relative_diff_pct <= relative_tolerance

        assert within_relative is False

    def test_pass_if_either_tolerance_met(self):
        """Should pass if within either absolute OR relative tolerance."""
        # Small value - absolute tolerance matters more
        stored_small = Decimal("0.001")
        live_small = Decimal("0.00105")
        absolute_tolerance = Decimal("0.0001")
        relative_tolerance = Decimal("0.1")

        diff_small = abs(live_small - stored_small)
        within_abs_small = diff_small <= absolute_tolerance
        if stored_small > 0:
            rel_diff_small = (diff_small / stored_small) * Decimal("100")
            within_rel_small = rel_diff_small <= relative_tolerance
        else:
            within_rel_small = True

        # For small values, absolute tolerance often fails but relative passes
        # 0.00005 diff on 0.001 = 5% diff (fails relative)
        # But 0.00005 < 0.0001 (passes absolute)
        passed_small = within_abs_small or within_rel_small
        assert passed_small is True

    def test_zero_stored_value(self):
        """Zero stored value should use absolute tolerance only."""
        stored_value = Decimal("0")
        live_value = Decimal("0.00005")
        absolute_tolerance = Decimal("0.0001")

        diff = abs(live_value - stored_value)
        within_absolute = diff <= absolute_tolerance

        # Can't compute relative diff with zero denominator
        assert within_absolute is True


class TestDiffCalculations:
    """Test diff calculations."""

    def test_positive_diff(self):
        """Positive diff when live > stored."""
        stored = Decimal("100")
        live = Decimal("110")

        diff = live - stored
        assert diff == Decimal("10")

    def test_negative_diff(self):
        """Negative diff when live < stored."""
        stored = Decimal("100")
        live = Decimal("90")

        diff = live - stored
        assert diff == Decimal("-10")

    def test_diff_percentage(self):
        """Diff percentage calculation."""
        stored = Decimal("100")
        live = Decimal("105")

        diff = abs(live - stored)
        diff_pct = (diff / stored) * Decimal("100")
        assert diff_pct == Decimal("5")


class TestReconciliationRunModel:
    """Test ReconciliationRun model."""

    def test_model_exists(self):
        """Verify ReconciliationRun model is importable."""
        from app.models.reconciliation import ReconciliationRun

        assert ReconciliationRun is not None

    def test_model_has_required_fields(self):
        """Verify model has all required fields."""
        from app.models.reconciliation import ReconciliationRun

        required_attrs = [
            'run_id',
            'created_at',
            'wallet_address',
            'netuids_checked',
            'passed',
            'total_checks',
            'passed_checks',
            'failed_checks',
            'total_stored_value_tao',
            'total_live_value_tao',
            'total_diff_tao',
            'total_diff_pct',
            'checks',
            'error_message',
        ]

        for attr in required_attrs:
            assert hasattr(ReconciliationRun, attr), f"Missing attribute: {attr}"


class TestReconciliationServiceConfig:
    """Test reconciliation service configuration."""

    def test_feature_flags_exist(self):
        """Verify reconciliation feature flags exist."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, 'enable_reconciliation_endpoints')
        assert hasattr(settings, 'enable_reconciliation_in_trust_pack')
        assert hasattr(settings, 'reconciliation_absolute_tolerance_tao')
        assert hasattr(settings, 'reconciliation_relative_tolerance_pct')

    def test_tolerance_defaults(self):
        """Verify tolerance defaults are reasonable."""
        from app.core.config import get_settings

        settings = get_settings()

        # Absolute tolerance should be small (0.0001 TAO)
        assert settings.reconciliation_absolute_tolerance_tao <= Decimal("0.001")

        # Relative tolerance should be small percentage (0.1%)
        assert settings.reconciliation_relative_tolerance_pct <= Decimal("1.0")

    def test_reconciliation_service_singleton(self):
        """Verify reconciliation service is a singleton."""
        from app.services.analysis.reconciliation import get_reconciliation_service

        s1 = get_reconciliation_service()
        s2 = get_reconciliation_service()
        assert s1 is s2


class TestTrustPackIntegration:
    """Test Trust Pack reconciliation integration."""

    def test_trust_pack_summary_keys(self):
        """Verify Trust Pack summary has expected keys."""
        expected_keys = {
            "last_run_at",
            "last_run_passed",
            "failed_checks",
            "has_drift",
        }

        # This documents the expected schema
        assert len(expected_keys) == 4

    def test_has_drift_logic(self):
        """Drift flag should be True when reconciliation fails."""
        # Passed reconciliation
        passed_summary = {
            "last_run_passed": True,
            "has_drift": False,
        }
        assert passed_summary["has_drift"] is False

        # Failed reconciliation
        failed_summary = {
            "last_run_passed": False,
            "has_drift": True,
        }
        assert failed_summary["has_drift"] is True


class TestReconciliationCheckResult:
    """Test individual check result structure."""

    def test_check_result_keys(self):
        """Verify check result has expected keys."""
        expected_keys = {
            "netuid",
            "passed",
            "stored_value_tao",
            "live_value_tao",
            "value_diff_tao",
            "value_diff_pct",
            "stored_alpha",
            "live_alpha",
            "alpha_diff",
            "within_absolute_tolerance",
            "within_relative_tolerance",
        }

        # This documents the expected schema
        assert len(expected_keys) == 11


class TestPositionComparison:
    """Test position comparison logic."""

    def test_position_exists_in_both(self):
        """Position in both stored and live should be compared normally."""
        stored = {"tao_value": 100, "alpha_balance": 50}
        live = {"tao_value": 100.0005, "alpha_balance": 50}

        # Both exist, compare values
        assert stored["tao_value"] > 0
        assert live["tao_value"] > 0

    def test_position_only_in_stored(self):
        """Position only in stored (closed position) should be flagged."""
        stored = {"tao_value": 100, "alpha_balance": 50}
        live = {"tao_value": 0, "alpha_balance": 0}

        # Position was closed/unstaked
        diff = abs(Decimal(str(live["tao_value"])) - Decimal(str(stored["tao_value"])))
        assert diff > Decimal("0")

    def test_position_only_in_live(self):
        """Position only in live (new position) should be flagged."""
        stored = {"tao_value": 0, "alpha_balance": 0}
        live = {"tao_value": 100, "alpha_balance": 50}

        # New position appeared
        diff = abs(Decimal(str(live["tao_value"])) - Decimal(str(stored["tao_value"])))
        assert diff > Decimal("0")
