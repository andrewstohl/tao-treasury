# Import Side Effects Prevention

This document describes the patterns used to eliminate import-time side effects from the backend codebase and how to maintain this invariant when adding new code.

## Why This Matters

Import-time side effects cause problems:
- **Test isolation**: Tests become order-dependent and flaky
- **Environment coupling**: Importing code requires environment variables to be set
- **Startup latency**: Eager initialization slows down application startup
- **Error masking**: Failures during import are harder to debug than runtime failures

## The Rules

### Hard Rules (enforced by tests)

1. **No module-level `settings = get_settings()`** anywhere in `backend/app/**`
2. **No module-level creation of**:
   - Database engines or session factories
   - Redis clients
   - HTTP clients (httpx, aiohttp, etc.)
   - External API clients (TaoStats, etc.)
   - Schedulers or background workers
   - Caches with I/O dependencies
3. **Importing any module must be safe** without environment variables set

### What's Allowed at Module Level

- Constants (literal values, computed from other constants)
- Class definitions (but not instances that trigger I/O)
- Function definitions
- Type aliases and protocols
- Logger instances (`structlog.get_logger()` is safe)
- Lazy proxy objects (see patterns below)

## Patterns Used

### Pattern 1: Lazy Settings in `__init__`

For classes that need settings, fetch them in `__init__`:

```python
# WRONG - module-level side effect
settings = get_settings()

class MyService:
    def __init__(self):
        self.wallet = settings.wallet_address  # Uses module-level settings


# CORRECT - lazy initialization
class MyService:
    def __init__(self):
        settings = get_settings()  # Deferred to instantiation time
        self.wallet = settings.wallet_address
```

### Pattern 2: Lazy Singleton with Getter + Proxy

For singleton services, use a private variable, getter function, and lazy proxy:

```python
from app.core.config import get_settings

class MyService:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.api_key

    async def do_work(self):
        # ... implementation


# Lazy singleton instance (None until first use)
_my_service: MyService | None = None


def get_my_service() -> MyService:
    """Get or create the MyService singleton."""
    global _my_service
    if _my_service is None:
        _my_service = MyService()
    return _my_service


class _LazyMyService:
    """Lazy proxy for backwards compatibility with module-level imports."""

    def __getattr__(self, name):
        return getattr(get_my_service(), name)


# This can be imported and used like the old eager singleton
my_service = _LazyMyService()
```

Usage in other modules:

```python
# Option 1: Direct getter (preferred for new code)
from app.services.my_service import get_my_service

service = get_my_service()
await service.do_work()

# Option 2: Lazy proxy (for backwards compatibility)
from app.services.my_service import my_service

await my_service.do_work()  # Triggers lazy initialization on first access
```

### Pattern 3: Lazy Settings in Endpoint Functions

For FastAPI endpoints that need settings:

```python
# WRONG
settings = get_settings()

@router.get("/data")
async def get_data():
    wallet = settings.wallet_address
    # ...


# CORRECT
@router.get("/data")
async def get_data():
    settings = get_settings()
    wallet = settings.wallet_address
    # ...
```

### Pattern 4: Constructor Injection (for testability)

When maximum testability is needed:

```python
class MyService:
    def __init__(self, wallet_address: str, api_key: str):
        self.wallet_address = wallet_address
        self.api_key = api_key


def get_my_service() -> MyService:
    settings = get_settings()
    return MyService(
        wallet_address=settings.wallet_address,
        api_key=settings.api_key,
    )
```

## Files Modified

The following files were updated to eliminate import-time side effects:

### API Layer
- `app/api/v1/portfolio.py` - Lazy settings in endpoint
- `app/api/v1/positions.py` - Lazy settings in endpoint
- `app/api/v1/recommendations.py` - Lazy settings in endpoint

### Data Services
- `app/services/data/taostats_client.py` - Lazy singleton pattern
- `app/services/data/data_sync.py` - Lazy singleton pattern

### Strategy Services
- `app/services/strategy/eligibility_gate.py` - Lazy singleton pattern
- `app/services/strategy/strategy_engine.py` - Lazy singleton pattern
- `app/services/strategy/position_sizer.py` - Lazy singleton pattern
- `app/services/strategy/regime_calculator.py` - Lazy singleton pattern
- `app/services/strategy/constraint_enforcer.py` - Lazy singleton pattern
- `app/services/strategy/rebalancer.py` - Lazy singleton pattern
- `app/services/strategy/macro_regime_detector.py` - Lazy singleton pattern

### Analysis Services
- `app/services/analysis/slippage_sync.py` - Lazy singleton pattern
- `app/services/analysis/risk_monitor.py` - Lazy singleton pattern
- `app/services/analysis/transaction_sync.py` - Lazy singleton pattern
- `app/services/analysis/nav_calculator.py` - Lazy singleton pattern
- `app/services/analysis/cost_basis.py` - Lazy singleton pattern

### Core (already lazy)
- `app/core/database.py` - Uses lazy engine/session factory creation
- `app/core/redis.py` - Uses lazy client creation

## Guard Tests

The file `tests/unit/test_import_side_effects.py` contains guard tests that will fail if import-time side effects are reintroduced:

1. **`test_no_get_settings_on_import`**: Patches `get_settings()` to raise an error, then imports all service modules. If any module calls `get_settings()` at import time, the test fails.

2. **`test_core_modules_remain_lazy`**: Verifies that `app.core.database` and `app.core.redis` don't create engines or clients at import time.

3. **`test_lazy_singletons_not_instantiated_on_import`**: Verifies that singleton variables (`_taostats_client`, `_data_sync_service`, etc.) remain `None` after import.

Run the guard tests:
```bash
pytest tests/unit/test_import_side_effects.py -v
```

## Adding New Code

When adding new services or modules:

1. **Never** use `settings = get_settings()` at module level
2. **Always** call `get_settings()` inside `__init__` or functions
3. **Use the lazy singleton pattern** for singleton services
4. **Add your module** to `test_no_get_settings_on_import` imports
5. **Run guard tests** before committing

Example checklist for new service:
- [ ] Settings fetched in `__init__`, not module level
- [ ] Private singleton variable: `_my_service: MyService | None = None`
- [ ] Getter function: `def get_my_service() -> MyService`
- [ ] Lazy proxy class for backwards compatibility (optional)
- [ ] Module added to guard test imports
- [ ] Guard tests pass: `pytest tests/unit/test_import_side_effects.py -v`
