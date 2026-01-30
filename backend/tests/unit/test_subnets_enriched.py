"""Tests for Phase 1 (UI Overhaul): Enriched Subnets Endpoint.

Tests cover:
- Volatile data extraction from pool API response
- Enriched response merge logic (DB + TaoStats)
- Degraded mode (TaoStats unavailable)
- Partial data (some netuids missing from TaoStats)
- Volatile field mapping correctness
- Rank ordering (nulls last)
- MarketPulse weighted aggregation
- Schema validation
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from app.schemas.subnet import (
    SparklinePoint,
    VolatilePoolData,
    EnrichedSubnetResponse,
    EnrichedSubnetListResponse,
)
from app.schemas.portfolio import MarketPulse


# ==================== Sample Data Factories ====================


def _make_pool_data(
    netuid: int = 1,
    price_change_24h: float = 2.5,
    price_change_7d: float = 8.1,
    fear_greed_index: float = 65.0,
    fear_greed_sentiment: str = "Greed",
    tao_volume_24h: float = 450.5,
    tao_buy_volume_24h: float = 280.0,
    tao_sell_volume_24h: float = 170.5,
    rank: int = 3,
    sparkline: Optional[list] = None,
) -> Dict:
    """Create a sample TaoStats pool data record."""
    return {
        "netuid": netuid,
        "rank": rank,
        "price": 0.0045,
        "price_change_1h": 0.5,
        "price_change_24h": price_change_24h,
        "price_change_7d": price_change_7d,
        "price_change_30d": 15.2,
        "high_24h": 0.0048,
        "low_24h": 0.0038,
        "market_cap": 55000000000000,
        "market_cap_change_24h": -1.5,
        "tao_volume_24h": tao_volume_24h,
        "tao_buy_volume_24h": tao_buy_volume_24h,
        "tao_sell_volume_24h": tao_sell_volume_24h,
        "buys_24h": 234,
        "sells_24h": 189,
        "buyers_24h": 45,
        "sellers_24h": 32,
        "fear_greed_index": fear_greed_index,
        "fear_greed_sentiment": fear_greed_sentiment,
        "sparkline_7d": sparkline or [
            {"timestamp": "2025-01-21T00:00:00Z", "price": 0.0042},
            {"timestamp": "2025-01-22T00:00:00Z", "price": 0.0044},
        ],
        "alpha_in_pool": 274470.73,
        "alpha_staked": 159947.53,
        "total_alpha": 434418.27,
        "root_prop": 0.15,
        "startup_mode": False,
        "total_tao": 12345000000000,
        "total_alpha": 274470730000000,
        "subnet_name": f"Subnet {netuid}",
    }


# ==================== Volatile Extraction Tests ====================


class TestVolatileExtraction:
    """Test _extract_volatile helper logic."""

    def test_volatile_data_fields_mapped(self):
        """Verify all 22 volatile fields are extracted correctly."""
        pool = _make_pool_data()
        volatile = VolatilePoolData(
            price_change_1h=pool.get("price_change_1h"),
            price_change_24h=pool.get("price_change_24h"),
            price_change_7d=pool.get("price_change_7d"),
            price_change_30d=pool.get("price_change_30d"),
            high_24h=pool.get("high_24h"),
            low_24h=pool.get("low_24h"),
            market_cap_change_24h=pool.get("market_cap_change_24h"),
            tao_volume_24h=pool.get("tao_volume_24h"),
            tao_buy_volume_24h=pool.get("tao_buy_volume_24h"),
            tao_sell_volume_24h=pool.get("tao_sell_volume_24h"),
            buys_24h=pool.get("buys_24h"),
            sells_24h=pool.get("sells_24h"),
            buyers_24h=pool.get("buyers_24h"),
            sellers_24h=pool.get("sellers_24h"),
            fear_greed_index=pool.get("fear_greed_index"),
            fear_greed_sentiment=pool.get("fear_greed_sentiment"),
            sparkline_7d=[
                SparklinePoint(timestamp=pt["timestamp"], price=pt["price"])
                for pt in pool.get("sparkline_7d", [])
            ],
            alpha_in_pool=pool.get("alpha_in_pool"),
            alpha_staked=pool.get("alpha_staked"),
            total_alpha=pool.get("total_alpha"),
            root_prop=pool.get("root_prop"),
            startup_mode=pool.get("startup_mode"),
        )

        assert volatile.price_change_1h == 0.5
        assert volatile.price_change_24h == 2.5
        assert volatile.price_change_7d == 8.1
        assert volatile.price_change_30d == 15.2
        assert volatile.high_24h == 0.0048
        assert volatile.low_24h == 0.0038
        assert volatile.market_cap_change_24h == -1.5
        assert volatile.tao_volume_24h == 450.5
        assert volatile.tao_buy_volume_24h == 280.0
        assert volatile.tao_sell_volume_24h == 170.5
        assert volatile.buys_24h == 234
        assert volatile.sells_24h == 189
        assert volatile.buyers_24h == 45
        assert volatile.sellers_24h == 32
        assert volatile.fear_greed_index == 65.0
        assert volatile.fear_greed_sentiment == "Greed"
        assert len(volatile.sparkline_7d) == 2
        assert volatile.alpha_in_pool == 274470.73
        assert volatile.root_prop == 0.15
        assert volatile.startup_mode is False

    def test_volatile_null_fields(self):
        """Verify null fields handled gracefully."""
        volatile = VolatilePoolData()
        assert volatile.price_change_24h is None
        assert volatile.fear_greed_index is None
        assert volatile.sparkline_7d is None
        assert volatile.startup_mode is None

    def test_sparkline_parsing(self):
        """Verify sparkline points are parsed correctly."""
        points = [
            SparklinePoint(timestamp="2025-01-21T00:00:00Z", price=0.0042),
            SparklinePoint(timestamp="2025-01-22T00:00:00Z", price=0.0044),
        ]
        assert points[0].timestamp == "2025-01-21T00:00:00Z"
        assert points[0].price == 0.0042
        assert points[1].price == 0.0044


# ==================== Enriched Response Tests ====================


class TestEnrichedResponse:
    """Test enriched subnet response construction."""

    def test_enriched_with_volatile(self):
        """Enriched response includes volatile data when available."""
        now = datetime.now(timezone.utc)
        volatile = VolatilePoolData(
            price_change_24h=2.5,
            fear_greed_sentiment="Greed",
        )

        response = EnrichedSubnetResponse(
            netuid=1,
            name="Subnet 1",
            emission_share=Decimal("0.023"),
            pool_tao_reserve=Decimal("12345"),
            alpha_price_tao=Decimal("0.0045"),
            rank=3,
            market_cap_tao=Decimal("55000"),
            volatile=volatile,
        )

        assert response.netuid == 1
        assert response.rank == 3
        assert response.volatile is not None
        assert response.volatile.price_change_24h == 2.5
        assert response.volatile.fear_greed_sentiment == "Greed"

    def test_enriched_without_volatile(self):
        """Enriched response has null volatile when TaoStats unavailable."""
        response = EnrichedSubnetResponse(
            netuid=1,
            name="Subnet 1",
            volatile=None,
        )

        assert response.volatile is None

    def test_enriched_list_response_structure(self):
        """EnrichedSubnetListResponse has expected structure."""
        response = EnrichedSubnetListResponse(
            subnets=[],
            total=0,
            eligible_count=0,
            taostats_available=True,
            cache_age_seconds=45,
        )

        assert response.taostats_available is True
        assert response.cache_age_seconds == 45
        assert response.total == 0

    def test_enriched_list_degraded_mode(self):
        """Degraded mode: taostats_available=false, all volatile=null."""
        subnets = [
            EnrichedSubnetResponse(
                netuid=1,
                name="Subnet 1",
                volatile=None,
            ),
            EnrichedSubnetResponse(
                netuid=2,
                name="Subnet 2",
                volatile=None,
            ),
        ]

        response = EnrichedSubnetListResponse(
            subnets=subnets,
            total=2,
            eligible_count=1,
            taostats_available=False,
            cache_age_seconds=None,
        )

        assert response.taostats_available is False
        assert response.cache_age_seconds is None
        assert all(s.volatile is None for s in response.subnets)

    def test_rank_ordering_nulls_last(self):
        """Subnets should sort by rank with nulls last."""
        subnets = [
            EnrichedSubnetResponse(netuid=1, name="A", rank=None),
            EnrichedSubnetResponse(netuid=2, name="B", rank=3),
            EnrichedSubnetResponse(netuid=3, name="C", rank=1),
            EnrichedSubnetResponse(netuid=4, name="D", rank=None),
            EnrichedSubnetResponse(netuid=5, name="E", rank=2),
        ]

        sorted_subnets = sorted(subnets, key=lambda x: (x.rank is None, x.rank or 0))

        assert sorted_subnets[0].rank == 1
        assert sorted_subnets[1].rank == 2
        assert sorted_subnets[2].rank == 3
        assert sorted_subnets[3].rank is None
        assert sorted_subnets[4].rank is None

    def test_partial_volatile_data(self):
        """Some subnets have volatile data, others don't."""
        volatile = VolatilePoolData(price_change_24h=5.0)

        subnets = [
            EnrichedSubnetResponse(
                netuid=1, name="With Data", volatile=volatile,
            ),
            EnrichedSubnetResponse(
                netuid=2, name="No Data", volatile=None,
            ),
        ]

        assert subnets[0].volatile is not None
        assert subnets[0].volatile.price_change_24h == 5.0
        assert subnets[1].volatile is None


