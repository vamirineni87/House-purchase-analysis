"""Walk Score API client for walkability, transit, and bike scores."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)


class WalkScoreClient(BaseClient):
    """Client for the Walk Score API — walkability, transit, and bike scores.

    API docs: https://www.walkscore.com/professional/api.php
    """

    source_name = "walkscore"
    base_url = "https://api.walkscore.com"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 168,  # 1 week — scores change rarely
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    async def get_score(
        self,
        lat: float,
        lon: float,
        address: str,
    ) -> dict | None:
        """Fetch Walk Score, Transit Score, and Bike Score for a location.

        Args:
            lat: Latitude of the location.
            lon: Longitude of the location.
            address: Street address of the location.

        Returns:
            Score data dict with keys like ``walkscore``, ``transit``,
            ``bike``, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {
            "format": "json",
            "lat": lat,
            "lon": lon,
            "address": address,
            "wsapikey": self.api_key,
            "transit": 1,
            "bike": 1,
        }
        return await self.get("/score", params=params)
