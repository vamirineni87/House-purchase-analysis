from typing import Optional

from .base import ApiClient


class ApiNinjasClient(ApiClient):
    """Client for the API Ninjas property tax endpoint."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        super().__init__(
            base_url="https://api.api-ninjas.com/v1",
            api_key=api_key,
            timeout=timeout,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    async def get_property_tax(self, zip_code: str) -> Optional[dict]:
        """Fetch property tax information for a ZIP code.

        Args:
            zip_code: 5-digit US ZIP code.

        Returns:
            Property tax data dict, or None on failure.
        """
        if not self.api_key:
            return None

        params = {"zip_code": zip_code}
        return await self.get(
            "propertytax", params=params, headers=self._auth_headers()
        )
