"""Manual component install-year override endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.services.component_overrides import (
    delete_override,
    get_overrides,
    set_override,
)

router = APIRouter(tags=["component_overrides"])

# Canonical keys the resolver/condition engine recognize. Reject anything
# else so users can't accidentally create dead overrides for typos.
VALID_KEYS = {
    "roof", "hvac", "water_heater", "electrical_panel", "windows",
    "appliances", "fence", "siding", "deck", "driveway", "garage_door",
    "kitchen", "bathroom", "patio", "gazebo", "sprinkler", "basement",
}


class OverrideIn(BaseModel):
    year: int = Field(..., ge=1800, le=2100)
    notes: Optional[str] = Field(None, max_length=500)


@router.get("/properties/{property_id}/component-overrides")
async def list_overrides(property_id: str, db: AsyncSession = Depends(get_db)):
    """Return all manual component overrides for a property."""
    return await get_overrides(db, property_id)


@router.put("/properties/{property_id}/component-overrides/{canonical_key}")
async def upsert_override(
    property_id: str,
    canonical_key: str,
    body: OverrideIn,
    db: AsyncSession = Depends(get_db),
):
    """Set or update a manual install-year override for one component."""
    if canonical_key not in VALID_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown canonical_key '{canonical_key}'. Valid keys: {sorted(VALID_KEYS)}",
        )
    payload = await set_override(db, property_id, canonical_key, body.year, body.notes)
    await db.commit()
    return {"canonical_key": canonical_key, **payload}


@router.delete(
    "/properties/{property_id}/component-overrides/{canonical_key}",
    status_code=204,
)
async def remove_override(
    property_id: str,
    canonical_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a manual override (revert to AI/county/default value)."""
    if canonical_key not in VALID_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown canonical_key '{canonical_key}'. Valid keys: {sorted(VALID_KEYS)}",
        )
    deleted = await delete_override(db, property_id, canonical_key)
    if not deleted:
        raise HTTPException(404, "No override exists for that component")
    await db.commit()
