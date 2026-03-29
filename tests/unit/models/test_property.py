"""Tests for property model creation and identity handling."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from pipa.models.property import AddressHistory, Parcel, ParcelIdentifier, Property


@pytest.mark.asyncio
async def test_create_property(db_session):
    """Can create a property with basic fields."""
    prop = Property(property_type="single_family")
    db_session.add(prop)
    await db_session.flush()

    assert prop.id is not None
    assert len(prop.id) == 36  # UUID format
    assert prop.property_type == "single_family"


@pytest.mark.asyncio
async def test_property_with_address(db_session):
    """Can create a property with an address."""
    prop = Property(property_type="townhouse")
    db_session.add(prop)
    await db_session.flush()

    addr = AddressHistory(
        property_id=prop.id,
        address_type="situs",
        normalized_address="123 MAIN ST, FAIRFAX, VA 22030",
        city="Fairfax",
        state="VA",
        zip_code="22030",
        county="fairfax",
        is_current=True,
    )
    db_session.add(addr)
    await db_session.flush()

    result = await db_session.execute(
        select(AddressHistory).where(AddressHistory.property_id == prop.id)
    )
    addresses = result.scalars().all()
    assert len(addresses) == 1
    assert addresses[0].county == "fairfax"
    assert addresses[0].is_current is True


@pytest.mark.asyncio
async def test_multiple_parcel_identifiers(db_session):
    """Property can have multiple parcel identifiers of different types."""
    prop = Property()
    db_session.add(prop)
    await db_session.flush()

    ids = [
        ParcelIdentifier(
            property_id=prop.id,
            county="fairfax",
            identifier_type="parcel_number",
            identifier_value="0572 01 0048",
            is_current=True,
        ),
        ParcelIdentifier(
            property_id=prop.id,
            county="fairfax",
            identifier_type="tax_map_number",
            identifier_value="057-2-01-0048",
            is_current=True,
        ),
        ParcelIdentifier(
            property_id=prop.id,
            county="fairfax",
            identifier_type="GIS_PIN",
            identifier_value="0572010048",
            is_current=True,
        ),
    ]
    db_session.add_all(ids)
    await db_session.flush()

    result = await db_session.execute(
        select(ParcelIdentifier).where(ParcelIdentifier.property_id == prop.id)
    )
    identifiers = result.scalars().all()
    assert len(identifiers) == 3
    types = {i.identifier_type for i in identifiers}
    assert types == {"parcel_number", "tax_map_number", "GIS_PIN"}


@pytest.mark.asyncio
async def test_address_history_tracking(db_session):
    """Can track address changes over time."""
    prop = Property()
    db_session.add(prop)
    await db_session.flush()

    # Original address
    old_addr = AddressHistory(
        property_id=prop.id,
        address_type="situs",
        normalized_address="100 OLD RD, FAIRFAX, VA 22030",
        is_current=False,
    )
    # New address after renumber
    new_addr = AddressHistory(
        property_id=prop.id,
        address_type="situs",
        normalized_address="200 NEW BLVD, FAIRFAX, VA 22030",
        is_current=True,
    )
    db_session.add_all([old_addr, new_addr])
    await db_session.flush()

    result = await db_session.execute(
        select(AddressHistory)
        .where(AddressHistory.property_id == prop.id, AddressHistory.is_current == True)
    )
    current = result.scalars().all()
    assert len(current) == 1
    assert "NEW BLVD" in current[0].normalized_address
