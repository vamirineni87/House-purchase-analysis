"""Property CRUD and watchlist management service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.property import AddressHistory, Property
from pipa.models.user import WatchlistEntry
from pipa.utils.geo import detect_county, normalize_address


class PropertyService:
    """Encapsulates property CRUD and watchlist operations."""

    # ------------------------------------------------------------------
    # Property CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_property(
        db: AsyncSession,
        *,
        street: str,
        city: str,
        state: str = "VA",
        zip_code: str = "",
        county: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        property_type: str = "single_family",
    ) -> Property:
        """Create a new property with its primary address."""
        county = county or detect_county(city, state, zip_code)

        prop = Property(property_type=property_type)
        db.add(prop)
        await db.flush()

        raw = f"{street}, {city}, {state} {zip_code}"
        address = AddressHistory(
            property_id=prop.id,
            address_type="situs",
            normalized_address=normalize_address(raw),
            raw_address=raw,
            city=city,
            state=state,
            zip_code=zip_code,
            county=county,
            latitude=latitude,
            longitude=longitude,
            is_current=True,
            valid_from=datetime.now(timezone.utc),
        )
        db.add(address)
        await db.flush()

        result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == prop.id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_property(
        db: AsyncSession,
        property_id: str,
    ) -> Optional[Property]:
        """Fetch a property by ID with addresses and identifiers loaded."""
        result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == property_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_properties(
        db: AsyncSession,
        *,
        county: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> list[Property]:
        """List properties with optional filters."""
        query = (
            select(Property)
            .options(selectinload(Property.addresses))
            .order_by(Property.created_at.desc())
        )

        if property_type:
            query = query.where(Property.property_type == property_type)

        result = await db.execute(query)
        properties = list(result.scalars().all())

        # Post-filter by county (requires inspecting loaded addresses)
        if county:
            filtered = []
            for p in properties:
                for addr in p.addresses:
                    if addr.is_current and addr.county and addr.county.lower() == county.lower():
                        filtered.append(p)
                        break
            return filtered

        return properties

    # ------------------------------------------------------------------
    # Watchlist
    # ------------------------------------------------------------------

    @staticmethod
    async def add_to_watchlist(
        db: AsyncSession,
        user_id: str,
        property_id: str,
        stage: str = "researching",
        priority: int = 0,
    ) -> WatchlistEntry:
        """Add a property to the user's watchlist. Raises if duplicate."""
        existing = await db.execute(
            select(WatchlistEntry).where(
                WatchlistEntry.user_id == user_id,
                WatchlistEntry.property_id == property_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Property already on watchlist")

        entry = WatchlistEntry(
            user_id=user_id,
            property_id=property_id,
            stage=stage,
            priority=priority,
        )
        db.add(entry)
        await db.flush()
        return entry

    @staticmethod
    async def update_stage(
        db: AsyncSession,
        entry_id: str,
        stage: str,
    ) -> Optional[WatchlistEntry]:
        """Update the kanban stage of a watchlist entry."""
        result = await db.execute(
            select(WatchlistEntry).where(WatchlistEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        entry.stage = stage
        entry.stage_changed_at = datetime.now(timezone.utc)
        return entry