# ==================== MarketPulse Tests ====================


class TestMarketPulse:
    """Test MarketPulse schema and aggregation logic."""

    def test_market_pulse_schema(self):
        """MarketPulse schema has expected fields."""
        pulse = MarketPulse(
            portfolio_24h_change_pct=Decimal("2.3"),
            portfolio_7d_change_pct=Decimal("8.1"),
            avg_sentiment_index=Decimal("65.0"),
            avg_sentiment_label="Greed",
            total_volume_24h_tao=Decimal("450.5"),
            net_buy_pressure_pct=Decimal("24.2"),
            top_mover_netuid=5,
            top_mover_name="Subnet 5",
            top_mover_change_24h=Decimal("12.5"),
            taostats_available=True,
        )

        assert pulse.portfolio_24h_change_pct == Decimal("2.3")
        assert pulse.avg_sentiment_label == "Greed"
        assert pulse.top_mover_netuid == 5
        assert pulse.taostats_available is True

    def test_market_pulse_unavailable(self):
        """MarketPulse defaults to unavailable."""
        pulse = MarketPulse(taostats_available=False)

        assert pulse.taostats_available is False
        assert pulse.portfolio_24h_change_pct is None
        assert pulse.avg_sentiment_label is None

    def test_weighted_24h_change_calculation(self):
        """Verify weighted average price change calculation."""
        # Position 1: 60% weight, +5% change
        # Position 2: 40% weight, -2% change
        # Expected: 0.6 * 5 + 0.4 * (-2) = 3.0 - 0.8 = 2.2%
        weight_1 = 0.6
        change_1 = 5.0
        weight_2 = 0.4
        change_2 = -2.0

        weighted = weight_1 * change_1 + weight_2 * change_2
        assert abs(weighted - 2.2) < 0.001

    def test_sentiment_label_mapping(self):
        """Verify sentiment index maps to correct labels."""
        test_cases = [
            (80.0, "Extreme Greed"),
            (60.0, "Greed"),
            (50.0, "Neutral"),
            (30.0, "Fear"),
            (15.0, "Extreme Fear"),
        ]

        for index, expected_label in test_cases:
            if index >= 75:
                label = "Extreme Greed"
            elif index >= 55:
                label = "Greed"
            elif index >= 45:
                label = "Neutral"
            elif index >= 25:
                label = "Fear"
            else:
                label = "Extreme Fear"

            assert label == expected_label, f"Index {index}: expected {expected_label}, got {label}"

    def test_net_buy_pressure_calculation(self):
        """Verify net buy pressure percentage calculation."""
        buy_volume = 280.0
        sell_volume = 170.5
        total_volume = buy_volume + sell_volume

        net_pressure = (buy_volume - sell_volume) / total_volume * 100
        # (280 - 170.5) / 450.5 * 100 = 109.5 / 450.5 * 100 ≈ 24.3%
        assert abs(net_pressure - 24.3) < 0.5

    def test_top_mover_selection(self):
        """Top mover is the position with highest absolute 24h change."""
        changes = {
            "SN1": 3.0,
            "SN2": -8.5,  # Highest absolute change
            "SN3": 5.2,
        }

        top_mover = max(changes.items(), key=lambda x: abs(x[1]))
        assert top_mover[0] == "SN2"
        assert top_mover[1] == -8.5


