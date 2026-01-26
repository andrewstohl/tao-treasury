"""Unit tests for TAO macro regime detection (Phase 2A).

Tests the portfolio-level market regime classifier that uses
aggregate signals to determine overall market conditions.
"""

import os
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

# Set required env vars before importing app modules
os.environ.setdefault("TAOSTATS_API_KEY", "test_api_key")
os.environ.setdefault("WALLET_ADDRESS", "test_wallet_address")


class TestMacroRegimeBasics:
    """Test basic macro regime detector setup."""

    def test_macro_regime_enum_values(self):
        """Test that MacroRegime enum has all expected values."""
        from app.services.strategy.macro_regime_detector import MacroRegime

        assert MacroRegime.BULL == "bull"
        assert MacroRegime.ACCUMULATION == "accumulation"
        assert MacroRegime.NEUTRAL == "neutral"
        assert MacroRegime.DISTRIBUTION == "distribution"
        assert MacroRegime.BEAR == "bear"
        assert MacroRegime.CAPITULATION == "capitulation"

    def test_detector_loads_config(self):
        """Test that detector loads thresholds from config."""
        from app.services.strategy.macro_regime_detector import MacroRegimeDetector

        detector = MacroRegimeDetector()

        # Should have all threshold attributes
        assert hasattr(detector, 'bull_flow_threshold')
        assert hasattr(detector, 'bear_flow_threshold')
        assert hasattr(detector, 'capitulation_flow_threshold')
        assert hasattr(detector, 'accumulation_drawdown_min')
        assert hasattr(detector, 'accumulation_drawdown_max')
        assert hasattr(detector, 'capitulation_drawdown')

    def test_detector_has_enabled_flag(self):
        """Test that detector has enable flag."""
        from app.services.strategy.macro_regime_detector import MacroRegimeDetector

        detector = MacroRegimeDetector()
        assert hasattr(detector, 'enabled')
        # Default should be False
        assert detector.enabled is False


