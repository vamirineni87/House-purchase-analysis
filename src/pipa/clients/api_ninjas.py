"""API Ninjas client for property tax and miscellaneous data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)


class ApiNinjasClient(BaseClient):
    """Client for the API Ninjas property tax and related endpoints.

    API docs: https://api-ninjas.com/api
    """

    source_name = "api_ninjas"
    base_url = "https://api.api-ninjas.com/v1"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 168,  # 1 week
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    def _default_headers(self) -> dict[str, str]:
        headers = super()._default_headers()
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    async def get_property_tax(self, zip_code: str) -> dict | None:
        """Fetch property tax information for a ZIP code.

        Args:
            zip_code: 5-digit US ZIP code.

        Returns:
            Property tax data dict, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {"zip_code": zip_code}
        return await self.get("/propertytax", params=params)

    async def get_city_data(self, city: str) -> dict | None:
        """Fetch city-level data (population, density, etc.).

        Args:
            city: City name (e.g. ``"Fairfax"``).

        Returns:
            City data dict, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {"name": city}
        data = await self.get("/city", params=params)
        if data is None:
            return None

        # API returns a list; take first match
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None
