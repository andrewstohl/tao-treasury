"""Examples proxy endpoint for TaoStats API."""

from typing import Any, Dict

import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import get_settings
from app.services.data.taostats_client import get_taostats_client

logger = structlog.get_logger()
router = APIRouter()

ALLOWED_ENDPOINTS = {
    # Portfolio & Stake
    "/api/dtao/stake_balance/latest/v1",
    "/api/dtao/stake_balance/history/v1",
    "/api/dtao/hotkey_alpha_shares/latest/v1",
    "/api/dtao/validator/latest/v1",
    "/api/validator/latest/v1",
    "/api/subnet/latest/v1",
    "/api/account/history/v1",
    "/api/delegation/v1",
    # Accounting & P&L
    "/api/accounting/tax/v1",
    "/api/accounting/v1",
    "/api/price/ohlc/v1",
    "/api/hotkey/family/latest/v1",
    # Subnet Analytics
    "/api/dtao/pool/history/v1",
    "/api/dtao/burned_alpha/v1",
    "/api/dtao/subnet_emission/v1",
    "/api/subnet/history/v1",
    "/api/stats/latest/v1",
    "/api/stats/history/v1",
    "/api/dtao/pool/total_price/v1",
    "/api/price/history/v1",
}

WALLET_ENDPOINTS = {
    "/api/dtao/stake_balance/latest/v1": "coldkey",
    "/api/dtao/stake_balance/history/v1": "coldkey",
    "/api/dtao/hotkey_alpha_shares/latest/v1": "coldkey",
    "/api/account/history/v1": "address",
    "/api/delegation/v1": "coldkey",
    "/api/accounting/tax/v1": "coldkey",
    "/api/accounting/v1": "coldkey",
}


@router.get("/proxy")
async def examples_proxy(
    request: Request,
    endpoint: str = Query(..., description="TaoStats API endpoint path"),
) -> Any:
    """Generic proxy for TaoStats API endpoints used by examples."""
    if endpoint not in ALLOWED_ENDPOINTS:
        raise HTTPException(status_code=400, detail=f"Endpoint not allowed: {endpoint}")

    settings = get_settings()
    client = get_taostats_client()

    params = dict(request.query_params)
    params.pop("endpoint", None)

    if endpoint in WALLET_ENDPOINTS:
        param_name = WALLET_ENDPOINTS[endpoint]
        if param_name not in params:
            params[param_name] = settings.wallet_address

    logger.info("Examples proxy request", endpoint=endpoint)

    try:
        data = await client._request(
            "GET",
            endpoint,
            params=params,
            cache_key=None,
            cache_ttl=None,
        )
        return data
    except Exception as e:
        logger.error("Examples proxy error", endpoint=endpoint, error=str(e))
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/wallet")
async def get_wallet_address() -> Dict[str, str]:
    """Return the configured wallet address."""
    settings = get_settings()
    return {"wallet_address": settings.wallet_address}
