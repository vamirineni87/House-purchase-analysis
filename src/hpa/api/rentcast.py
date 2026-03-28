from typing import Optional

from .base import ApiClient


class RentCastClient(ApiClient):
    """Client for the RentCast API (property data and comparable sales)."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        super().__init__(
            base_url="https://api.rentcast.io/v1",
            api_key=api_key,
            timeout=timeout,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    async def get_property(self, address: str) -> Optional[dict]:
        """Fetch property details by street address.

        Args:
            address: Full street address of the property.

        Returns:
            Property data dict, or None on failure.
        """
        if not self.api_key:
            return None

        params = {"address": address}
        return await self.get("properties", params=params, headers=self._auth_headers())

    async def get_comparable_sales(
        self,
        address: str,
        radius: float = 1.0,
        limit: int = 10,
    ) -> Optional[list[dict]]:
        """Fetch comparable recent sales near a property.

        Args:
            address: Full street address of the subject property.
            radius: Search radius in miles.
            limit: Maximum number of comparables to return.

        Returns:
            List of comparable sale dicts, or None on failure.
        """
        if not self.api_key:
            return None

        params = {
            "address": address,
            "radius": radius,
            "limit": limit,
        }
        data = await self.get(
            "sales/comparables", params=params, headers=self._auth_headers()
        )
        if data is None:
            return None

        # The API may return a list directly or wrap it in a key.
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("comparables", data.get("results", [data]))
        return None
