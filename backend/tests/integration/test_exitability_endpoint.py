"""Integration tests for /exitability endpoint.

Tests the actual FastAPI endpoint with proper dependency injection.
Uses an in-memory SQLite database with seeded rows - no patching of internals.
Only stubs external TaoStats calls if needed.
"""

import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest
from decimal import Decimal
from typing import AsyncGenerator

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.models.position import Position
from app.models.subnet import Subnet
from app.models.slippage import SlippageSurface


# Create in-memory SQLite engine for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Only create tables needed for exitability tests
    # (avoid creating all tables which includes PostgreSQL-specific JSONB columns)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Position.__table__,
                    Subnet.__table__,
                    SlippageSurface.__table__,
                ]
            )
        )

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
async def app_with_test_db(test_session):
    """Create app with test database override."""
    from app.main import app

    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


async def seed_test_data(
    session: AsyncSession,
    positions: list[dict],
    subnets: list[dict],
    slippage_surfaces: list[dict],
):
    """Seed test data into the database.

    Args:
        session: Database session
        positions: List of position dicts with keys: netuid, tao_value_mid, wallet_address
        subnets: List of subnet dicts with keys: netuid, name
        slippage_surfaces: List of slippage dicts with keys: netuid, action, size_tao, slippage_pct
    """
    from sqlalchemy import text

    # Use raw SQL inserts to avoid SQLite autoincrement issues with BigInteger
    # Seed subnets first (positions reference them)
    for i, subnet_data in enumerate(subnets, start=1):
        await session.execute(
            text("""
                INSERT INTO subnets (
                    id, netuid, name, pool_tao_reserve, pool_alpha_reserve, is_eligible,
                    owner_take, age_days, emission_share, total_stake_tao, alpha_price_tao,
                    holder_count, taoflow_1d, taoflow_3d, taoflow_7d, taoflow_14d,
                    flow_regime, flow_regime_days, regime_candidate_days, validator_apy
                )
                VALUES (
                    :id, :netuid, :name, :pool_tao_reserve, :pool_alpha_reserve, :is_eligible,
                    0, 90, 0.01, 10000, 1.0,
                    100, 0, 0, 0, 0,
                    'neutral', 0, 0, 0.1
                )
            """),
            {
                "id": i,
                "netuid": subnet_data["netuid"],
                "name": subnet_data["name"],
                "pool_tao_reserve": float(subnet_data.get("pool_tao_reserve", Decimal("10000"))),
                "pool_alpha_reserve": float(subnet_data.get("pool_alpha_reserve", Decimal("1000000"))),
                "is_eligible": subnet_data.get("is_eligible", True),
            }
        )

    # Seed positions
    for i, pos_data in enumerate(positions, start=1):
        await session.execute(
            text("""
                INSERT INTO positions (
                    id, wallet_address, netuid, tao_value_mid, alpha_balance,
                    tao_value_exec_50pct, tao_value_exec_100pct, entry_price_tao, cost_basis_tao,
                    realized_pnl_tao, unrealized_pnl_tao, unrealized_pnl_pct,
                    current_apy, apy_30d_avg, daily_yield_tao, weekly_yield_tao,
                    exit_slippage_50pct, exit_slippage_100pct
                )
                VALUES (
                    :id, :wallet_address, :netuid, :tao_value_mid, :alpha_balance,
                    :tao_value_mid, :tao_value_mid, 1.0, :tao_value_mid,
                    0, 0, 0,
                    0.1, 0.1, 0, 0,
                    0.02, 0.03
                )
            """),
            {
                "id": i,
                "wallet_address": pos_data.get("wallet_address", "test_wallet_address"),
                "netuid": pos_data["netuid"],
                "tao_value_mid": float(pos_data["tao_value_mid"]),
                "alpha_balance": float(pos_data.get("alpha_balance", Decimal("0"))),
            }
        )

    # Seed slippage surfaces
    for i, slip_data in enumerate(slippage_surfaces, start=1):
        await session.execute(
            text("""
                INSERT INTO slippage_surfaces (
                    id, netuid, action, size_tao, slippage_pct,
                    expected_output, pool_tao_reserve, pool_alpha_reserve
                )
                VALUES (
                    :id, :netuid, :action, :size_tao, :slippage_pct,
                    0, 10000, 1000000
                )
            """),
            {
                "id": i,
                "netuid": slip_data["netuid"],
                "action": slip_data.get("action", "unstake"),
                "size_tao": float(slip_data["size_tao"]),
                "slippage_pct": float(slip_data["slippage_pct"]),
            }
        )

    await session.commit()


