"""Property CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_db
from pipa.models.property import AddressHistory, Property
from pipa.schemas.property import PropertyCreate, PropertyResponse, PropertySummary
from pipa.utils.geo import detect_county, normalize_address, parse_address

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
