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


@router.get("/properties/{property_id}/flood-zone")
async def get_flood_zone(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get FEMA flood zone designation for a property.

    Queries the FEMA National Flood Hazard Layer using the property's
    lat/lng coordinates. No API key needed.
    """
    from pipa.models.property import AddressHistory

    await _verify_property(db, property_id)

    # Get coordinates
    result = await db.execute(
        select(AddressHistory).where(
            AddressHistory.property_id == property_id,
            AddressHistory.is_current == True,
        ).limit(1)
    )
    addr = result.scalar_one_or_none()
    if not addr or not addr.latitude or not addr.longitude:
        # Try listing data for coordinates
        from pipa.models.listing_page import ListingPageSnapshot
        snap_result = await db.execute(
            select(ListingPageSnapshot).where(
                ListingPageSnapshot.property_id == property_id,
            ).order_by(ListingPageSnapshot.scraped_at.desc()).limit(1)
        )
        snap = snap_result.scalar_one_or_none()
        lat = snap.parsed_fields.get("latitude") if snap and snap.parsed_fields else None
        lng = snap.parsed_fields.get("longitude") if snap and snap.parsed_fields else None
        if not lat or not lng:
            return {"error": "No coordinates available for property"}
    else:
        lat, lng = addr.latitude, addr.longitude

    from pipa.clients.fema_flood import lookup_flood_zone
    flood = await lookup_flood_zone(float(lat), float(lng))
    if not flood:
        return {"error": "FEMA flood zone lookup failed"}
    return flood


@router.get("/properties/{property_id}/schools")
async def get_schools(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get LCPS assigned schools + Zillow schools + cross-reference.

    Returns LCPS official assignments (authoritative), Zillow nearby
    schools (supplementary), and any discrepancies between them.
    """
    await _verify_property(db, property_id)

    # Get LCPS school evidence
    from pipa.models.source import EvidenceItem
    lcps_result = await db.execute(
        select(EvidenceItem).where(
            EvidenceItem.property_id == property_id,
            EvidenceItem.field_name.in_([
                "school_elementary", "school_middle", "school_high",
            ]),
            EvidenceItem.confidence == "confirmed",
        ).order_by(EvidenceItem.observed_at.desc())
    )
    lcps_items = lcps_result.scalars().all()

    # Deduplicate by field_name (keep latest)
    seen = {}
    for item in lcps_items:
        level = item.field_name.replace("school_", "")
        if level not in seen:
            seen[level] = item.field_value

    lcps_schools = []
    for level in ("elementary", "middle", "high"):
        name = seen.get(level)
        if name:
            lcps_schools.append({"name": name, "level": level, "_source": "lcps"})

    # Get Zillow schools from listing data
    from pipa.models.listing_page import ListingPageSnapshot
    snap_result = await db.execute(
        select(ListingPageSnapshot).where(
            ListingPageSnapshot.property_id == property_id,
        ).order_by(ListingPageSnapshot.scraped_at.desc()).limit(1)
    )
    snap = snap_result.scalar_one_or_none()
    zillow_schools = []
    if snap and snap.parsed_fields:
        raw = snap.parsed_fields.get("assigned_schools") or snap.parsed_fields.get("nearby_schools") or []
        for s in raw:
            s["_source"] = "zillow"
            # Merge Zillow rating/distance into LCPS schools
            for ls in lcps_schools:
                if ls["level"] == (s.get("level") or "").lower():
                    ls["rating"] = s.get("rating")
                    ls["distance_mi"] = s.get("distance_mi") or s.get("distance")
                    ls["grades"] = s.get("grades")
                    ls["enrollment"] = s.get("enrollment")
                    ls["student_teacher_ratio"] = s.get("student_teacher_ratio")
        zillow_schools = raw

    # Cross-reference
    from pipa.services.school_service import SchoolService
    xref = await SchoolService.cross_reference_zillow(db, property_id)

    return {
        "lcps_schools": lcps_schools if lcps_schools else zillow_schools,
        "zillow_schools": zillow_schools,
        "cross_reference": xref,
    }