class TestExitabilityEndpointIntegration:
    """Integration tests hitting /api/v1/strategy/exitability with real DI."""

    @pytest.mark.asyncio
    async def test_endpoint_with_passing_positions(self, test_session, app_with_test_db):
        """Test endpoint returns PASS for positions with acceptable slippage."""
        # Seed data with low slippage (PASS level)
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 1, "tao_value_mid": Decimal("1000")},
            ],
            subnets=[
                {"netuid": 1, "name": "Test Subnet Alpha"},
            ],
            slippage_surfaces=[
                {"netuid": 1, "size_tao": Decimal("100"), "slippage_pct": Decimal("0.01")},
                {"netuid": 1, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.02")},
                {"netuid": 1, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.03")},
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Assert required schema fields
        assert "feature_enabled" in data
        assert "total_positions" in data
        assert "warnings_count" in data
        assert "force_trims_count" in data
        assert "total_trim_tao" in data
        assert "positions" in data
        assert "warnings" in data
        assert "force_trims" in data

        # Assert counts
        assert data["total_positions"] == 1
        assert data["warnings_count"] == 0
        assert data["force_trims_count"] == 0
        assert data["total_trim_tao"] == 0.0

        # Assert representative position entry
        assert len(data["positions"]) == 1
        pos = data["positions"][0]
        assert pos["netuid"] == 1
        assert pos["subnet_name"] == "Test Subnet Alpha"
        assert pos["level"] == "pass"
        assert "slippage_50pct" in pos
        assert "slippage_100pct" in pos
        assert "current_size_tao" in pos
        assert "reason" in pos

    @pytest.mark.asyncio
    async def test_endpoint_with_warning_positions(self, test_session, app_with_test_db):
        """Test endpoint correctly identifies WARNING level positions.

        WARNING requires:
        - 50% exit slippage <= 5% (not BLOCK_BUY)
        - 100% exit slippage > 7.5% and <= 10% (WARNING tier)
        """
        # Seed data with WARNING slippage
        # Position size = 1000 TAO
        # 50% exit = 500 TAO -> 4% (< 5%, not BLOCK_BUY)
        # 100% exit = 1000 TAO -> 8.5% (> 7.5%, < 10%, WARNING)
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 2, "tao_value_mid": Decimal("1000")},
            ],
            subnets=[
                {"netuid": 2, "name": "Warning Subnet"},
            ],
            slippage_surfaces=[
                {"netuid": 2, "size_tao": Decimal("100"), "slippage_pct": Decimal("0.02")},
                {"netuid": 2, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.04")},  # 4% at 50% exit
                {"netuid": 2, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.085")},  # 8.5% at 100% exit
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Strict assertions
        assert data["total_positions"] == 1
        assert data["warnings_count"] == 1
        assert data["force_trims_count"] == 0

        # Verify position is WARNING level
        assert len(data["positions"]) == 1
        pos = data["positions"][0]
        assert pos["netuid"] == 2
        assert pos["level"] == "warning"
        assert pos["slippage_50pct"] <= 0.05  # <= 5%
        assert pos["slippage_100pct"] > 0.075  # > 7.5%
        assert pos["slippage_100pct"] <= 0.10  # <= 10%

    @pytest.mark.asyncio
    async def test_endpoint_with_force_trim_positions(self, test_session, app_with_test_db):
        """Test endpoint correctly identifies FORCE_TRIM positions with trim details."""
        # Seed data with FORCE_TRIM slippage (100% exit > 10%)
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 3, "tao_value_mid": Decimal("1000")},
            ],
            subnets=[
                {"netuid": 3, "name": "High Slippage Subnet"},
            ],
            slippage_surfaces=[
                {"netuid": 3, "size_tao": Decimal("100"), "slippage_pct": Decimal("0.04")},
                {"netuid": 3, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.08")},
                {"netuid": 3, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.12")},  # 12% at full exit
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Should have force_trim
        assert data["total_positions"] == 1
        assert data["force_trims_count"] == 1
        assert data["total_trim_tao"] > 0

        # Check force_trims array
        assert len(data["force_trims"]) == 1
        trim = data["force_trims"][0]
        assert trim["netuid"] == 3
        assert trim["level"] == "force_trim"
        assert trim["slippage_100pct"] >= 0.10  # Above force trim threshold

        # Should have trim recommendation fields
        assert "safe_size_tao" in trim or "trim_amount_tao" in trim

    @pytest.mark.asyncio
    async def test_endpoint_with_mixed_positions(self, test_session, app_with_test_db):
        """Test endpoint handles multiple positions with different exitability levels.

        Position layout:
        - netuid 1: PASS (1000 TAO, 2% at full exit)
        - netuid 2: BLOCK_BUY (1000 TAO, 6% at 50% exit > 5%)
        - netuid 3: FORCE_TRIM (3000 TAO, 15% at full exit > 10%)
        """
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 1, "tao_value_mid": Decimal("1000")},  # PASS
                {"netuid": 2, "tao_value_mid": Decimal("1000")},  # BLOCK_BUY (50% exit > 5%)
                {"netuid": 3, "tao_value_mid": Decimal("3000")},  # FORCE_TRIM (100% exit > 10%)
            ],
            subnets=[
                {"netuid": 1, "name": "Good Subnet"},
                {"netuid": 2, "name": "Medium Subnet"},
                {"netuid": 3, "name": "Bad Subnet"},
            ],
            slippage_surfaces=[
                # PASS: netuid 1 (all slippage < 5%)
                {"netuid": 1, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.01")},
                {"netuid": 1, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.02")},
                # BLOCK_BUY: netuid 2 (50% exit at 500 TAO = 6% > 5%)
                {"netuid": 2, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.06")},
                {"netuid": 2, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.08")},
                # FORCE_TRIM: netuid 3 (100% exit at 3000 TAO = 15% > 10%)
                {"netuid": 3, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.08")},
                {"netuid": 3, "size_tao": Decimal("2000"), "slippage_pct": Decimal("0.11")},
                {"netuid": 3, "size_tao": Decimal("3000"), "slippage_pct": Decimal("0.15")},
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Strict count assertions
        assert data["total_positions"] == 3
        assert data["force_trims_count"] == 1

        # Verify position levels by netuid
        positions_by_netuid = {p["netuid"]: p for p in data["positions"]}
        assert positions_by_netuid[1]["level"] == "pass"
        assert positions_by_netuid[2]["level"] == "block_buy"
        assert positions_by_netuid[3]["level"] == "force_trim"

        # Verify force_trims array
        assert len(data["force_trims"]) == 1
        assert data["force_trims"][0]["netuid"] == 3
        assert data["force_trims"][0]["slippage_100pct"] >= 0.10

    @pytest.mark.asyncio
    async def test_endpoint_with_no_positions(self, test_session, app_with_test_db):
        """Test endpoint handles empty portfolio gracefully."""
        # No data seeded

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        assert data["total_positions"] == 0
        assert data["warnings_count"] == 0
        assert data["force_trims_count"] == 0
        assert len(data["positions"]) == 0

    @pytest.mark.asyncio
    async def test_endpoint_skips_root_network(self, test_session, app_with_test_db):
        """Test that root network (netuid=0) positions are skipped."""
        # Seed data with root and non-root positions
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 0, "tao_value_mid": Decimal("5000")},  # Root - should be skipped
                {"netuid": 1, "tao_value_mid": Decimal("1000")},  # dTAO - should be included
            ],
            subnets=[
                {"netuid": 0, "name": "Root Network"},
                {"netuid": 1, "name": "Test Subnet"},
            ],
            slippage_surfaces=[
                {"netuid": 0, "size_tao": Decimal("5000"), "slippage_pct": Decimal("0.01")},
                {"netuid": 1, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.02")},
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Only netuid=1 should be in results (root skipped)
        assert data["total_positions"] == 1
        assert data["positions"][0]["netuid"] == 1


class TestExitabilityResponseSchema:
    """Test that response schema matches ExitabilityResponse model."""

    @pytest.mark.asyncio
    async def test_response_has_all_required_fields(self, test_session, app_with_test_db):
        """Verify response contains all fields defined in ExitabilityResponse."""
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 1, "tao_value_mid": Decimal("1000")},
            ],
            subnets=[
                {"netuid": 1, "name": "Test"},
            ],
            slippage_surfaces=[
                {"netuid": 1, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.05")},
                {"netuid": 1, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.08")},
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Top-level required fields from ExitabilityResponse
        required_top_level = [
            "feature_enabled",
            "total_positions",
            "warnings_count",
            "force_trims_count",
            "total_trim_tao",
            "positions",
            "warnings",
            "force_trims",
        ]
        for field in required_top_level:
            assert field in data, f"Missing required field: {field}"

        # Position entry required fields from ExitabilityPositionResponse
        if data["positions"]:
            pos = data["positions"][0]
            required_position_fields = [
                "netuid",
                "subnet_name",
                "level",
                "slippage_50pct",
                "slippage_100pct",
                "current_size_tao",
                "reason",
            ]
            for field in required_position_fields:
                assert field in pos, f"Missing required position field: {field}"

    @pytest.mark.asyncio
    async def test_field_types_correct(self, test_session, app_with_test_db):
        """Verify response field types match schema expectations."""
        await seed_test_data(
            test_session,
            positions=[
                {"netuid": 1, "tao_value_mid": Decimal("1000")},
            ],
            subnets=[
                {"netuid": 1, "name": "Test"},
            ],
            slippage_surfaces=[
                {"netuid": 1, "size_tao": Decimal("500"), "slippage_pct": Decimal("0.03")},
                {"netuid": 1, "size_tao": Decimal("1000"), "slippage_pct": Decimal("0.05")},
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_test_db),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/strategy/exitability")

        assert response.status_code == 200
        data = response.json()

        # Type checks
        assert isinstance(data["feature_enabled"], bool)
        assert isinstance(data["total_positions"], int)
        assert isinstance(data["warnings_count"], int)
        assert isinstance(data["force_trims_count"], int)
        assert isinstance(data["total_trim_tao"], (int, float))
        assert isinstance(data["positions"], list)
        assert isinstance(data["warnings"], list)
        assert isinstance(data["force_trims"], list)

        if data["positions"]:
            pos = data["positions"][0]
            assert isinstance(pos["netuid"], int)
            assert isinstance(pos["subnet_name"], str)
            assert isinstance(pos["level"], str)
            assert isinstance(pos["slippage_50pct"], (int, float))
            assert isinstance(pos["slippage_100pct"], (int, float))
            assert isinstance(pos["current_size_tao"], (int, float))
            assert isinstance(pos["reason"], str)
