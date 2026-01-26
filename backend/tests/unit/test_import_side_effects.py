"""Guard test to ensure no import-time side effects.

This test verifies that importing backend modules does not trigger:
- get_settings() calls
- Database connections
- Redis connections
- HTTP client creation
- Any other I/O operations

If this test fails, it means someone introduced import-time side effects
that need to be moved to lazy initialization.
"""

import sys
from unittest.mock import patch, MagicMock
import pytest


class TestNoImportSideEffects:
    """Verify that importing modules does not trigger side effects."""

    def test_no_get_settings_on_import(self):
        """Ensure get_settings() is not called during import.

        We monkeypatch get_settings to raise an error, then import
        modules that previously had side effects. If get_settings
        is called at import time, this test will fail.
        """
        # Track if get_settings was called
        call_tracker = {"called": False, "caller": None}

        def mock_get_settings():
            import traceback
            call_tracker["called"] = True
            call_tracker["caller"] = "".join(traceback.format_stack())
            raise RuntimeError(
                "get_settings() was called during import! "
                "This indicates an import-time side effect.\n"
                f"Call stack:\n{call_tracker['caller']}"
            )

        # Clear any cached modules that might have already loaded
        modules_to_clear = [
            key for key in list(sys.modules.keys())
            if key.startswith("app.services.") or key.startswith("app.api.")
        ]
        for mod in modules_to_clear:
            del sys.modules[mod]

        # Patch get_settings before importing
        with patch("app.core.config.get_settings", mock_get_settings):
            # Import modules that previously had import-time side effects
            # These should all import cleanly without calling get_settings

            # Strategy modules
            try:
                from app.services.strategy import eligibility_gate
                from app.services.strategy import strategy_engine
                from app.services.strategy import position_sizer
                from app.services.strategy import regime_calculator
                from app.services.strategy import constraint_enforcer
                from app.services.strategy import rebalancer
                from app.services.strategy import macro_regime_detector
            except RuntimeError as e:
                if "get_settings() was called during import" in str(e):
                    pytest.fail(f"Strategy module import caused side effect: {e}")
                raise

            # Analysis modules
            try:
                from app.services.analysis import slippage_sync
                from app.services.analysis import risk_monitor
                from app.services.analysis import transaction_sync
                from app.services.analysis import nav_calculator
                from app.services.analysis import cost_basis
            except RuntimeError as e:
                if "get_settings() was called during import" in str(e):
                    pytest.fail(f"Analysis module import caused side effect: {e}")
                raise

            # Data modules
            try:
                from app.services.data import taostats_client
                from app.services.data import data_sync
            except RuntimeError as e:
                if "get_settings() was called during import" in str(e):
                    pytest.fail(f"Data module import caused side effect: {e}")
                raise

            # API modules
            try:
                from app.api.v1 import portfolio
                from app.api.v1 import positions
                from app.api.v1 import recommendations
            except RuntimeError as e:
                if "get_settings() was called during import" in str(e):
                    pytest.fail(f"API module import caused side effect: {e}")
                raise

        # If we got here, no side effects occurred
        assert not call_tracker["called"], "get_settings was called during import"

    def test_core_modules_remain_lazy(self):
        """Verify that core database and redis modules use lazy initialization."""
        # Clear modules
        for key in list(sys.modules.keys()):
            if "app.core.database" in key or "app.core.redis" in key:
                del sys.modules[key]

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()

            # Import should not create engine or redis client
            from app.core import database
            from app.core import redis

            # Check that the private variables are None (not yet initialized)
            assert database._engine is None, "Database engine was created at import time"
            assert database._async_session_factory is None, "Session factory was created at import time"
            assert redis._redis_client is None, "Redis client was created at import time"

    def test_lazy_singletons_not_instantiated_on_import(self):
        """Verify lazy singletons are not instantiated at import time.

        This test checks that the internal singleton variables remain None
        after import, confirming lazy initialization is working.
        """
        # Clear service modules to ensure fresh import
        modules_to_clear = [
            key for key in list(sys.modules.keys())
            if key.startswith("app.services.")
        ]
        for mod in modules_to_clear:
            del sys.modules[mod]

        # Import modules fresh - this should NOT instantiate singletons
        import app.services.data.taostats_client
        import app.services.data.data_sync
        import app.services.analysis.risk_monitor
        import app.services.analysis.cost_basis
        import app.services.analysis.transaction_sync

        # Access modules from sys.modules to avoid any name shadowing
        tc_mod = sys.modules["app.services.data.taostats_client"]
        ds_mod = sys.modules["app.services.data.data_sync"]
        rm_mod = sys.modules["app.services.analysis.risk_monitor"]
        cb_mod = sys.modules["app.services.analysis.cost_basis"]
        ts_mod = sys.modules["app.services.analysis.transaction_sync"]

        # Verify internal singleton state is None (not yet instantiated)
        # These will only be set when get_xxx() is called
        assert tc_mod._taostats_client is None, (
            "TaoStatsClient was instantiated at import time"
        )
        assert ds_mod._data_sync_service is None, (
            "DataSyncService was instantiated at import time"
        )
        assert rm_mod._risk_monitor is None, (
            "RiskMonitor was instantiated at import time"
        )
        assert cb_mod._cost_basis_service is None, (
            "CostBasisService was instantiated at import time"
        )
        assert ts_mod._transaction_sync_service is None, (
            "TransactionSyncService was instantiated at import time"
        )
