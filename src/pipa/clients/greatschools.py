"""GreatSchools API client for school ratings and nearby schools."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)


class GreatSchoolsClient(BaseClient):
    """Client for the GreatSchools API — school ratings and nearby schools.

    API docs: https://www.greatschools.org/api/docs/main.page
    """

    source_name = "greatschools"
    base_url = "https://gs-api.greatschools.org"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 168,  # 1 week — school data changes rarely
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    async def get_nearby_schools(
        self,
        lat: float,
        lon: float,
        radius: int = 5,
        limit: int = 10,
    ) -> list[dict] | None:
        """Fetch nearby schools with ratings.

        Args:
            lat: Latitude of the location.
            lon: Longitude of the location.
            radius: Search radius in miles.
            limit: Maximum number of schools to return.

        Returns:
            List of school dicts, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {
            "lat": lat,
            "lon": lon,
            "radius": radius,
            "limit": limit,
            "key": self.api_key,
        }
        data = await self.get("/schools/nearby", params=params)
        if data is None:
            return None

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("schools", [])
        return None

    async def get_school_details(self, school_id: int) -> dict | None:
        """Fetch detailed info for a specific school.

        Args:
            school_id: GreatSchools school ID.

        Returns:
            School detail dict, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {"key": self.api_key}
        return await self.get(f"/schools/{school_id}", params=params)
