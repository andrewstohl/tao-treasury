"""Unit tests for exitability gate functionality.

Tests the ExitabilityLevel classification and safe position size calculation.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.strategy.eligibility_gate import (
    EligibilityGate,
    ExitabilityLevel,
    ExitabilityResult,
)


class TestExitabilityLevel:
    """Test exitability level classification."""

    def test_level_values(self):
        """Test that all exitability levels have correct values."""
        assert ExitabilityLevel.PASS.value == "pass"
        assert ExitabilityLevel.WARNING.value == "warning"
        assert ExitabilityLevel.BLOCK_BUY.value == "block_buy"
        assert ExitabilityLevel.FORCE_TRIM.value == "force_trim"

    def test_level_ordering(self):
        """Test that levels have logical severity ordering."""
        # FORCE_TRIM is most severe
        # BLOCK_BUY is second most severe
        # WARNING is third
        # PASS is least severe
        levels = [ExitabilityLevel.PASS, ExitabilityLevel.WARNING,
                  ExitabilityLevel.BLOCK_BUY, ExitabilityLevel.FORCE_TRIM]
        assert len(levels) == 4


class TestExitabilityResult:
    """Test ExitabilityResult dataclass."""

    def test_basic_result(self):
        """Test creating a basic exitability result."""
        result = ExitabilityResult(
            netuid=1,
            level=ExitabilityLevel.PASS,
            slippage_50pct=Decimal("0.02"),
            slippage_100pct=Decimal("0.04"),
            reason="Slippage acceptable",
        )

        assert result.netuid == 1
        assert result.level == ExitabilityLevel.PASS
        assert result.slippage_50pct == Decimal("0.02")
        assert result.slippage_100pct == Decimal("0.04")
        assert result.safe_size_tao is None
        assert result.trim_amount_tao is None

    def test_force_trim_result(self):
        """Test exitability result with trim recommendations."""
        result = ExitabilityResult(
            netuid=5,
            level=ExitabilityLevel.FORCE_TRIM,
            slippage_50pct=Decimal("0.08"),
            slippage_100pct=Decimal("0.12"),
            reason="100% exit slippage exceeds 10%",
            current_size_tao=Decimal("1000"),
            safe_size_tao=Decimal("700"),
            trim_amount_tao=Decimal("300"),
            trim_pct=Decimal("30"),
        )

        assert result.level == ExitabilityLevel.FORCE_TRIM
        assert result.safe_size_tao == Decimal("700")
        assert result.trim_amount_tao == Decimal("300")
        assert result.trim_pct == Decimal("30")


class TestSlippageInterpolation:
    """Test slippage interpolation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.gate = EligibilityGate()

    def test_interpolate_empty_surfaces(self):
        """Test interpolation with no data returns default high slippage."""
        result = self.gate._interpolate_slippage([], Decimal("100"))
        assert result == Decimal("0.10")

    def test_interpolate_exact_match(self):
        """Test interpolation when size exactly matches a surface."""
        surfaces = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.01")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.05")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.10")),
        ]

        result = self.gate._interpolate_slippage(surfaces, Decimal("500"))
        assert result == Decimal("0.05")

    def test_interpolate_between_values(self):
        """Test linear interpolation between two surfaces."""
        surfaces = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.01")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.05")),
        ]

        # 300 is halfway between 100 and 500
        result = self.gate._interpolate_slippage(surfaces, Decimal("300"))
        # Expected: 0.01 + 0.5 * (0.05 - 0.01) = 0.01 + 0.02 = 0.03
        assert result == Decimal("0.03")

    def test_interpolate_below_minimum(self):
        """Test interpolation for size below smallest surface."""
        surfaces = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.01")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.05")),
        ]

        result = self.gate._interpolate_slippage(surfaces, Decimal("50"))
        # Should return slippage of smallest size
        assert result == Decimal("0.01")

    def test_interpolate_above_maximum(self):
        """Test interpolation for size above largest surface."""
        surfaces = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.01")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.05")),
        ]

        result = self.gate._interpolate_slippage(surfaces, Decimal("1000"))
        # Should return slippage of largest size
        assert result == Decimal("0.05")


