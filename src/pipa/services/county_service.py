"""County data ingestion and retrieval service.

Orchestrates GIS lookups and scraper calls, stores results in
assessment, permit, and deed tables.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.assessment import AssessmentSnapshot
from pipa.models.deed import DeedRecord
from pipa.models.permit import PermitRecord
from pipa.models.property import Property
from pipa.schemas.county import CountyRefreshResult

logger = logging.getLogger(__name__)


class CountyService:
    """Fetches, caches, and returns county data for a property."""

    # ------------------------------------------------------------------
    # Refresh — orchestrates all county data sources
    # ------------------------------------------------------------------

    @staticmethod
    async def refresh_county_data(
        db: AsyncSession,
        property_id: str,
    ) -> CountyRefreshResult:
        """Fetch fresh county data and upsert into the database.

        In production this would call GIS ArcGIS REST endpoints and
        county scraper modules.  For now it is a stub that returns
        counts of whatever already exists.
        """
        result = CountyRefreshResult(property_id=property_id)

        # Verify property exists
        prop_result = await db.execute(
            select(Property).where(Property.id == property_id)
        )
        prop = prop_result.scalar_one_or_none()
        if prop is None:
            result.errors.append("Property not found")
            return result

        # TODO: call Fairfax/Loudoun GIS API clients here
        # TODO: call county scraper modules here
        # For now, count existing records as a placeholder
        assessments = await db.execute(
            select(AssessmentSnapshot).where(
                AssessmentSnapshot.property_id == property_id
            )
        )
        result.assessments_fetched = len(list(assessments.scalars().all()))

        permits = await db.execute(
            select(PermitRecord).where(
                PermitRecord.property_id == property_id
            )
        )
        result.permits_fetched = len(list(permits.scalars().all()))

        deeds = await db.execute(
            select(DeedRecord).where(
                DeedRecord.property_id == property_id
            )
        )
        result.deeds_fetched = len(list(deeds.scalars().all()))

        logger.info(
            "County refresh for %s: %d assessments, %d permits, %d deeds",
            property_id,
            result.assessments_fetched,
            result.permits_fetched,
            result.deeds_fetched,
        )

        return result

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    @staticmethod
    async def get_assessments(
        db: AsyncSession,
        property_id: str,
    ) -> list[AssessmentSnapshot]:
        """Return all assessment snapshots for a property, newest first."""
        result = await db.execute(
            select(AssessmentSnapshot)
            .where(AssessmentSnapshot.property_id == property_id)
            .order_by(AssessmentSnapshot.tax_year.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_permits(
        db: AsyncSession,
        property_id: str,
    ) -> list[PermitRecord]:
        """Return all permit records for a property, newest first."""
        result = await db.execute(
            select(PermitRecord)
            .where(PermitRecord.property_id == property_id)
            .order_by(PermitRecord.issue_date.desc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_deeds(
        db: AsyncSession,
        property_id: str,
    ) -> list[DeedRecord]:
        """Return all deed records for a property, newest first."""
        result = await db.execute(
            select(DeedRecord)
            .where(DeedRecord.property_id == property_id)
            .order_by(DeedRecord.sale_date.desc().nullslast())
        )
        return list(result.scalars().all())
