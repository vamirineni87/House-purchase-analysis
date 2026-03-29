"""Property import service — create properties from address strings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.property import AddressHistory, Property
from pipa.models.user import User, WatchlistEntry
from pipa.utils.geo import detect_county, normalize_address, parse_address

logger = logging.getLogger(__name__)


class PropertyImportService:
    """Creates properties from raw address strings, wiring up related records."""

    # ------------------------------------------------------------------
    # Import from full address string
    # ------------------------------------------------------------------

    @staticmethod
    async def import_property(
        db: AsyncSession,
        address_str: str,
        property_type: str = "single_family",
    ) -> Property:
        """Parse an address string and create a fully-wired Property.

        Steps:
        1. Parse address components from the string.
        2. Detect county from city/state/zip heuristics.
        3. Create Property + AddressHistory.
        4. Ensure a default user and watchlist entry exist.

        Returns the created Property with addresses loaded.
        """
        parts = parse_address(address_str)

        return await PropertyImportService.import_from_address_parts(
            db,
            street=parts["street"],
            city=parts["city"],
            state=parts.get("state", "VA"),
            zip_code=parts.get("zip_code", ""),
            property_type=property_type,
        )

    # ------------------------------------------------------------------
    # Import from pre-parsed address parts
    # ------------------------------------------------------------------

    @staticmethod
    async def import_from_address_parts(
        db: AsyncSession,
        street: str,
        city: str,
        state: str = "VA",
        zip_code: str = "",
        property_type: str = "single_family",
    ) -> Property:
        """Create a Property from explicit address components.

        Also creates a default user and watchlist entry if they do not
        already exist.

        Returns the created Property with addresses loaded.
        """
        county = detect_county(city, state, zip_code)

        # Create the property
        prop = Property(property_type=property_type)
        db.add(prop)
        await db.flush()

        raw = f"{street}, {city}, {state} {zip_code}".strip()
        address = AddressHistory(
            property_id=prop.id,
            address_type="situs",
            normalized_address=normalize_address(raw),
            raw_address=raw,
            city=city,
            state=state,
            zip_code=zip_code,
            county=county,
            is_current=True,
            valid_from=datetime.now(timezone.utc),
        )
        db.add(address)
        await db.flush()

        # Ensure a default user exists
        default_user = await PropertyImportService._get_or_create_default_user(db)

        # Add to watchlist if not already present
        existing_entry = await db.execute(
            select(WatchlistEntry).where(
                WatchlistEntry.user_id == default_user.id,
                WatchlistEntry.property_id == prop.id,
            )
        )
        if existing_entry.scalar_one_or_none() is None:
            entry = WatchlistEntry(
                user_id=default_user.id,
                property_id=prop.id,
                stage="researching",
                priority=0,
            )
            db.add(entry)
            await db.flush()

        logger.info(
            "Imported property %s at %s (county=%s)",
            prop.id,
            raw,
            county,
        )

        # Reload with relationships
        result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == prop.id)
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_or_create_default_user(db: AsyncSession) -> User:
        """Return the default user, creating one if needed."""
        result = await db.execute(
            select(User).where(User.email == "default@pipa.local")
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = User(
            email="default@pipa.local",
            display_name="Default User",
        )
        db.add(user)
        await db.flush()
        return user
