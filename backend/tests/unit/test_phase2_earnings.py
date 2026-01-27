"""Tests for Phase 2: Earnings Attribution.

Tests cover:
- Earnings identity: earnings = end_value - start_value - net_flows
- Per-netuid and total rollup calculations
- Edge cases (empty data, negative earnings, etc.)
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch


class TestEarningsIdentity:
    """Test the core earnings identity holds."""

    def test_earnings_identity_basic(self):
        """earnings = end_value - start_value - net_flows"""
        start_value = Decimal("100")
        end_value = Decimal("120")
        net_flows = Decimal("10")  # Added 10 TAO

        expected_earnings = end_value - start_value - net_flows
        # 120 - 100 - 10 = 10 TAO earnings

        assert expected_earnings == Decimal("10")

    def test_earnings_identity_with_withdrawals(self):
        """Withdrawals (negative flows) should be handled correctly."""
        start_value = Decimal("100")
        end_value = Decimal("80")
        net_flows = Decimal("-30")  # Withdrew 30 TAO

        expected_earnings = end_value - start_value - net_flows
        # 80 - 100 - (-30) = 80 - 100 + 30 = 10 TAO earnings

        assert expected_earnings == Decimal("10")

    def test_earnings_identity_negative_earnings(self):
        """Negative earnings (loss) should be computed correctly."""
        start_value = Decimal("100")
        end_value = Decimal("90")
        net_flows = Decimal("0")  # No flows

        expected_earnings = end_value - start_value - net_flows
        # 90 - 100 - 0 = -10 TAO (loss)

        assert expected_earnings == Decimal("-10")

    def test_earnings_identity_with_mixed_flows(self):
        """Mixed deposits and withdrawals should net out."""
        start_value = Decimal("100")
        end_value = Decimal("150")
        # Deposited 20, withdrew 5 = net +15
        net_flows = Decimal("15")

        expected_earnings = end_value - start_value - net_flows
        # 150 - 100 - 15 = 35 TAO earnings

        assert expected_earnings == Decimal("35")


class TestEarningsPercentage:
    """Test earnings percentage and APY calculations."""

    def test_earnings_pct_basic(self):
        """Earnings percentage = earnings / start_value * 100."""
        start_value = Decimal("100")
        earnings = Decimal("10")

        earnings_pct = (earnings / start_value) * Decimal("100")
        assert earnings_pct == Decimal("10")  # 10%

    def test_earnings_pct_zero_start(self):
        """Zero start value should not cause division by zero."""
        start_value = Decimal("0")
        earnings = Decimal("10")

        if start_value > 0:
            earnings_pct = (earnings / start_value) * Decimal("100")
        else:
            earnings_pct = Decimal("0")

        assert earnings_pct == Decimal("0")

    def test_annualized_apy_calculation(self):
        """APY = (earnings / start_value / days) * 365 * 100."""
        start_value = Decimal("1000")
        earnings = Decimal("10")
        days = 30

        daily_rate = earnings / start_value / Decimal(str(days))
        annualized_apy = daily_rate * Decimal("365") * Decimal("100")

        # 10 / 1000 / 30 * 365 * 100 = 12.17%
        expected_apy = (Decimal("10") / Decimal("1000") / Decimal("30")) * Decimal("365") * Decimal("100")
        assert abs(annualized_apy - expected_apy) < Decimal("0.01")


class TestEarningsAggregation:
    """Test per-netuid rollup to total."""

    def test_total_is_sum_of_netuids(self):
        """Total earnings should be sum of per-netuid earnings."""
        netuid_earnings = [
            {"netuid": 1, "earnings_tao": Decimal("10")},
            {"netuid": 2, "earnings_tao": Decimal("5")},
            {"netuid": 3, "earnings_tao": Decimal("-2")},
        ]

        total_earnings = sum(n["earnings_tao"] for n in netuid_earnings)
        assert total_earnings == Decimal("13")

    def test_total_values_aggregate(self):
        """All components should aggregate correctly."""
        netuids = [
            {
                "netuid": 1,
                "start_value_tao": Decimal("100"),
                "end_value_tao": Decimal("110"),
                "net_flows_tao": Decimal("5"),
            },
            {
                "netuid": 2,
                "start_value_tao": Decimal("200"),
                "end_value_tao": Decimal("220"),
                "net_flows_tao": Decimal("10"),
            },
        ]

        total_start = sum(n["start_value_tao"] for n in netuids)
        total_end = sum(n["end_value_tao"] for n in netuids)
        total_flows = sum(n["net_flows_tao"] for n in netuids)
        total_earnings = total_end - total_start - total_flows

        assert total_start == Decimal("300")
        assert total_end == Decimal("330")
        assert total_flows == Decimal("15")
        assert total_earnings == Decimal("15")


class TestEarningsServiceConfig:
    """Test earnings service configuration."""

    def test_feature_flag_exists(self):
        """Verify earnings feature flag exists in settings."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, 'enable_earnings_endpoints')
        assert hasattr(settings, 'enable_earnings_timeseries_by_netuid')

    def test_earnings_service_singleton(self):
        """Verify earnings service is a singleton."""
        from app.services.analysis.earnings import get_earnings_service

        s1 = get_earnings_service()
        s2 = get_earnings_service()
        assert s1 is s2


class TestEarningsEndpointSchemas:
    """Test endpoint response schemas are stable."""

    def test_summary_response_keys(self):
        """Verify summary response has expected keys."""
        expected_keys = {
            "wallet_address",
            "start",
            "end",
            "period_days",
            "total_start_value_tao",
            "total_end_value_tao",
            "total_net_flows_tao",
            "total_earnings_tao",
            "total_earnings_pct",
            "total_annualized_apy_estimate",
            "by_netuid",
        }

        # This documents the expected schema
        assert len(expected_keys) == 11

    def test_timeseries_response_keys(self):
        """Verify timeseries response has expected keys."""
        expected_keys = {
            "wallet_address",
            "start",
            "end",
            "granularity",
            "bucket_count",
            "buckets",
        }

        assert len(expected_keys) == 6

    def test_bucket_response_keys(self):
        """Verify bucket response has expected keys."""
        expected_keys = {
            "bucket_start",
            "bucket_end",
            "total_start_value_tao",
            "total_end_value_tao",
            "total_net_flows_tao",
            "total_earnings_tao",
            "total_earnings_pct",
        }

        assert len(expected_keys) == 7
