"""Hazard profile service — natural hazard risk assessment."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.clients.static_data.epa_radon_zones import get_radon_zone
from pipa.clients.static_data.fema_nri import load_nri_for_county
from pipa.clients.static_data.va_tax_rates import get_tax_rate
from pipa.models.hazard import HazardProfile
from pipa.models.property import AddressHistory, Property

logger = logging.getLogger(__name__)


class HazardService:
    """Creates and enriches natural hazard risk profiles for properties."""

    # ------------------------------------------------------------------
    # Get or create
    # ------------------------------------------------------------------

    @staticmethod
    async def get_or_create_hazard_profile(
        db: AsyncSession,
        property_id: str,
    ) -> HazardProfile:
        """Return the hazard profile for a property, creating if needed.

        A freshly created profile will have all risk fields set to None
        until ``enrich_hazard_profile`` is called.
        """
        result = await db.execute(
            select(HazardProfile).where(
                HazardProfile.property_id == property_id
            )
        )
        profile = result.scalar_one_or_none()
        if profile is not None:
            return profile

        profile = HazardProfile(property_id=property_id)
        db.add(profile)
        await db.flush()

        logger.info("Created hazard profile for property %s", property_id)
        return profile

    # ------------------------------------------------------------------
    # Enrich from static data sources
    # ------------------------------------------------------------------

    @staticmethod
    async def enrich_hazard_profile(
        db: AsyncSession,
        property_id: str,
        county: Optional[str] = None,
        state: str = "VA",
    ) -> HazardProfile:
        """Populate a hazard profile from static reference data.

        Sources used:
        - EPA radon zone data
        - FEMA National Risk Index (NRI) county-level data
        - VA property tax rates (informational, stored in nri_data)

        If *county* is not supplied, it is resolved from the property's
        current address.
        """
        profile = await HazardService.get_or_create_hazard_profile(
            db, property_id
        )

        # Resolve county from address if not provided
        if county is None:
            county = await HazardService._resolve_county(db, property_id)

        if county is None:
            logger.warning(
                "Cannot enrich hazard profile for %s: county unknown",
                property_id,
            )
            return profile

        # EPA radon zone
        radon_zone = get_radon_zone(county, state)
        if radon_zone is not None:
            profile.radon_zone = str(radon_zone)
            # Map zone to a 0-1 risk score
            radon_risk_map = {1: 0.8, 2: 0.4, 3: 0.1}
            profile.radon_risk = radon_risk_map.get(radon_zone, 0.0)

        # FEMA NRI data
        nri = load_nri_for_county(county, state)
        profile.nri_data = nri

        # Extract specific hazard scores from NRI
        hazards = nri.get("hazards", {})

        flood_data = hazards.get("flooding", {})
        profile.flood_risk_score = flood_data.get("score")

        wildfire_data = hazards.get("wildfire", {})
        profile.wildfire_risk = wildfire_data.get("score")

        earthquake_data = hazards.get("earthquake", {})
        profile.earthquake_risk = earthquake_data.get("score")

        hurricane_data = hazards.get("hurricane", {})
        profile.hurricane_risk = hurricane_data.get("score")

        tornado_data = hazards.get("tornado", {})
        profile.tornado_risk = tornado_data.get("score")

        # Compute overall risk score as weighted average of key hazards
        risk_scores = [
            s for s in [
                profile.flood_risk_score,
                profile.wildfire_risk,
                profile.earthquake_risk,
                profile.hurricane_risk,
                profile.tornado_risk,
                profile.radon_risk * 100 if profile.radon_risk else None,
            ]
            if s is not None
        ]
        if risk_scores:
            profile.overall_risk_score = round(
                sum(risk_scores) / len(risk_scores), 1
            )

        # Store VA tax rate in NRI data for reference
        tax_rate = get_tax_rate(county)
        if tax_rate is not None and profile.nri_data is not None:
            # Avoid mutating the cached NRI dict
            profile.nri_data = {**profile.nri_data, "va_tax_rate_per_100": tax_rate}

        profile.last_updated = datetime.now(timezone.utc)
        await db.flush()

        logger.info(
            "Enriched hazard profile for property %s (county=%s, overall_risk=%.1f)",
            property_id,
            county,
            profile.overall_risk_score or 0.0,
        )
        return profile

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_county(
        db: AsyncSession,
        property_id: str,
    ) -> Optional[str]:
        """Resolve county from the property's current situs address."""
        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.property_id == property_id,
                AddressHistory.is_current.is_(True),
                AddressHistory.address_type == "situs",
            )
        )
        addr = result.scalar_one_or_none()
        if addr is not None and addr.county:
            return addr.county
        return None
