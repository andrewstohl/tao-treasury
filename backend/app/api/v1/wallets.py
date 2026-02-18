"""Wallet management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.wallet import Wallet
from app.schemas.wallet import (
    WalletCreate,
    WalletUpdate,
    WalletResponse,
    WalletListResponse,
)

router = APIRouter()


@router.get("", response_model=WalletListResponse)
async def list_wallets(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> WalletListResponse:
    """List all tracked wallets."""
    stmt = select(Wallet).order_by(Wallet.created_at.desc())
    if active_only:
        stmt = stmt.where(Wallet.is_active == True)  # noqa: E712

    result = await db.execute(stmt)
    wallets = list(result.scalars().all())

    return WalletListResponse(
        wallets=[WalletResponse.model_validate(w) for w in wallets],
        total=len(wallets),
    )


@router.post("", response_model=WalletResponse, status_code=201)
async def add_wallet(
    request: WalletCreate,
    db: AsyncSession = Depends(get_db),
) -> WalletResponse:
    """Add a new wallet to track."""
    # Check if wallet already exists
    existing = await db.get(Wallet, request.address)
    if existing:
        if not existing.is_active:
            # Re-activate a previously deactivated wallet
            existing.is_active = True
            if request.label is not None:
                existing.label = request.label
            await db.flush()
            await db.refresh(existing)
            wallet = existing
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Wallet {request.address} already exists",
            )
    else:
        wallet = Wallet(
            address=request.address,
            label=request.label,
            is_active=True,
        )
        db.add(wallet)
        await db.flush()
        await db.refresh(wallet)

    # Note: the frontend triggers a sync (POST /tasks/refresh) after adding
    # a wallet so that positions and snapshots are ready before queries fire.
    # A background sync here would be unreliable because the DB transaction
    # hasn't been committed yet when asyncio.create_task runs.

    return WalletResponse.model_validate(wallet)


@router.get("/{address}", response_model=WalletResponse)
async def get_wallet(
    address: str,
    db: AsyncSession = Depends(get_db),
) -> WalletResponse:
    """Get a specific wallet."""
    wallet = await db.get(Wallet, address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    return WalletResponse.model_validate(wallet)


@router.patch("/{address}", response_model=WalletResponse)
async def update_wallet(
    address: str,
    request: WalletUpdate,
    db: AsyncSession = Depends(get_db),
) -> WalletResponse:
    """Update a wallet's label or active status."""
    wallet = await db.get(Wallet, address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    if request.label is not None:
        wallet.label = request.label
    if request.is_active is not None:
        wallet.is_active = request.is_active

    await db.flush()
    await db.refresh(wallet)

    return WalletResponse.model_validate(wallet)


@router.delete("/{address}", status_code=204)
async def delete_wallet(
    address: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a wallet from tracking.

    Soft-deletes the wallet by setting is_active=False.
    Position and transaction history is preserved.
    The wallet can be re-added later to restore tracking.
    """
    wallet = await db.get(Wallet, address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet.is_active = False
