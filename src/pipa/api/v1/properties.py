"""Property CRUD and ingest endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_config, get_db
from pipa.models.property import AddressHistory, Property
from pipa.schemas.property import (
    PropertyCreate,
    PropertyIngestRequest,
    PropertyIngestResponse,
    PropertyResponse,
    PropertySummary,
)
from pipa.utils.geo import detect_county, normalize_address, parse_address

logger = logging.getLogger(__name__)

router = APIRouter(tags=["properties"])


@router.post("/properties", response_model=PropertyResponse, status_code=201)
async def create_property(body: PropertyCreate, db: AsyncSession = Depends(get_db)):
    """Create a new property with its address."""
    addr = body.address
    parsed = parse_address(f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}")

    # Detect county if not provided
    county = addr.county or detect_county(addr.city, addr.state, addr.zip_code)

    # Create property
    prop = Property(property_type=body.property_type)
    db.add(prop)
    await db.flush()  # Get the ID

    # Create address
    normalized = normalize_address(f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}")
    address = AddressHistory(
        property_id=prop.id,
        address_type="situs",
        normalized_address=normalized,
        raw_address=f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}",
        city=addr.city,
        state=addr.state,
        zip_code=addr.zip_code,
        county=county,
        latitude=addr.latitude,
        longitude=addr.longitude,
        is_current=True,
        valid_from=datetime.now(timezone.utc),
    )
    db.add(address)
    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses), selectinload(Property.parcel_identifiers))
        .where(Property.id == prop.id)
    )
    prop = result.scalar_one()

    return prop


@router.get("/properties", response_model=list[PropertySummary])
async def list_properties(db: AsyncSession = Depends(get_db)):
    """List all properties."""
    result = await db.execute(
        select(Property).options(selectinload(Property.addresses)).order_by(Property.created_at.desc())
    )
    properties = result.scalars().all()

    summaries = []
    for p in properties:
        current_addr = None
        county = None
        for a in p.addresses:
            if a.is_current and a.address_type == "situs":
                current_addr = a.normalized_address
                county = a.county
                break
        summaries.append(
            PropertySummary(
                id=p.id,
                property_type=p.property_type,
                address=current_addr,
                county=county,
                created_at=p.created_at,
            )
        )
    return summaries


@router.get("/properties/{property_id}", response_model=PropertyResponse)
async def get_property(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get a property by ID with all addresses and identifiers."""
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses), selectinload(Property.parcel_identifiers))
        .where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.delete("/properties/{property_id}", status_code=204)
async def delete_property(property_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a property."""
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    await db.delete(prop)


@router.post("/properties/ingest", response_model=PropertyIngestResponse, status_code=201)
async def ingest_property(body: PropertyIngestRequest, db: AsyncSession = Depends(get_db)):
    """Ingest a property from a listing URL or manual address.

    If a URL is provided, scrapes the listing page and extracts property data.
    If only an address is provided, creates the property without scraping.
    """
    from pipa.services.listing_ingest import ListingIngestService

    config = get_config()
    service = ListingIngestService(
        storage_dir=config.storage_dir,
        headless=config.scrapers.playwright_headless,
    )

    try:
        if body.url:
            # Validate URL source before attempting scrape
            source = service.detect_source(body.url)
            if source == "unknown":
                raise HTTPException(
                    status_code=400,
                    detail="URL must be from zillow.com, redfin.com, or realtor.com",
                )

            prop, snapshot = await service.ingest_from_url(db, body.url)
            return PropertyIngestResponse(
                property=PropertyResponse.model_validate(prop),
                snapshot={
                    "id": snapshot.id,
                    "property_id": snapshot.property_id,
                    "source_site": snapshot.source_site,
                    "listing_url": snapshot.listing_url,
                    "scraped_at": snapshot.scraped_at,
                    "parsed_fields": snapshot.parsed_fields,
                    "raw_html_path": snapshot.raw_html_path,
                    "screenshot_path": snapshot.screenshot_path,
                    "parser_version": snapshot.parser_version,
                    "created_at": snapshot.created_at,
                    "updated_at": snapshot.updated_at,
                },
            )
        elif body.address:
            # Manual address entry
            addr = body.address
            address_str = f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}"
            prop = await service.ingest_from_address(
                db, address_str, property_type=body.property_type
            )
            return PropertyIngestResponse(
                property=PropertyResponse.model_validate(prop),
                snapshot=None,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="At least one of 'url' or 'address' must be provided",
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to ingest property")
        raise HTTPException(status_code=500, detail="Failed to ingest property from listing")
    finally:
        await service.close()
