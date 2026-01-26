"""Unit tests for regime persistence (anti-whipsaw) functionality.

Tests that regime transitions require N consecutive days of the
candidate regime before being applied.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))


class TestRegimePersistenceBasics:
    """Test basic persistence logic."""

    def test_persistence_requirements_loaded(self):
        """Test that persistence requirements are loaded from config."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()

        # Should have persistence requirements for each regime
        assert FlowRegime.RISK_ON in calc.persistence_requirements
        assert FlowRegime.RISK_OFF in calc.persistence_requirements
        assert FlowRegime.QUARANTINE in calc.persistence_requirements
        assert FlowRegime.DEAD in calc.persistence_requirements
        assert FlowRegime.NEUTRAL in calc.persistence_requirements

        # Neutral should have no persistence requirement (1 day = immediate)
        assert calc.persistence_requirements[FlowRegime.NEUTRAL] == 1

    def test_enable_persistence_flag(self):
        """Test that persistence feature flag is available."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()

        # Should have enable_persistence attribute
        assert hasattr(calc, 'enable_persistence')
        # Default should be False
        assert calc.enable_persistence is False


class TestApplyPersistence:
    """Test apply_persistence method."""

    def setup_method(self):
        """Set up test fixtures."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        self.calc = RegimeCalculator()
        # Enable persistence for testing
        self.calc.enable_persistence = True
        self.calc.persistence_requirements = {
            self.calc.persistence_requirements.keys().__iter__().__next__(): 2
            for _ in range(5)
        }

    def create_mock_subnet(self, current_regime="neutral", candidate=None, candidate_days=0):
        """Create a mock subnet for testing."""
        subnet = MagicMock()
        subnet.netuid = 1
        subnet.flow_regime = current_regime
        subnet.regime_candidate = candidate
        subnet.regime_candidate_days = candidate_days
        return subnet

    def test_no_transition_when_candidate_matches_current(self):
        """Test that no transition occurs when candidate matches current regime."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True

        subnet = self.create_mock_subnet(current_regime="neutral")

        final_regime, reason, did_transition = calc.apply_persistence(
            subnet, FlowRegime.NEUTRAL, "Mixed flow"
        )

        assert final_regime == FlowRegime.NEUTRAL
        assert not did_transition

    def test_transition_blocked_first_day(self):
        """Test that transition is blocked on first day of new candidate."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True
        calc.persistence_requirements[FlowRegime.RISK_OFF] = 2

        subnet = self.create_mock_subnet(
            current_regime="neutral",
            candidate=None,
            candidate_days=0
        )

        final_regime, reason, did_transition = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow"
        )

        # Should stay in neutral (persistence not met)
        assert final_regime == FlowRegime.NEUTRAL
        assert not did_transition
        # Candidate should be set
        assert subnet.regime_candidate == "risk_off"
        assert subnet.regime_candidate_days == 1

    def test_transition_blocked_second_day_needs_two(self):
        """Test that transition with 2-day requirement blocks on day 1."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True
        calc.persistence_requirements[FlowRegime.RISK_OFF] = 2

        # Subnet already has 1 day of risk_off candidate
        subnet = self.create_mock_subnet(
            current_regime="neutral",
            candidate="risk_off",
            candidate_days=1
        )

        final_regime, reason, did_transition = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow"
        )

        # Should NOW transition (2 days met)
        assert final_regime == FlowRegime.RISK_OFF
        assert did_transition
        assert "persistence" in reason.lower()

    def test_transition_allowed_after_persistence_met(self):
        """Test that transition is allowed after persistence requirement met."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True
        calc.persistence_requirements[FlowRegime.QUARANTINE] = 3

        # Subnet has 2 days of quarantine candidate
        subnet = self.create_mock_subnet(
            current_regime="risk_off",
            candidate="quarantine",
            candidate_days=2
        )

        final_regime, reason, did_transition = calc.apply_persistence(
            subnet, FlowRegime.QUARANTINE, "Severe outflow"
        )

        # Should now transition (3rd day = 3 days met)
        assert final_regime == FlowRegime.QUARANTINE
        assert did_transition

    def test_candidate_reset_on_different_regime(self):
        """Test that candidate is reset when computed regime changes."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True
        calc.persistence_requirements[FlowRegime.RISK_OFF] = 2
        calc.persistence_requirements[FlowRegime.RISK_ON] = 2

        # Subnet was trending toward risk_off for 1 day
        subnet = self.create_mock_subnet(
            current_regime="neutral",
            candidate="risk_off",
            candidate_days=1
        )

        # But today computes to risk_on instead
        final_regime, reason, did_transition = calc.apply_persistence(
            subnet, FlowRegime.RISK_ON, "Positive flow"
        )

        # Should stay in neutral, candidate reset to risk_on
        assert final_regime == FlowRegime.NEUTRAL
        assert not did_transition
        assert subnet.regime_candidate == "risk_on"
        assert subnet.regime_candidate_days == 1  # Reset to 1

    def test_persistence_disabled_allows_immediate_transition(self):
        """Test that disabling persistence allows immediate transitions."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = False  # Disabled

        subnet = self.create_mock_subnet(current_regime="neutral")

        final_regime, reason, did_transition = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow"
        )

        # Should transition immediately
        assert final_regime == FlowRegime.RISK_OFF
        assert did_transition


