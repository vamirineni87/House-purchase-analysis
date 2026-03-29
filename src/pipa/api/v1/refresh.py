"""Data refresh endpoints — refresh, freshness checks, and cross-reference.

Provides a unified API for triggering data source refreshes, checking
how stale each source is, and running cross-reference conflict checks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.property import Property
from pipa.services.data_refresh import DataRefreshService

router = APIRouter(tags=["refresh"])

# Valid source slugs for single-source refresh
_VALID_SOURCES = {"zillow", "redfin", "county", "schools", "hazard", "census", "walkscore"}


async def _verify_property(db: AsyncSession, property_id: str) -> None:
    """Raise 404 if the property does not exist."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Property not found")


@router.post("/properties/{property_id}/refresh")
async def refresh_all_sources(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Refresh all data sources for a property.

    Triggers a refresh of Zillow, county, schools, hazard, and other
    data sources. Returns status per source with count of updated fields.
    """
    await _verify_property(db, property_id)
    return await DataRefreshService.refresh_all(db, property_id)


@router.post("/properties/{property_id}/refresh/{source}")
async def refresh_single_source(
    property_id: str,
    source: str,
    db: AsyncSession = Depends(get_db),
):
    """Refresh a single data source for a property.

    Valid sources: zillow, redfin, county, schools, hazard, census, walkscore.
    """
    await _verify_property(db, property_id)

    if source.lower() not in _VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source '{source}'. Valid sources: {', '.join(sorted(_VALID_SOURCES))}",
        )

    return await DataRefreshService.refresh_source(db, property_id, source)


@router.get("/properties/{property_id}/freshness")
async def check_freshness(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Check data freshness for all sources.

    Returns per-source information including last fetch time, configured
    TTL, whether the data is stale, and the configured stale behavior.
    """
    await _verify_property(db, property_id)
    return await DataRefreshService.check_freshness(db, property_id)


@router.get("/properties/{property_id}/cross-reference")
async def cross_reference_all(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run cross-reference checks across all data sources.

    Compares Zillow vs County, Zillow vs LCPS schools, listing price vs
    assessment, and other field-level cross-checks. Returns a list of
    conflicts with severity levels.
    """
    await _verify_property(db, property_id)
    return await DataRefreshService.cross_reference_all(db, property_id)
