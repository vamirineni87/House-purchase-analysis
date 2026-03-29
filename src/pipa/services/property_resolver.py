"""Property resolver service — find or create properties by address/parcel."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.property import AddressHistory, ParcelIdentifier, Property
from pipa.services.property_import import PropertyImportService
from pipa.utils.geo import normalize_address

logger = logging.getLogger(__name__)


class PropertyResolverService:
    """Resolves properties by address or parcel, creating if needed."""

    # ------------------------------------------------------------------
    # Resolve by address
    # ------------------------------------------------------------------

    @staticmethod
    async def resolve_by_address(
        db: AsyncSession,
        normalized_address: str,
    ) -> Optional[Property]:
        """Find an existing property whose current address matches.

        The comparison is made against the ``normalized_address`` column
        on current situs addresses.

        Returns the Property with addresses loaded, or None.
        """
        target = normalize_address(normalized_address)

        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.normalized_address == target,
                AddressHistory.is_current.is_(True),
            )
        )
        addr = result.scalar_one_or_none()
        if addr is None:
            return None

        prop_result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == addr.property_id)
        )
        return prop_result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Resolve by parcel
    # ------------------------------------------------------------------

    @staticmethod
    async def resolve_by_parcel(
        db: AsyncSession,
        county: str,
        parcel_number: str,
    ) -> Optional[Property]:
        """Find an existing property by county + parcel identifier.

        Searches ``ParcelIdentifier`` for a current entry matching
        the county and identifier value.

        Returns the Property with addresses loaded, or None.
        """
        result = await db.execute(
            select(ParcelIdentifier).where(
                ParcelIdentifier.county == county.lower(),
                ParcelIdentifier.identifier_type == "parcel_number",
                ParcelIdentifier.identifier_value == parcel_number,
                ParcelIdentifier.is_current.is_(True),
            )
        )
        pid = result.scalar_one_or_none()
        if pid is None:
            return None

        prop_result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == pid.property_id)
        )
        return prop_result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Resolve or create
    # ------------------------------------------------------------------

    @staticmethod
    async def resolve_or_create(
        db: AsyncSession,
        address_str: str,
        property_type: str = "single_family",
    ) -> tuple[Property, bool]:
        """Find a property by address, or create it if it does not exist.

        Returns a tuple of ``(property, is_new)`` where *is_new* is True
        when the property was freshly created.
        """
        existing = await PropertyResolverService.resolve_by_address(
            db, address_str
        )
        if existing is not None:
            logger.debug("Resolved existing property %s for %s", existing.id, address_str)
            return existing, False

        prop = await PropertyImportService.import_property(
            db, address_str, property_type=property_type
        )
        logger.info("Created new property %s for %s", prop.id, address_str)
        return prop, True