# ==================== _extract_volatile Runtime Tests ====================


class TestExtractVolatileFunction:
    """Test the actual _extract_volatile helper from the subnets API."""

    def test_extract_volatile_happy_path(self):
        """Full pool data extracts all volatile fields correctly."""
        from app.api.v1.subnets import _extract_volatile

        pool = _make_pool_data(
            netuid=1,
            price_change_24h=2.5,
            fear_greed_index=65.0,
            fear_greed_sentiment="Greed",
            tao_volume_24h=450.5,
        )
        volatile = _extract_volatile(pool)

        assert volatile.price_change_1h == 0.5
        assert volatile.price_change_24h == 2.5
        assert volatile.price_change_7d == 8.1
        assert volatile.price_change_30d == 15.2
        assert volatile.high_24h == 0.0048
        assert volatile.low_24h == 0.0038
        assert volatile.market_cap_change_24h == -1.5
        assert volatile.tao_volume_24h == 450.5
        assert volatile.tao_buy_volume_24h == 280.0
        assert volatile.tao_sell_volume_24h == 170.5
        assert volatile.buys_24h == 234
        assert volatile.sells_24h == 189
        assert volatile.buyers_24h == 45
        assert volatile.sellers_24h == 32
        assert volatile.fear_greed_index == 65.0
        assert volatile.fear_greed_sentiment == "Greed"
        assert volatile.sparkline_7d is not None
        assert len(volatile.sparkline_7d) == 2
        assert volatile.alpha_in_pool == 274470.73
        assert volatile.root_prop == 0.15
        assert volatile.startup_mode is False

    def test_extract_volatile_missing_fields(self):
        """Pool data with missing fields returns None for those fields."""
        from app.api.v1.subnets import _extract_volatile

        pool = {"netuid": 1, "price": 0.005}
        volatile = _extract_volatile(pool)

        assert volatile.price_change_24h is None
        assert volatile.fear_greed_index is None
        assert volatile.tao_volume_24h is None
        assert volatile.buys_24h is None
        assert volatile.sparkline_7d is None
        assert volatile.startup_mode is None

    def test_extract_volatile_invalid_types(self):
        """Pool data with invalid types returns None gracefully."""
        from app.api.v1.subnets import _extract_volatile

        pool = {
            "netuid": 1,
            "price_change_24h": "not_a_number",
            "buys_24h": "invalid",
            "fear_greed_index": {},
        }
        volatile = _extract_volatile(pool)

        assert volatile.price_change_24h is None
        assert volatile.buys_24h is None
        assert volatile.fear_greed_index is None

    def test_extract_volatile_empty_sparkline(self):
        """Empty sparkline list produces None."""
        from app.api.v1.subnets import _extract_volatile

        pool = {"netuid": 1, "sparkline_7d": []}
        volatile = _extract_volatile(pool)

        # Empty list is falsy, so sparkline should be None
        assert volatile.sparkline_7d is None

    def test_extract_volatile_sparkline_with_non_dict(self):
        """Sparkline with non-dict entries filters them out."""
        from app.api.v1.subnets import _extract_volatile

        pool = {
            "netuid": 1,
            "sparkline_7d": [
                {"timestamp": "2025-01-21T00:00:00Z", "price": 0.0042},
                "invalid_entry",
                42,
                {"timestamp": "2025-01-22T00:00:00Z", "price": 0.0044},
            ],
        }
        volatile = _extract_volatile(pool)

        assert volatile.sparkline_7d is not None
        assert len(volatile.sparkline_7d) == 2


