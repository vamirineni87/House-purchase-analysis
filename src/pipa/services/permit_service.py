"""Permit service — permit retrieval and component inference."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.component import ComponentEvidence, ComponentSystem
from pipa.models.permit import PermitRecord

logger = logging.getLogger(__name__)

# Mapping of keywords in permit descriptions to component types.
# Each entry is (regex_pattern, component_type, default_lifespan_years).
_PERMIT_COMPONENT_PATTERNS: list[tuple[str, str, int]] = [
    (r"\broof(ing)?\b", "roof", 25),
    (r"\bhvac\b|\bair\s*condition(er|ing)\b|\bfurnace\b|\bheat(ing)?\s*(pump|system)\b", "hvac", 20),
    (r"\belectrical\b|\bpanel\b|\bwiring\b", "electrical_panel", 40),
    (r"\bplumb(ing)?\b|\bpipe\b|\bsewer\b", "plumbing", 50),
    (r"\bwater\s*heater\b|\bhot\s*water\b", "water_heater", 12),
    (r"\bwindow(s)?\b", "windows", 25),
    (r"\bsiding\b", "siding", 30),
    (r"\bdeck\b|\bporch\b|\bpatio\b", "deck", 20),
    (r"\bfoundation\b", "foundation", 75),
    (r"\bappliance(s)?\b|\bkitchen\b", "appliances", 15),
    (r"\bdrain(age)?\b|\bgutter(s)?\b|\bgrading\b", "drainage", 20),
]


class PermitService:
    """Retrieves permits and infers component systems from permit data."""

    # ------------------------------------------------------------------
    # Permit retrieval
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Component inference from permits
    # ------------------------------------------------------------------

    @staticmethod
    async def infer_components(
        db: AsyncSession,
        property_id: str,
    ) -> list[dict]:
        """Scan permits for keywords and create/update ComponentSystem entries.

        For each permit that matches a known component pattern, this
        method creates or updates a ``ComponentSystem`` row and records
        a ``ComponentEvidence`` row linking back to the permit.

        Returns a list of dicts describing the inferred components.
        """
        permits = await PermitService.get_permits(db, property_id)
        if not permits:
            return []

        inferred: list[dict] = []

        for permit in permits:
            searchable = " ".join(
                filter(None, [permit.type, permit.description])
            ).lower()

            for pattern, component_type, lifespan in _PERMIT_COMPONENT_PATTERNS:
                if not re.search(pattern, searchable, re.IGNORECASE):
                    continue

                install_year = (
                    permit.issue_date.year if permit.issue_date else None
                )

                # Find or create the component system
                component = await PermitService._get_or_create_component(
                    db,
                    property_id=property_id,
                    component_type=component_type,
                    install_year=install_year,
                    lifespan=lifespan,
                    cost=permit.estimated_cost,
                )

                # Record evidence linking this permit
                evidence = ComponentEvidence(
                    component_system_id=component.id,
                    source="permit",
                    source_date=permit.issue_date,
                    extracted_value=(
                        f"Permit {permit.permit_number}: {permit.description or permit.type}"
                    ),
                    confidence_score=0.8,
                )
                db.add(evidence)

                inferred.append({
                    "component_type": component_type,
                    "install_year": install_year,
                    "permit_number": permit.permit_number,
                    "permit_description": permit.description,
                    "estimated_cost": permit.estimated_cost,
                })

        await db.flush()

        logger.info(
            "Inferred %d component entries from %d permits for property %s",
            len(inferred),
            len(permits),
            property_id,
        )
        return inferred

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_or_create_component(
        db: AsyncSession,
        property_id: str,
        component_type: str,
        install_year: Optional[int],
        lifespan: int,
        cost: Optional[float],
    ) -> ComponentSystem:
        """Find an existing ComponentSystem or create a new one.

        If an existing component is found but the permit has a newer
        install year, the component is updated.
        """
        result = await db.execute(
            select(ComponentSystem).where(
                ComponentSystem.property_id == property_id,
                ComponentSystem.component_type == component_type,
            )
        )
        component = result.scalar_one_or_none()

        if component is not None:
            # Update if the permit gives a more recent install year
            if install_year and (
                component.estimated_install_year is None
                or install_year > component.estimated_install_year
            ):
                component.estimated_install_year = install_year
                component.confidence = "confirmed"
            if cost and (
                component.estimated_replacement_cost is None
                or cost > component.estimated_replacement_cost
            ):
                component.estimated_replacement_cost = cost
            return component

        component = ComponentSystem(
            property_id=property_id,
            component_type=component_type,
            estimated_install_year=install_year,
            expected_lifespan=lifespan,
            estimated_replacement_cost=cost,
            confidence="confirmed" if install_year else "estimated",
        )
        db.add(component)
        await db.flush()
        return component