class TestMacroSignals:
    """Test MacroSignals dataclass."""

    def test_macro_signals_creation(self):
        """Test creating MacroSignals with all fields."""
        from app.services.strategy.macro_regime_detector import MacroSignals

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.05"),
            aggregate_flow_14d=Decimal("0.03"),
            drawdown_from_ath=Decimal("0.08"),
            regime_distribution={"neutral": 5, "risk_on": 3},
            risk_off_pct=Decimal("0.10"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        assert signals.aggregate_flow_7d == Decimal("0.05")
        assert signals.drawdown_from_ath == Decimal("0.08")
        assert signals.total_subnets == 10


class TestCapitulationRegime:
    """Test CAPITULATION regime detection."""

    def test_capitulation_severe_drawdown_and_outflow(self):
        """Test capitulation detected with severe drawdown + outflow."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.capitulation_drawdown = Decimal("0.25")
        detector.capitulation_flow_threshold = Decimal("-0.10")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("-0.15"),  # Severe outflow
            aggregate_flow_14d=Decimal("-0.12"),
            drawdown_from_ath=Decimal("0.30"),   # Severe drawdown
            regime_distribution={"risk_off": 8, "neutral": 2},
            risk_off_pct=Decimal("0.80"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.CAPITULATION
        assert result.confidence == "high"
        assert "drawdown" in result.reason.lower()

    def test_no_capitulation_with_only_drawdown(self):
        """Test capitulation NOT detected with only drawdown (no severe outflow)."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.capitulation_drawdown = Decimal("0.25")
        detector.capitulation_flow_threshold = Decimal("-0.10")
        detector.bear_flow_threshold = Decimal("-0.03")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("-0.05"),  # Moderate outflow (not severe)
            aggregate_flow_14d=Decimal("-0.03"),
            drawdown_from_ath=Decimal("0.30"),   # Severe drawdown
            regime_distribution={"risk_off": 5, "neutral": 5},
            risk_off_pct=Decimal("0.50"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        # Should be BEAR (has outflow) but not CAPITULATION
        assert result.regime == MacroRegime.BEAR
        assert result.regime != MacroRegime.CAPITULATION


class TestBullRegime:
    """Test BULL regime detection."""

    def test_bull_strong_inflows_low_drawdown(self):
        """Test bull detected with strong inflows and low drawdown."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bull_flow_threshold = Decimal("0.03")
        detector.accumulation_drawdown_min = Decimal("0.10")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.05"),   # Strong inflow
            aggregate_flow_14d=Decimal("0.04"),  # Sustained
            drawdown_from_ath=Decimal("0.03"),   # Low drawdown
            regime_distribution={"risk_on": 7, "neutral": 3},
            risk_off_pct=Decimal("0"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.BULL
        assert result.confidence == "high"  # Both 7d and 14d strong

    def test_bull_medium_confidence(self):
        """Test bull with medium confidence when 14d not as strong."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bull_flow_threshold = Decimal("0.03")
        detector.accumulation_drawdown_min = Decimal("0.10")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.05"),   # Strong inflow
            aggregate_flow_14d=Decimal("0.01"),  # Weaker 14d
            drawdown_from_ath=Decimal("0.05"),
            regime_distribution={"risk_on": 5, "neutral": 5},
            risk_off_pct=Decimal("0"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.BULL
        assert result.confidence == "medium"

    def test_no_bull_with_high_drawdown(self):
        """Test bull NOT detected with high drawdown despite inflows."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bull_flow_threshold = Decimal("0.03")
        detector.accumulation_drawdown_min = Decimal("0.10")
        detector.accumulation_drawdown_max = Decimal("0.25")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.05"),   # Strong inflow
            aggregate_flow_14d=Decimal("0.04"),
            drawdown_from_ath=Decimal("0.15"),   # In drawdown zone
            regime_distribution={"risk_on": 5, "neutral": 5},
            risk_off_pct=Decimal("0"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        # Should be ACCUMULATION instead (in drawdown zone with positive flows)
        assert result.regime == MacroRegime.ACCUMULATION


class TestBearRegime:
    """Test BEAR regime detection."""

    def test_bear_negative_flows(self):
        """Test bear detected with negative flows."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bear_flow_threshold = Decimal("-0.03")
        detector.capitulation_drawdown = Decimal("0.25")
        detector.capitulation_flow_threshold = Decimal("-0.10")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("-0.05"),  # Negative flow
            aggregate_flow_14d=Decimal("-0.04"),
            drawdown_from_ath=Decimal("0.10"),   # Not severe
            regime_distribution={"risk_off": 6, "neutral": 4},
            risk_off_pct=Decimal("0.60"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.BEAR
        assert result.confidence == "high"

    def test_bear_from_high_risk_off_concentration(self):
        """Test bear detected from high risk-off subnet concentration."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bear_flow_threshold = Decimal("-0.03")
        detector.bull_flow_threshold = Decimal("0.03")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("-0.01"),  # Mild negative (not bear threshold)
            aggregate_flow_14d=Decimal("0"),
            drawdown_from_ath=Decimal("0.05"),
            regime_distribution={"risk_off": 4, "quarantine": 1, "neutral": 5},
            risk_off_pct=Decimal("0.50"),  # 50% in risk-off+
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.BEAR
        assert "risk-off" in result.reason.lower()


class TestAccumulationRegime:
    """Test ACCUMULATION regime detection."""

    def test_accumulation_in_drawdown_zone_with_positive_flow(self):
        """Test accumulation detected in drawdown zone with positive flows."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.accumulation_drawdown_min = Decimal("0.10")
        detector.accumulation_drawdown_max = Decimal("0.25")
        detector.bear_flow_threshold = Decimal("-0.03")
        detector.bull_flow_threshold = Decimal("0.03")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.01"),   # Mild positive
            aggregate_flow_14d=Decimal("0"),
            drawdown_from_ath=Decimal("0.15"),   # In accumulation zone
            regime_distribution={"neutral": 6, "risk_on": 2, "risk_off": 2},
            risk_off_pct=Decimal("0.20"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.ACCUMULATION
        assert "drawdown zone" in result.reason.lower()

    def test_accumulation_stabilizing_after_decline(self):
        """Test accumulation with stabilizing flows (not positive yet)."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.accumulation_drawdown_min = Decimal("0.10")
        detector.accumulation_drawdown_max = Decimal("0.25")
        detector.bear_flow_threshold = Decimal("-0.03")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("-0.01"),  # Mild negative (but not bear)
            aggregate_flow_14d=Decimal("-0.05"),
            drawdown_from_ath=Decimal("0.20"),   # In accumulation zone
            regime_distribution={"neutral": 5, "risk_off": 3, "risk_on": 2},
            risk_off_pct=Decimal("0.30"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.ACCUMULATION
        assert result.confidence == "medium"  # Flows not positive yet


class TestDistributionRegime:
    """Test DISTRIBUTION regime detection."""

    def test_distribution_near_highs_slowing_flows(self):
        """Test distribution detected near highs with decelerating flows."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bull_flow_threshold = Decimal("0.03")
        detector.bear_flow_threshold = Decimal("-0.03")
        detector.accumulation_drawdown_min = Decimal("0.10")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.01"),   # Mild positive (not bull)
            aggregate_flow_14d=Decimal("0.02"),  # 14d > 7d = decelerating
            drawdown_from_ath=Decimal("0.05"),   # Near highs
            regime_distribution={"neutral": 5, "risk_on": 3, "risk_off": 2},
            risk_off_pct=Decimal("0.20"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.DISTRIBUTION
        assert "decelerating" in result.reason.lower()


class TestNeutralRegime:
    """Test NEUTRAL regime detection."""

    def test_neutral_mixed_signals(self):
        """Test neutral returned for mixed/unclear signals."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroSignals, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = True
        detector.bull_flow_threshold = Decimal("0.03")
        detector.bear_flow_threshold = Decimal("-0.03")
        detector.accumulation_drawdown_min = Decimal("0.10")

        signals = MacroSignals(
            aggregate_flow_7d=Decimal("0.01"),   # Mild positive
            aggregate_flow_14d=Decimal("0.01"),  # Same = not decelerating
            drawdown_from_ath=Decimal("0.05"),   # Low drawdown
            regime_distribution={"neutral": 5, "risk_on": 3, "risk_off": 2},
            risk_off_pct=Decimal("0.20"),
            total_subnets=10,
            total_liquidity_tao=Decimal("100000"),
        )

        result = detector.classify_regime(signals)

        assert result.regime == MacroRegime.NEUTRAL
        assert result.confidence == "low"


class TestRegimePolicy:
    """Test policy retrieval for each regime."""

    def test_bull_policy_aggressive(self):
        """Test bull policy allows expansion and new positions."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroRegime
        )

        detector = MacroRegimeDetector()
        policy = detector.get_regime_policy(MacroRegime.BULL)

        assert policy["sleeve_target"] == "upper"
        assert policy["new_positions_allowed"] is True
        assert policy["sleeve_modifier"] == Decimal("1.0")

    def test_capitulation_policy_defensive(self):
        """Test capitulation policy is max defensive."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroRegime
        )

        detector = MacroRegimeDetector()
        policy = detector.get_regime_policy(MacroRegime.CAPITULATION)

        assert policy["sleeve_target"] == "minimum"
        assert policy["new_positions_allowed"] is False
        assert policy["sleeve_modifier"] == Decimal("0.25")
        assert policy["root_bias"] == Decimal("0.25")

    def test_all_regimes_have_policies(self):
        """Test all regimes have defined policies."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroRegime
        )

        detector = MacroRegimeDetector()

        for regime in MacroRegime:
            policy = detector.get_regime_policy(regime)
            assert "sleeve_target" in policy
            assert "sleeve_modifier" in policy
            assert "new_positions_allowed" in policy
            assert "root_bias" in policy


class TestDisabledDetector:
    """Test behavior when detector is disabled."""

    @pytest.mark.asyncio
    async def test_disabled_returns_neutral(self):
        """Test that disabled detector returns neutral."""
        from app.services.strategy.macro_regime_detector import (
            MacroRegimeDetector, MacroRegime
        )

        detector = MacroRegimeDetector()
        detector.enabled = False

        result = await detector.detect_regime()

        assert result.regime == MacroRegime.NEUTRAL
        assert "disabled" in result.reason.lower()
