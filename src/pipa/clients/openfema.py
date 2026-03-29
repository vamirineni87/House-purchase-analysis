"""OpenFEMA API client for disaster and flood risk data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)


class OpenFEMAClient(BaseClient):
    """Client for the OpenFEMA API — disaster declarations and flood risk.

    API docs: https://www.fema.gov/about/openfema/api
    No API key required for public data.
    """

    source_name = "openfema"
    base_url = "https://www.fema.gov/api/open/v2"

    def __init__(
        self,
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 168,  # 1 week
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    async def get_flood_risk(self, zip_code: str) -> dict | None:
        """Fetch flood-related disaster declarations for a ZIP code area.

        Args:
            zip_code: 5-digit US ZIP code.

        Returns:
            Disaster declarations dict, or ``None`` on failure.
        """
        odata_filter = (
            f"designatedArea eq '{zip_code}' and "
            f"incidentType eq 'Flood'"
        )
        params = {
            "$filter": odata_filter,
            "$top": 10,
            "$orderby": "declarationDate desc",
        }
        return await self.get("/DisasterDeclarationsSummaries", params=params)

    async def get_disaster_history(
        self,
        state: str = "Virginia",
        limit: int = 25,
    ) -> dict | None:
        """Fetch recent disaster declarations for a state.

        Args:
            state: State name (e.g. ``"Virginia"``).
            limit: Maximum number of records.

        Returns:
            Disaster declarations dict, or ``None`` on failure.
        """
        params = {
            "$filter": f"state eq '{state}'",
            "$top": limit,
            "$orderby": "declarationDate desc",
        }
        return await self.get("/DisasterDeclarationsSummaries", params=params)

    async def get_nfip_policies(
        self,
        state: str = "VA",
        county: str | None = None,
    ) -> dict | None:
        """Fetch NFIP flood insurance policy statistics.

        Args:
            state: Two-letter state abbreviation.
            county: Optional county name to filter.

        Returns:
            Policy statistics dict, or ``None`` on failure.
        """
        odata_filter = f"propertyState eq '{state}'"
        if county:
            odata_filter += f" and countyCode eq '{county}'"

        params = {
            "$filter": odata_filter,
            "$top": 10,
        }
        return await self.get("/FimaNfipPolicies", params=params)
