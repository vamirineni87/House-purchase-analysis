"""RentCast API client for property data and comparable sales."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)


class RentCastClient(BaseClient):
    """Client for the RentCast API — property data and comparable sales.

    API docs: https://developers.rentcast.io/reference
    """

    source_name = "rentcast"
    base_url = "https://api.rentcast.io/v1"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 2.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 24,
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

    async def get_property(self, address: str) -> dict | None:
        """Fetch property details by street address.

        Args:
            address: Full street address of the property.

        Returns:
            Property data dict, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {"address": address}
        return await self.get("/properties", params=params)

    async def get_comparable_sales(
        self,
        address: str,
        radius: float = 1.0,
        limit: int = 10,
    ) -> list[dict] | None:
        """Fetch comparable recent sales near a property.

        Args:
            address: Full street address of the subject property.
            radius: Search radius in miles.
            limit: Maximum number of comparables to return.

        Returns:
            List of comparable sale dicts, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {
            "address": address,
            "radius": radius,
            "limit": limit,
        }
        data = await self.get("/sales/comparables", params=params)
        if data is None:
            return None

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("comparables", data.get("results", [data]))
        return None

    async def get_rent_estimate(
        self,
        address: str,
        bedrooms: int | None = None,
        bathrooms: float | None = None,
        sqft: int | None = None,
    ) -> dict | None:
        """Get a rent estimate for a property.

        Args:
            address: Full street address.
            bedrooms: Number of bedrooms.
            bathrooms: Number of bathrooms.
            sqft: Square footage.

        Returns:
            Rent estimate dict, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params: dict = {"address": address}
        if bedrooms is not None:
            params["bedrooms"] = bedrooms
        if bathrooms is not None:
            params["bathrooms"] = bathrooms
        if sqft is not None:
            params["squareFootage"] = sqft

        return await self.get("/avm/rent/long-term", params=params)
