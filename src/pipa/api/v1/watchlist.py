"""Watchlist kanban management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.user import User, WatchlistEntry
from pipa.schemas.property import WatchlistEntryCreate, WatchlistEntryResponse, WatchlistStageUpdate

router = APIRouter(tags=["watchlist"])

# Canonical email for the single-user default. Must match
# pipa.services.property_import.PropertyImportService._get_or_create_default_user
# so the property-ingest path and the watchlist path agree on the same row.
_DEFAULT_USER_EMAIL = "default@pipa.local"


async def _get_default_user_id(db: AsyncSession) -> str:
    """Look up (and lazily create) the default user, return its id.

    Previously this module hardcoded a UUID which broke the moment the
    DB was wiped — the rebuilt user got a fresh UUID and the watchlist
    endpoint kept inserting against the stale id, hitting a FOREIGN KEY
    constraint on watchlist_entry.user_id.
    """
    result = await db.execute(select(User).where(User.email == _DEFAULT_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        return user.id
    # Lazily create on first access. Property ingest also creates this
    # row but the watchlist UI may run before any property has been added.
    user = User(email=_DEFAULT_USER_EMAIL, display_name="Default User")
    db.add(user)
    await db.flush()
    return user.id


@router.get("/watchlist", response_model=list[WatchlistEntryResponse])
async def list_watchlist(stage: str | None = None, db: AsyncSession = Depends(get_db)):
    """List watchlist entries, optionally filtered by stage."""
    user_id = await _get_default_user_id(db)
    query = select(WatchlistEntry).where(WatchlistEntry.user_id == user_id)
    if stage:
        query = query.where(WatchlistEntry.stage == stage)
    query = query.order_by(WatchlistEntry.priority.desc(), WatchlistEntry.added_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/watchlist", response_model=WatchlistEntryResponse, status_code=201)
async def add_to_watchlist(body: WatchlistEntryCreate, db: AsyncSession = Depends(get_db)):
    """Add a property to the watchlist."""
    user_id = await _get_default_user_id(db)

    # Check for duplicate
    existing = await db.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.user_id == user_id,
            WatchlistEntry.property_id == body.property_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Property already on watchlist")

    entry = WatchlistEntry(
        user_id=user_id,
        property_id=body.property_id,
        stage=body.stage,
        priority=body.priority,
    )
    db.add(entry)
    await db.flush()
    return entry


@router.patch("/watchlist/{entry_id}", response_model=WatchlistEntryResponse)
async def update_watchlist_stage(entry_id: str, body: WatchlistStageUpdate, db: AsyncSession = Depends(get_db)):
    """Update watchlist entry stage (kanban move)."""
    result = await db.execute(select(WatchlistEntry).where(WatchlistEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")

    entry.stage = body.stage
    entry.stage_changed_at = datetime.now(timezone.utc)
    return entry


@router.delete("/watchlist/{entry_id}", status_code=204)
async def remove_from_watchlist(entry_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a property from the watchlist."""
    result = await db.execute(select(WatchlistEntry).where(WatchlistEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    await db.delete(entry)
