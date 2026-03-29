"""FBI Crime Data Explorer API client."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)

# The FBI Crime Data API uses a publicly available API key
_PUBLIC_API_KEY = "iiHnOKfno2Mgkt5AynpvPpUQTEyxE77jo1RU8PIv"


class FBICrimeClient(BaseClient):
    """Client for the FBI Crime Data Explorer API.

    API docs: https://crime-data-explorer.fr.cloud.gov/pages/docApi
    Uses the public API key provided by the FBI for open data access.
    """

    source_name = "fbi_crime"
    base_url = "https://api.usa.gov/crime/fbi/sapi"

    def __init__(
        self,
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 168,  # 1 week — crime data is updated infrequently
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=_PUBLIC_API_KEY,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    async def get_state_crime(
        self,
        state_abbr: str,
        year: int | None = None,
    ) -> dict | None:
        """Fetch crime estimates for a US state.

        Args:
            state_abbr: Two-letter state abbreviation (e.g. ``"VA"``).
            year: Optional year to filter results.

        Returns:
            Crime data dict, or ``None`` on failure.
        """
        params: dict = {"api_key": self.api_key}
        if year is not None:
            params["year"] = year

        return await self.get(f"/api/estimates/{state_abbr}", params=params)

    async def get_agency_crime(
        self,
        ori: str,
        offense: str = "violent-crime",
    ) -> dict | None:
        """Fetch crime data for a specific agency by ORI code.

        Args:
            ori: Agency ORI code (e.g. ``"VA0590000"`` for Fairfax County PD).
            offense: Offense category (e.g. ``"violent-crime"``, ``"property-crime"``).

        Returns:
            Crime data dict, or ``None`` on failure.
        """
        params: dict = {"api_key": self.api_key}
        return await self.get(
            f"/api/summarized/agency/{ori}/{offense}", params=params
        )
