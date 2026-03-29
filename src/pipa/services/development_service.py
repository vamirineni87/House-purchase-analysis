"""Development case management service."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.development import DevelopmentCase

logger = logging.getLogger(__name__)


class DevelopmentService:
    """CRUD operations for nearby development and land-use cases."""

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    async def get_nearby_cases(
        db: AsyncSession,
        property_id: str,
    ) -> list[DevelopmentCase]:
        """Return all development cases linked to a property, newest first."""
        result = await db.execute(
            select(DevelopmentCase)
            .where(DevelopmentCase.property_id == property_id)
            .order_by(DevelopmentCase.hearing_date.desc().nullslast())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    async def add_case(
        db: AsyncSession,
        property_id: str,
        case_data: dict,
    ) -> DevelopmentCase:
        """Create a new development case linked to a property.

        *case_data* should contain keys matching ``DevelopmentCase``
        columns: ``case_number``, ``case_type``, and optionally
        ``applicant``, ``description``, ``distance_feet``, ``status``,
        ``hearing_date``, ``source``.
        """
        case = DevelopmentCase(
            property_id=property_id,
            case_number=case_data["case_number"],
            case_type=case_data["case_type"],
            applicant=case_data.get("applicant"),
            description=case_data.get("description"),
            distance_feet=case_data.get("distance_feet"),
            status=case_data.get("status"),
            hearing_date=case_data.get("hearing_date"),
            source=case_data.get("source", "manual"),
        )
        db.add(case)
        await db.flush()

        logger.info(
            "Added development case %s (%s) for property %s",
            case.case_number,
            case.case_type,
            property_id,
        )
        return case

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    async def update_case_status(
        db: AsyncSession,
        case_id: str,
        status: str,
    ) -> DevelopmentCase:
        """Update the status of an existing development case.

        Raises ``ValueError`` if the case is not found.
        """
        result = await db.execute(
            select(DevelopmentCase).where(DevelopmentCase.id == case_id)
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise ValueError(f"Development case {case_id} not found")

        case.status = status
        await db.flush()

        logger.info("Updated development case %s status to %s", case_id, status)
        return case
