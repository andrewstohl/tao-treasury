"""Unit tests for emissions collapse detection (Phase 1B).

Tests that emissions collapse detection correctly identifies:
- 30% drop -> Risk-Off
- 50% drop -> Quarantine
- Near-zero emission_share -> Dead
- Emissions override only makes regime MORE restrictive
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))


class TestEmissionsCollapseDetection:
    """Test check_emissions_collapse method."""

    def create_mock_subnet(self, emission_share=Decimal("0.01")):
        """Create a mock subnet with given emission share."""
        subnet = MagicMock()
        subnet.netuid = 1
        subnet.name = "Test Subnet"
        subnet.emission_share = emission_share
        subnet.flow_regime = "neutral"
        return subnet

    @pytest.mark.asyncio
    async def test_near_zero_emissions_detected_as_dead(self):
        """Test that near-zero emissions trigger Dead regime suggestion."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_near_zero_threshold = Decimal("0.0001")  # 0.01%

        # Near-zero emission
        subnet = self.create_mock_subnet(emission_share=Decimal("0.00005"))

        mock_db = AsyncMock()

        result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is True
        assert result.severity == "critical"
        assert result.suggested_regime == FlowRegime.DEAD
        assert "near-zero" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_30_percent_drop_triggers_risk_off(self):
        """Test that 30% emissions drop triggers Risk-Off suggestion."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_warning_threshold = Decimal("0.30")
        calc.emissions_severe_threshold = Decimal("0.50")
        calc.emissions_lookback_days = 7

        # Current emission: 0.007 (down 30% from 0.01 baseline)
        subnet = self.create_mock_subnet(emission_share=Decimal("0.007"))

        mock_db = AsyncMock()

        # Mock history with baseline of 0.01
        with patch.object(calc, 'get_emission_history') as mock_history:
            mock_history.return_value = [
                (datetime.now(timezone.utc), Decimal("0.007")),  # Most recent
                (datetime.now(timezone.utc) - timedelta(days=7), Decimal("0.01")),  # Baseline
            ]

            result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is True
        assert result.severity == "warning"
        assert result.suggested_regime == FlowRegime.RISK_OFF
        assert result.delta_pct == Decimal("-0.3")  # -30%

    @pytest.mark.asyncio
    async def test_50_percent_drop_triggers_quarantine(self):
        """Test that 50% emissions drop triggers Quarantine suggestion."""
        from app.services.strategy.regime_calculator import RegimeCalculator, FlowRegime

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_warning_threshold = Decimal("0.30")
        calc.emissions_severe_threshold = Decimal("0.50")
        calc.emissions_lookback_days = 7

        # Current emission: 0.005 (down 50% from 0.01 baseline)
        subnet = self.create_mock_subnet(emission_share=Decimal("0.005"))

        mock_db = AsyncMock()

        with patch.object(calc, 'get_emission_history') as mock_history:
            mock_history.return_value = [
                (datetime.now(timezone.utc), Decimal("0.005")),
                (datetime.now(timezone.utc) - timedelta(days=7), Decimal("0.01")),
            ]

            result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is True
        assert result.severity == "severe"
        assert result.suggested_regime == FlowRegime.QUARANTINE
        assert result.delta_pct == Decimal("-0.5")  # -50%

    @pytest.mark.asyncio
    async def test_stable_emissions_no_collapse(self):
        """Test that stable emissions don't trigger collapse."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_warning_threshold = Decimal("0.30")
        calc.emissions_severe_threshold = Decimal("0.50")
        calc.emissions_lookback_days = 7

        # Emission stable at 0.01
        subnet = self.create_mock_subnet(emission_share=Decimal("0.01"))

        mock_db = AsyncMock()

        with patch.object(calc, 'get_emission_history') as mock_history:
            mock_history.return_value = [
                (datetime.now(timezone.utc), Decimal("0.01")),
                (datetime.now(timezone.utc) - timedelta(days=7), Decimal("0.01")),
            ]

            result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is False
        assert result.severity is None
        assert result.suggested_regime is None
        assert result.delta_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_emissions_increase_no_collapse(self):
        """Test that emissions increase doesn't trigger collapse."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_lookback_days = 7

        # Emission increased from 0.01 to 0.015 (+50%)
        subnet = self.create_mock_subnet(emission_share=Decimal("0.015"))

        mock_db = AsyncMock()

        with patch.object(calc, 'get_emission_history') as mock_history:
            mock_history.return_value = [
                (datetime.now(timezone.utc), Decimal("0.015")),
                (datetime.now(timezone.utc) - timedelta(days=7), Decimal("0.01")),
            ]

            result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is False
        assert result.delta_pct == Decimal("0.5")  # +50%

    @pytest.mark.asyncio
    async def test_no_history_available(self):
        """Test handling when no emission history is available."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_near_zero_threshold = Decimal("0.0001")

        subnet = self.create_mock_subnet(emission_share=Decimal("0.01"))

        mock_db = AsyncMock()

        with patch.object(calc, 'get_emission_history') as mock_history:
            mock_history.return_value = []  # No history

            result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is False
        assert "no emission history" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_zero_baseline_handled_gracefully(self):
        """Test handling when baseline emission was zero."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True
        calc.emissions_near_zero_threshold = Decimal("0.0001")

        subnet = self.create_mock_subnet(emission_share=Decimal("0.01"))

        mock_db = AsyncMock()

        with patch.object(calc, 'get_emission_history') as mock_history:
            mock_history.return_value = [
                (datetime.now(timezone.utc), Decimal("0.01")),
                (datetime.now(timezone.utc) - timedelta(days=7), Decimal("0")),  # Zero baseline
            ]

            result = await calc.check_emissions_collapse(mock_db, subnet)

        assert result.has_collapse is False
        assert "baseline emission was zero" in result.reason.lower()


class TestEmissionsOverride:
    """Test apply_emissions_override method."""

    def test_override_makes_regime_more_restrictive(self):
        """Test that emissions override only makes regime MORE restrictive."""
        from app.services.strategy.regime_calculator import (
            RegimeCalculator, FlowRegime, EmissionsCollapseResult
        )

        calc = RegimeCalculator()

        # Flow says Risk-On, emissions says Risk-Off
        emissions_result = EmissionsCollapseResult(
            netuid=1,
            has_collapse=True,
            severity="warning",
            suggested_regime=FlowRegime.RISK_OFF,
            current_emission_share=Decimal("0.007"),
            baseline_emission_share=Decimal("0.01"),
            delta_pct=Decimal("-0.30"),
            reason="30% drop",
        )

        final_regime, final_reason, overridden = calc.apply_emissions_override(
            FlowRegime.RISK_ON, "Positive flow", emissions_result
        )

        assert final_regime == FlowRegime.RISK_OFF
        assert overridden is True
        assert "EMISSIONS OVERRIDE" in final_reason

    def test_override_does_not_make_regime_less_restrictive(self):
        """Test that emissions cannot override to LESS restrictive regime."""
        from app.services.strategy.regime_calculator import (
            RegimeCalculator, FlowRegime, EmissionsCollapseResult
        )

        calc = RegimeCalculator()

        # Flow says Quarantine, emissions only suggests Risk-Off
        emissions_result = EmissionsCollapseResult(
            netuid=1,
            has_collapse=True,
            severity="warning",
            suggested_regime=FlowRegime.RISK_OFF,  # Less severe than Quarantine
            current_emission_share=Decimal("0.007"),
            baseline_emission_share=Decimal("0.01"),
            delta_pct=Decimal("-0.30"),
            reason="30% drop",
        )

        final_regime, final_reason, overridden = calc.apply_emissions_override(
            FlowRegime.QUARANTINE, "Severe outflow", emissions_result
        )

        # Should NOT override - Quarantine is already more restrictive
        assert final_regime == FlowRegime.QUARANTINE
        assert overridden is False
        assert "EMISSIONS OVERRIDE" not in final_reason

    def test_no_override_when_no_collapse(self):
        """Test that no override happens when no emissions collapse."""
        from app.services.strategy.regime_calculator import (
            RegimeCalculator, FlowRegime, EmissionsCollapseResult
        )

        calc = RegimeCalculator()

        emissions_result = EmissionsCollapseResult(
            netuid=1,
            has_collapse=False,
            severity=None,
            suggested_regime=None,
            current_emission_share=Decimal("0.01"),
            baseline_emission_share=Decimal("0.01"),
            delta_pct=Decimal("0"),
            reason="Stable",
        )

        final_regime, final_reason, overridden = calc.apply_emissions_override(
            FlowRegime.RISK_ON, "Positive flow", emissions_result
        )

        assert final_regime == FlowRegime.RISK_ON
        assert overridden is False

    def test_severity_hierarchy_respected(self):
        """Test that severity hierarchy is correctly applied."""
        from app.services.strategy.regime_calculator import (
            RegimeCalculator, FlowRegime, EmissionsCollapseResult
        )

        calc = RegimeCalculator()

        # Test each combination to verify hierarchy:
        # RISK_ON < NEUTRAL < RISK_OFF < QUARANTINE < DEAD

        test_cases = [
            # (flow_regime, suggested_regime, should_override)
            (FlowRegime.RISK_ON, FlowRegime.NEUTRAL, True),
            (FlowRegime.RISK_ON, FlowRegime.RISK_OFF, True),
            (FlowRegime.RISK_ON, FlowRegime.QUARANTINE, True),
            (FlowRegime.RISK_ON, FlowRegime.DEAD, True),
            (FlowRegime.NEUTRAL, FlowRegime.RISK_ON, False),  # Less restrictive
            (FlowRegime.NEUTRAL, FlowRegime.RISK_OFF, True),
            (FlowRegime.RISK_OFF, FlowRegime.QUARANTINE, True),
            (FlowRegime.QUARANTINE, FlowRegime.RISK_OFF, False),  # Less restrictive
            (FlowRegime.DEAD, FlowRegime.QUARANTINE, False),  # Less restrictive
        ]

        for flow_regime, suggested, should_override in test_cases:
            emissions_result = EmissionsCollapseResult(
                netuid=1,
                has_collapse=True,
                severity="test",
                suggested_regime=suggested,
                current_emission_share=Decimal("0.005"),
                baseline_emission_share=Decimal("0.01"),
                delta_pct=Decimal("-0.50"),
                reason="Test",
            )

            _, _, overridden = calc.apply_emissions_override(
                flow_regime, "Test", emissions_result
            )

            assert overridden == should_override, \
                f"Expected override={should_override} for {flow_regime} -> {suggested}"


class TestEmissionsCollapseConfig:
    """Test emissions collapse configuration loading."""

    def test_default_thresholds_loaded(self):
        """Test that default thresholds are loaded from config."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()

        # Should have emissions collapse settings
        assert hasattr(calc, 'enable_emissions_collapse')
        assert hasattr(calc, 'emissions_warning_threshold')
        assert hasattr(calc, 'emissions_severe_threshold')
        assert hasattr(calc, 'emissions_near_zero_threshold')
        assert hasattr(calc, 'emissions_lookback_days')

        # Check default values from config
        assert calc.emissions_warning_threshold == Decimal("0.30")  # 30%
        assert calc.emissions_severe_threshold == Decimal("0.50")  # 50%
        assert calc.emissions_near_zero_threshold == Decimal("0.0001")  # 0.01%
        assert calc.emissions_lookback_days == 7

    def test_feature_flag_default_off(self):
        """Test that emissions collapse feature flag defaults to off."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()

        # Feature should be disabled by default
        assert calc.enable_emissions_collapse is False


class TestGetEmissionHistory:
    """Test get_emission_history method."""

    @pytest.mark.asyncio
    async def test_queries_subnet_snapshots(self):
        """Test that emission history queries SubnetSnapshot table."""
        from app.services.strategy.regime_calculator import RegimeCalculator

        calc = RegimeCalculator()
        calc.emissions_lookback_days = 7

        mock_db = AsyncMock()

        # Mock the query result
        mock_row1 = MagicMock()
        mock_row1.timestamp = datetime.now(timezone.utc)
        mock_row1.emission_share = Decimal("0.01")

        mock_row2 = MagicMock()
        mock_row2.timestamp = datetime.now(timezone.utc) - timedelta(days=7)
        mock_row2.emission_share = Decimal("0.012")

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row1, mock_row2]
        mock_db.execute.return_value = mock_result

        history = await calc.get_emission_history(mock_db, netuid=1)

        # Verify query was executed
        mock_db.execute.assert_called_once()

        # Verify results
        assert len(history) == 2
        assert history[0][1] == Decimal("0.01")  # Most recent
        assert history[1][1] == Decimal("0.012")  # Baseline


class TestUpdateAllRegimesWithEmissions:
    """Test update_all_regimes integration with emissions collapse."""

    @pytest.mark.asyncio
    async def test_emissions_collapse_tracked_in_results(self):
        """Test that emissions collapses are tracked in update results."""
        from app.services.strategy.regime_calculator import (
            RegimeCalculator, FlowRegime, EmissionsCollapseResult
        )

        calc = RegimeCalculator()
        calc.enable_emissions_collapse = True

        # Mock the subnet with collapse
        mock_subnet = MagicMock()
        mock_subnet.netuid = 1
        mock_subnet.name = "Collapsing Subnet"
        mock_subnet.emission_share = Decimal("0.005")
        mock_subnet.flow_regime = "neutral"
        mock_subnet.regime_candidate = None
        mock_subnet.regime_candidate_days = 0
        mock_subnet.flow_regime_since = datetime.now(timezone.utc)
        mock_subnet.taoflow_1d = Decimal("0.01")
        mock_subnet.taoflow_3d = Decimal("0.01")
        mock_subnet.taoflow_7d = Decimal("0.01")
        mock_subnet.taoflow_14d = Decimal("0.01")

        # Mock emissions collapse detection
        collapse_result = EmissionsCollapseResult(
            netuid=1,
            has_collapse=True,
            severity="severe",
            suggested_regime=FlowRegime.QUARANTINE,
            current_emission_share=Decimal("0.005"),
            baseline_emission_share=Decimal("0.01"),
            delta_pct=Decimal("-0.50"),
            reason="50% emissions drop",
        )

        with patch('app.services.strategy.regime_calculator.get_db_context') as mock_ctx:
            mock_db = AsyncMock()
            mock_ctx.return_value.__aenter__.return_value = mock_db

            # Mock subnet query
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_subnet]
            mock_db.execute.return_value = mock_result

            # Mock emissions collapse check and compute_portfolio_regime
            # (compute_portfolio_regime makes additional DB queries that need separate mocking)
            with patch.object(calc, 'check_emissions_collapse', return_value=collapse_result):
                with patch.object(calc, 'compute_portfolio_regime',
                                  return_value=(FlowRegime.NEUTRAL, "Mocked", {"neutral": 1})):
                    results = await calc.update_all_regimes()

        # Verify emissions tracking in results
        assert results["emissions_collapse_enabled"] is True
        assert results["emissions_overrides"] >= 0
        assert "emissions_collapses" in results
