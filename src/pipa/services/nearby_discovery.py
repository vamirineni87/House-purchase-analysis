"""Nearby property discovery service — find spatially related properties.

Until full geometry support is available, discovery falls back to
address-based heuristics (same street, same zip code).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.nearby import NearbyRelationship
from pipa.models.property import AddressHistory, Property

logger = logging.getLogger(__name__)


class NearbyDiscoveryService:
    """Discovers spatial and logical relationships between properties."""

    # ------------------------------------------------------------------
    # Radius-based discovery
    # ------------------------------------------------------------------

    @staticmethod
    async def discover_nearby(
        db: AsyncSession,
        property_id: str,
        radius_feet: float = 2640.0,
    ) -> list[NearbyRelationship]:
        """Find properties within *radius_feet* of the subject property.

        Default radius is 2640 ft (0.5 miles).

        When geometry data is not available, this falls back to
        same-street + same-zip matching as a proxy for proximity.

        Returns newly created NearbyRelationship records.
        """
        subject_addr = await NearbyDiscoveryService._get_current_address(
            db, property_id
        )
        if subject_addr is None:
            logger.warning("No current address for property %s", property_id)
            return []

        # Stub: use same-zip-code as a proxy for radius
        candidates = await db.execute(
            select(AddressHistory).where(
                AddressHistory.zip_code == subject_addr.zip_code,
                AddressHistory.is_current.is_(True),
                AddressHistory.property_id != property_id,
            )
        )
        candidate_addrs = list(candidates.scalars().all())

        # Filter to same street as a tighter proxy
        subject_street = NearbyDiscoveryService._extract_street_name(
            subject_addr.normalized_address
        )
        same_street = [
            ca for ca in candidate_addrs
            if NearbyDiscoveryService._extract_street_name(ca.normalized_address) == subject_street
        ]

        now = datetime.now(timezone.utc)
        relationships: list[NearbyRelationship] = []

        for addr in same_street:
            # Skip if relationship already exists
            existing = await db.execute(
                select(NearbyRelationship).where(
                    NearbyRelationship.subject_property_id == property_id,
                    NearbyRelationship.related_property_id == addr.property_id,
                    NearbyRelationship.relationship_type == "same_street",
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            rel = NearbyRelationship(
                subject_property_id=property_id,
                related_property_id=addr.property_id,
                relationship_type="same_street",
                distance_feet=None,  # unknown without geometry
                is_current=True,
                computed_at=now,
            )
            db.add(rel)
            relationships.append(rel)

        # Also include all same-zip properties with a weaker relationship
        for addr in candidate_addrs:
            if addr in same_street:
                continue

            existing = await db.execute(
                select(NearbyRelationship).where(
                    NearbyRelationship.subject_property_id == property_id,
                    NearbyRelationship.related_property_id == addr.property_id,
                    NearbyRelationship.relationship_type == "within_500ft",
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            rel = NearbyRelationship(
                subject_property_id=property_id,
                related_property_id=addr.property_id,
                relationship_type="within_500ft",
                distance_feet=None,
                is_current=True,
                computed_at=now,
            )
            db.add(rel)
            relationships.append(rel)

        await db.flush()

        logger.info(
            "Discovered %d nearby relationships for property %s",
            len(relationships),
            property_id,
        )
        return relationships

    # ------------------------------------------------------------------
    # Subdivision discovery
    # ------------------------------------------------------------------

    @staticmethod
    async def discover_same_subdivision(
        db: AsyncSession,
        property_id: str,
    ) -> list[NearbyRelationship]:
        """Find properties in the same subdivision.

        Stub: matches on same street name + same zip code as a proxy
        until subdivision data is available from plat records.
        """
        subject_addr = await NearbyDiscoveryService._get_current_address(
            db, property_id
        )
        if subject_addr is None:
            return []

        subject_street = NearbyDiscoveryService._extract_street_name(
            subject_addr.normalized_address
        )

        candidates = await db.execute(
            select(AddressHistory).where(
                AddressHistory.zip_code == subject_addr.zip_code,
                AddressHistory.is_current.is_(True),
                AddressHistory.property_id != property_id,
            )
        )
        candidate_addrs = list(candidates.scalars().all())

        same_subdivision = [
            ca for ca in candidate_addrs
            if NearbyDiscoveryService._extract_street_name(ca.normalized_address) == subject_street
        ]

        now = datetime.now(timezone.utc)
        relationships: list[NearbyRelationship] = []

        for addr in same_subdivision:
            existing = await db.execute(
                select(NearbyRelationship).where(
                    NearbyRelationship.subject_property_id == property_id,
                    NearbyRelationship.related_property_id == addr.property_id,
                    NearbyRelationship.relationship_type == "same_subdivision",
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            rel = NearbyRelationship(
                subject_property_id=property_id,
                related_property_id=addr.property_id,
                relationship_type="same_subdivision",
                distance_feet=None,
                is_current=True,
                computed_at=now,
            )
            db.add(rel)
            relationships.append(rel)

        await db.flush()
        return relationships

    # ------------------------------------------------------------------
    # Adjacent discovery
    # ------------------------------------------------------------------

    @staticmethod
    async def discover_adjacent(
        db: AsyncSession,
        property_id: str,
    ) -> list[NearbyRelationship]:
        """Find properties adjacent to the subject.

        Stub: uses same street + sequential house numbers as a proxy
        until parcel geometry is available.
        """
        subject_addr = await NearbyDiscoveryService._get_current_address(
            db, property_id
        )
        if subject_addr is None:
            return []

        subject_street = NearbyDiscoveryService._extract_street_name(
            subject_addr.normalized_address
        )
        subject_number = NearbyDiscoveryService._extract_house_number(
            subject_addr.normalized_address
        )

        if subject_number is None:
            return []

        candidates = await db.execute(
            select(AddressHistory).where(
                AddressHistory.zip_code == subject_addr.zip_code,
                AddressHistory.is_current.is_(True),
                AddressHistory.property_id != property_id,
            )
        )
        candidate_addrs = list(candidates.scalars().all())

        now = datetime.now(timezone.utc)
        relationships: list[NearbyRelationship] = []

        for addr in candidate_addrs:
            cand_street = NearbyDiscoveryService._extract_street_name(
                addr.normalized_address
            )
            if cand_street != subject_street:
                continue

            cand_number = NearbyDiscoveryService._extract_house_number(
                addr.normalized_address
            )
            if cand_number is None:
                continue

            # Consider adjacent if house numbers are within 4 of each other
            if abs(cand_number - subject_number) > 4:
                continue

            existing = await db.execute(
                select(NearbyRelationship).where(
                    NearbyRelationship.subject_property_id == property_id,
                    NearbyRelationship.related_property_id == addr.property_id,
                    NearbyRelationship.relationship_type == "adjacent",
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            rel = NearbyRelationship(
                subject_property_id=property_id,
                related_property_id=addr.property_id,
                relationship_type="adjacent",
                distance_feet=None,
                is_current=True,
                computed_at=now,
            )
            db.add(rel)
            relationships.append(rel)

        await db.flush()
        return relationships

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_current_address(
        db: AsyncSession,
        property_id: str,
    ) -> Optional[AddressHistory]:
        """Load the current situs address for a property."""
        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.property_id == property_id,
                AddressHistory.is_current.is_(True),
                AddressHistory.address_type == "situs",
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _extract_street_name(normalized_address: str) -> str:
        """Extract the street name from a normalized address.

        Strips the house number (first token) and everything after
        the first comma.
        """
        # Take everything before the first comma
        before_comma = normalized_address.split(",")[0].strip()
        parts = before_comma.split()
        if len(parts) <= 1:
            return before_comma
        # Drop leading house number
        return " ".join(parts[1:])

    @staticmethod
    def _extract_house_number(normalized_address: str) -> Optional[int]:
        """Extract the numeric house number from a normalized address."""
        before_comma = normalized_address.split(",")[0].strip()
        parts = before_comma.split()
        if not parts:
            return None
        try:
            return int(parts[0])
        except ValueError:
            return None