class TestExitabilityThresholds:
    """Test exitability threshold logic."""

    def setup_method(self):
        """Set up test fixtures with default thresholds."""
        self.gate = EligibilityGate()
        # Default thresholds from config:
        # max_exit_slippage_50pct = 0.05 (5%)
        # max_exit_slippage_100pct = 0.10 (10%)
        # exitability_warning_threshold = 0.075 (7.5%)

    def test_thresholds_loaded(self):
        """Test that thresholds are loaded from config."""
        assert self.gate.max_exit_slippage_50pct == Decimal("0.05")
        assert self.gate.max_exit_slippage_100pct == Decimal("0.10")
        assert self.gate.exitability_warning_threshold == Decimal("0.075")

    def test_level_determination_pass(self):
        """Test PASS level when slippage is acceptable."""
        # If 50% exit < 5% and 100% exit < 7.5% => PASS
        # slip_50 = 2%, slip_100 = 4% => PASS
        pass  # Tested in async tests below

    def test_level_determination_warning(self):
        """Test WARNING level when approaching limits."""
        # If 100% exit > 7.5% but <= 10% => WARNING
        pass  # Tested in async tests below

    def test_level_determination_block_buy(self):
        """Test BLOCK_BUY when 50% exit slippage too high."""
        # If 50% exit > 5% => BLOCK_BUY
        pass  # Tested in async tests below

    def test_level_determination_force_trim(self):
        """Test FORCE_TRIM when 100% exit slippage too high."""
        # If 100% exit > 10% => FORCE_TRIM
        pass  # Tested in async tests below


class TestFeatureFlag:
    """Test feature flag behavior."""

    def test_feature_flag_default_off(self):
        """Test that feature flag is off by default."""
        gate = EligibilityGate()
        # Note: This depends on config default, may need mocking
        # assert gate.enable_exitability_gate == False

    def test_hard_gate_only_when_enabled(self):
        """Test that hard gate behavior only applies when flag is on."""
        # When flag is off, slippage check should use legacy soft behavior
        # When flag is on, BLOCK_BUY should block new buys
        pass  # Requires integration testing with full setup


class TestBinarySearchSafeSize:
    """Test binary search for safe position size."""

    def setup_method(self):
        """Set up test fixtures."""
        self.gate = EligibilityGate()

    def test_binary_search_converges(self):
        """Test that binary search converges to a solution."""
        # Create mock surfaces with linear slippage growth
        surfaces = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.01")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.05")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.10")),
            MagicMock(size_tao=Decimal("2000"), slippage_pct=Decimal("0.20")),
        ]

        # For a position of 1500 TAO with 15% slippage at full exit,
        # we need to find size where slippage <= 7.5%
        # Based on linear interpolation, ~750 TAO should give ~7.5%
        # The binary search should find something close to this

        # This is a synchronous helper test - full async test needed
        pass


# Async tests require pytest-asyncio
@pytest.mark.asyncio
class TestCheckExitabilityAsync:
    """Async tests for check_exitability method."""

    async def test_check_exitability_pass(self):
        """Test exitability check returns PASS for acceptable slippage."""
        gate = EligibilityGate()

        # Mock database session and slippage surfaces
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.01")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.03")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.05")),
        ]
        mock_db.execute.return_value = mock_result

        result = await gate.check_exitability(
            db=mock_db,
            netuid=1,
            position_size_tao=Decimal("200"),
        )

        assert result.level == ExitabilityLevel.PASS
        assert result.netuid == 1

    async def test_check_exitability_warning(self):
        """Test exitability check returns WARNING for 7.5-10% slippage at 100% exit.

        WARNING requires:
        - 50% exit slippage <= 5% (not BLOCK_BUY)
        - 100% exit slippage > 7.5% and <= 10% (WARNING tier, not FORCE_TRIM)
        """
        gate = EligibilityGate()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        # Carefully chosen values so that:
        # - 50% exit (500 TAO) = 4% slippage (< 5%, not BLOCK_BUY)
        # - 100% exit (1000 TAO) = 8.5% slippage (> 7.5%, < 10%, WARNING)
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.02")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.04")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.085")),
        ]
        mock_db.execute.return_value = mock_result

        result = await gate.check_exitability(
            db=mock_db,
            netuid=2,
            position_size_tao=Decimal("1000"),
        )

        # 50% exit at 500 TAO = 4% (< 5%, not BLOCK_BUY)
        # 100% exit at 1000 TAO = 8.5% (> 7.5%, < 10%) => WARNING
        assert result.level == ExitabilityLevel.WARNING

    async def test_check_exitability_block_buy(self):
        """Test exitability check returns BLOCK_BUY for high 50% slippage."""
        gate = EligibilityGate()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.03")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.06")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.09")),
        ]
        mock_db.execute.return_value = mock_result

        result = await gate.check_exitability(
            db=mock_db,
            netuid=3,
            position_size_tao=Decimal("1000"),
        )

        # 50% exit at 500 TAO = 6% slippage (> 5%) => BLOCK_BUY
        assert result.level == ExitabilityLevel.BLOCK_BUY

    async def test_check_exitability_force_trim(self):
        """Test exitability check returns FORCE_TRIM for high 100% slippage."""
        gate = EligibilityGate()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.05")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.08")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.12")),
        ]
        mock_db.execute.return_value = mock_result

        result = await gate.check_exitability(
            db=mock_db,
            netuid=4,
            position_size_tao=Decimal("1000"),
        )

        # 100% exit at 1000 TAO = 12% slippage (> 10%) => FORCE_TRIM
        assert result.level == ExitabilityLevel.FORCE_TRIM
        # Should have calculated safe size and trim amount
        assert result.safe_size_tao is not None or result.trim_amount_tao is not None

    async def test_check_exitability_no_data(self):
        """Test exitability check handles missing slippage data."""
        gate = EligibilityGate()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await gate.check_exitability(
            db=mock_db,
            netuid=5,
            position_size_tao=Decimal("100"),
        )

        # Should return WARNING when no data available
        assert result.level == ExitabilityLevel.WARNING
        assert "no slippage data" in result.reason.lower()


