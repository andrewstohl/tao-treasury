"""Pytest configuration and fixtures for TAO Treasury tests."""

import os
import pytest
import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Set required env vars for tests before importing app modules
# DATABASE_URL points to test DB so imports never boot prod engine during collection
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TAOSTATS_API_KEY", "test_api_key")
os.environ.setdefault("WALLET_ADDRESS", "test_wallet_address")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def mock_settings():
    """Provide mock settings for testing."""
    from unittest.mock import MagicMock
    from decimal import Decimal

    settings = MagicMock()
    settings.wallet_address = "test_wallet_address"
    settings.max_exit_slippage_50pct = Decimal("0.05")
    settings.max_exit_slippage_100pct = Decimal("0.10")
    settings.exitability_warning_threshold = Decimal("0.075")
    settings.enable_exitability_gate = False
    settings.min_liquidity_tao = Decimal("1000")
    settings.min_holder_count = 50
    settings.min_subnet_age_days = 30
    settings.max_owner_take = Decimal("0.20")
    settings.min_emission_share = Decimal("0.001")

    return settings