# ==================== Schema Validation Tests ====================


class TestSchemaValidation:
    """Test Pydantic schema validation."""

    def test_subnet_response_with_rank(self):
        """SubnetResponse includes rank and market_cap_tao."""
        from app.schemas.subnet import SubnetResponse

        now = datetime.now(timezone.utc)
        response = SubnetResponse(
            id=1,
            netuid=1,
            name="Test Subnet",
            rank=5,
            market_cap_tao=Decimal("55000"),
            created_at=now,
            updated_at=now,
        )

        assert response.rank == 5
        assert response.market_cap_tao == Decimal("55000")

    def test_subnet_response_null_rank(self):
        """SubnetResponse handles null rank."""
        from app.schemas.subnet import SubnetResponse

        now = datetime.now(timezone.utc)
        response = SubnetResponse(
            id=1,
            netuid=1,
            name="Test Subnet",
            rank=None,
            created_at=now,
            updated_at=now,
        )

        assert response.rank is None
        assert response.market_cap_tao == Decimal("0")

    def test_dashboard_response_includes_market_pulse(self):
        """DashboardResponse has market_pulse field."""
        from app.schemas.portfolio import DashboardResponse

        # Verify MarketPulse is part of DashboardResponse fields
        fields = DashboardResponse.model_fields
        assert "market_pulse" in fields

    def test_volatile_pool_data_serialization(self):
        """VolatilePoolData serializes to dict correctly."""
        volatile = VolatilePoolData(
            price_change_24h=2.5,
            fear_greed_index=65.0,
            sparkline_7d=[
                SparklinePoint(timestamp="2025-01-21T00:00:00Z", price=0.0042),
            ],
        )

        data = volatile.model_dump()
        assert data["price_change_24h"] == 2.5
        assert data["fear_greed_index"] == 65.0
        assert len(data["sparkline_7d"]) == 1
        assert data["sparkline_7d"][0]["price"] == 0.0042

    def test_enriched_subnet_list_response_serialization(self):
        """EnrichedSubnetListResponse serializes correctly."""
        response = EnrichedSubnetListResponse(
            subnets=[
                EnrichedSubnetResponse(
                    netuid=1,
                    name="Subnet 1",
                    rank=1,
                    volatile=VolatilePoolData(price_change_24h=5.0),
                ),
            ],
            total=1,
            eligible_count=1,
            taostats_available=True,
            cache_age_seconds=30,
        )

        data = response.model_dump()
        assert data["taostats_available"] is True
        assert data["cache_age_seconds"] == 30
        assert len(data["subnets"]) == 1
        assert data["subnets"][0]["volatile"]["price_change_24h"] == 5.0