class TestWhipsawPrevention:
    """Test that whipsaw sequences don't cause rapid regime flipping."""

    def test_whipsaw_sequence_blocked(self):
        """Test that rapid back-and-forth regime changes are blocked."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True
        calc.persistence_requirements[FlowRegime.RISK_ON] = 2
        calc.persistence_requirements[FlowRegime.RISK_OFF] = 2

        # Start in neutral
        subnet = MagicMock()
        subnet.netuid = 1
        subnet.flow_regime = "neutral"
        subnet.regime_candidate = None
        subnet.regime_candidate_days = 0

        # Day 1: Signal says risk_off
        regime, reason, transitioned = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow day 1"
        )
        assert regime == FlowRegime.NEUTRAL  # Blocked
        assert not transitioned

        # Day 2: Signal flips to risk_on (whipsaw!)
        subnet.flow_regime = "neutral"
        subnet.regime_candidate = "risk_off"
        subnet.regime_candidate_days = 1

        regime, reason, transitioned = calc.apply_persistence(
            subnet, FlowRegime.RISK_ON, "Positive flow day 2"
        )
        assert regime == FlowRegime.NEUTRAL  # Still blocked, candidate reset
        assert not transitioned
        assert subnet.regime_candidate == "risk_on"
        assert subnet.regime_candidate_days == 1  # Reset

        # Day 3: Signal back to risk_off (another whipsaw!)
        regime, reason, transitioned = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow day 3"
        )
        assert regime == FlowRegime.NEUTRAL  # Still blocked
        assert not transitioned
        assert subnet.regime_candidate == "risk_off"
        assert subnet.regime_candidate_days == 1  # Reset again

        # Net result: Despite 3 days of signals, no transitions occurred
        # because the signal kept whipsawing

    def test_consistent_signal_eventually_transitions(self):
        """Test that consistent signal eventually causes transition."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True
        calc.persistence_requirements[FlowRegime.RISK_OFF] = 2

        subnet = MagicMock()
        subnet.netuid = 1
        subnet.flow_regime = "neutral"
        subnet.regime_candidate = None
        subnet.regime_candidate_days = 0

        # Day 1: Signal says risk_off
        regime, reason, transitioned = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow day 1"
        )
        assert regime == FlowRegime.NEUTRAL  # Blocked
        assert subnet.regime_candidate_days == 1

        # Day 2: Signal STILL says risk_off (consistent)
        subnet.flow_regime = "neutral"  # Still in neutral
        subnet.regime_candidate = "risk_off"
        subnet.regime_candidate_days = 1

        regime, reason, transitioned = calc.apply_persistence(
            subnet, FlowRegime.RISK_OFF, "Negative flow day 2"
        )
        assert regime == FlowRegime.RISK_OFF  # NOW transitions
        assert transitioned


class TestPersistenceRequirementsByRegime:
    """Test that different regimes have appropriate persistence requirements."""

    def test_dead_requires_confirmation(self):
        """Test that Dead regime requires 2 days (confirmation)."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True

        # Dead should require 2 days
        assert calc.persistence_requirements[FlowRegime.DEAD] == 2

    def test_quarantine_requires_more_days(self):
        """Test that Quarantine requires 3 days (more conservative)."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True

        # Quarantine should require 3 days
        assert calc.persistence_requirements[FlowRegime.QUARANTINE] == 3

    def test_neutral_no_persistence(self):
        """Test that Neutral has no persistence requirement."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_persistence = True

        # Neutral should be 1 (immediate)
        assert calc.persistence_requirements[FlowRegime.NEUTRAL] == 1