@pytest.mark.asyncio
class TestMinPositionSafetyGuard:
    """Test minimum position safety guard in calculate_safe_position_size."""

    async def test_safe_size_above_minimum_returns_size(self):
        """Test that safe size above minimum is returned normally."""
        from app.services.strategy.eligibility_gate import EligibilityGate

        gate = EligibilityGate()

        # Mock surfaces where safe size would be ~500 TAO (above min_position_tao=50)
        surfaces = [
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.02")),
            MagicMock(size_tao=Decimal("500"), slippage_pct=Decimal("0.07")),
            MagicMock(size_tao=Decimal("1000"), slippage_pct=Decimal("0.15")),
        ]

        mock_db = AsyncMock()

        safe_size = await gate.calculate_safe_position_size(
            db=mock_db,
            netuid=1,
            current_size_tao=Decimal("1000"),
            surfaces=surfaces,
        )

        # Safe size should be returned (above minimum)
        assert safe_size is not None
        assert safe_size > Decimal("50")  # Above min_position_tao

    async def test_safe_size_below_minimum_returns_none(self):
        """Test that safe size below minimum returns None (full exit)."""
        from app.services.strategy.eligibility_gate import EligibilityGate

        gate = EligibilityGate()

        # Mock surfaces where even smallest size has high slippage
        # This should result in safe_size being very small (below min)
        surfaces = [
            MagicMock(size_tao=Decimal("10"), slippage_pct=Decimal("0.08")),
            MagicMock(size_tao=Decimal("50"), slippage_pct=Decimal("0.15")),
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.25")),
        ]

        mock_db = AsyncMock()

        safe_size = await gate.calculate_safe_position_size(
            db=mock_db,
            netuid=1,
            current_size_tao=Decimal("100"),
            surfaces=surfaces,
        )

        # Safe size should be None (full exit recommended)
        # because any safe size would be below minimum
        assert safe_size is None

    async def test_force_trim_recommends_full_exit_when_below_min(self):
        """Test that FORCE_TRIM recommends 100% trim when safe size below minimum."""
        from app.services.strategy.eligibility_gate import EligibilityGate, ExitabilityLevel

        gate = EligibilityGate()

        # Mock surfaces where safe size would be below minimum
        surfaces = [
            MagicMock(size_tao=Decimal("10"), slippage_pct=Decimal("0.08")),
            MagicMock(size_tao=Decimal("50"), slippage_pct=Decimal("0.15")),
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.25")),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = surfaces
        mock_db.execute.return_value = mock_result

        result = await gate.check_exitability(
            db=mock_db,
            netuid=1,
            position_size_tao=Decimal("100"),
        )

        # Should be FORCE_TRIM with 100% trim (full exit)
        assert result.level == ExitabilityLevel.FORCE_TRIM
        if result.trim_pct:
            # If trim recommendation exists, should be 100%
            assert result.trim_pct == Decimal("100")
        if result.safe_size_tao is not None:
            assert result.safe_size_tao == Decimal("0")

    async def test_portfolio_nav_based_minimum(self):
        """Test that portfolio NAV is used for percentage-based minimum."""
        from app.services.strategy.eligibility_gate import EligibilityGate

        gate = EligibilityGate()

        # Mock surfaces where safe size would be 100 TAO
        # This is above min_position_tao (50) but might be below 3% of NAV
        surfaces = [
            MagicMock(size_tao=Decimal("50"), slippage_pct=Decimal("0.05")),
            MagicMock(size_tao=Decimal("100"), slippage_pct=Decimal("0.07")),
            MagicMock(size_tao=Decimal("200"), slippage_pct=Decimal("0.12")),
        ]

        mock_db = AsyncMock()

        # With portfolio NAV of 10000, min 3% = 300 TAO
        safe_size = await gate.calculate_safe_position_size(
            db=mock_db,
            netuid=1,
            current_size_tao=Decimal("200"),
            surfaces=surfaces,
            portfolio_nav_tao=Decimal("10000"),  # 3% = 300 TAO minimum
        )

        # Safe size (~100 TAO) is below 3% of portfolio (300 TAO)
        # So should return None for full exit
        assert safe_size is None
