"""Watchlist kanban management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.user import WatchlistEntry
from pipa.schemas.property import WatchlistEntryCreate, WatchlistEntryResponse, WatchlistStageUpdate

router = APIRouter(tags=["watchlist"])

# For now, use a default user ID (single-user desktop app)
DEFAULT_USER_ID = "default-user"


@router.get("/watchlist", response_model=list[WatchlistEntryResponse])
async def list_watchlist(stage: str | None = None, db: AsyncSession = Depends(get_db)):
    """List watchlist entries, optionally filtered by stage."""
    query = select(WatchlistEntry).where(WatchlistEntry.user_id == DEFAULT_USER_ID)
    if stage:
        query = query.where(WatchlistEntry.stage == stage)
    query = query.order_by(WatchlistEntry.priority.desc(), WatchlistEntry.added_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/watchlist", response_model=WatchlistEntryResponse, status_code=201)
async def add_to_watchlist(body: WatchlistEntryCreate, db: AsyncSession = Depends(get_db)):
    """Add a property to the watchlist."""
    # Check for duplicate
    existing = await db.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.user_id == DEFAULT_USER_ID,
            WatchlistEntry.property_id == body.property_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Property already on watchlist")

    entry = WatchlistEntry(
        user_id=DEFAULT_USER_ID,
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
