"""Wallet schemas for API requests and responses."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WalletCreate(BaseModel):
    """Request to add a new wallet."""

    address: str = Field(
        ...,
        min_length=46,
        max_length=128,
        pattern=r"^[1-9A-HJ-NP-Za-km-z]{46,48}$",
        description="Wallet address (SS58 format, typically 47-48 characters)",
    )
    label: Optional[str] = Field(None, max_length=128, description="Optional display label")


class WalletUpdate(BaseModel):
    """Request to update a wallet."""

    label: Optional[str] = Field(None, max_length=128, description="Optional display label")
    is_active: Optional[bool] = Field(None, description="Whether to sync this wallet")


class WalletResponse(BaseModel):
    """Wallet details."""

    address: str
    label: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WalletListResponse(BaseModel):
    """List of wallets."""

    wallets: List[WalletResponse]
    total: int
