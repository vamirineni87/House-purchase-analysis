"""County data endpoints — assessments, permits, deeds, and refresh."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.property import Property
from pipa.models.source import SourceRecord
from pipa.schemas.county import (
    AssessmentResponse,
    CountyRefreshResult,
    DeedResponse,
    PermitResponse,
)
from pipa.services.county_service import CountyService

router = APIRouter(tags=["county"])


async def _verify_property(db: AsyncSession, property_id: str) -> None:
    """Raise 404 if the property does not exist."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Property not found")


@router.get("/properties/{property_id}/county")
async def get_county_data(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get all county data for a property.

    Returns assessments, permits, deeds, AND the full residential summary
    from the raw county scrape (sqft, baths, roof, HVAC, etc.).
    """
    await _verify_property(db, property_id)
    assessments = await CountyService.get_assessments(db, property_id)
    permits = await CountyService.get_permits(db, property_id)
    deeds = await CountyService.get_deeds(db, property_id)

    # Get the raw county summary with all residential details
    result = await db.execute(
        select(SourceRecord)
        .where(
            SourceRecord.property_id == property_id,
            SourceRecord.source_name.in_(["loudoun_county", "loudoun_parcel"]),
        )
        .order_by(SourceRecord.fetched_at.desc())
        .limit(1)
    )
    source_rec = result.scalar_one_or_none()
    summary = {}
    if source_rec and source_rec.raw_payload:
        payload = source_rec.raw_payload
        summary = payload.get("_summary", {})

    return {
        "assessments": [
            {c.name: getattr(a, c.name) for c in a.__table__.columns}
            for a in assessments
        ] if assessments else [],
        "permits": [
            {c.name: getattr(p, c.name) for c in p.__table__.columns}
            for p in permits
        ] if permits else [],
        "deeds": [
            {c.name: getattr(d, c.name) for c in d.__table__.columns}
            for d in deeds
        ] if deeds else [],
        "summary": summary,
    }


@router.post(
    "/properties/{property_id}/county/refresh",
    response_model=CountyRefreshResult,
)
async def refresh_county_data(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a county data refresh for a property.

    Fetches latest assessments, permits, and deeds from county sources.
    """
    await _verify_property(db, property_id)
    return await CountyService.refresh_county_data(db, property_id)


@router.get(
    "/properties/{property_id}/county/assessments",
    response_model=list[AssessmentResponse],
)
async def get_assessments(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all assessment snapshots for a property."""
    await _verify_property(db, property_id)
    return await CountyService.get_assessments(db, property_id)


@router.get(
    "/properties/{property_id}/county/permits",
    response_model=list[PermitResponse],
)
async def get_permits(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all permit records for a property."""
    await _verify_property(db, property_id)
    return await CountyService.get_permits(db, property_id)


@router.get(
    "/properties/{property_id}/county/deeds",
    response_model=list[DeedResponse],
)
async def get_deeds(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all deed records for a property."""
    await _verify_property(db, property_id)
    return await CountyService.get_deeds(db, property_id)
