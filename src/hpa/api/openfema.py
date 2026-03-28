from typing import Optional

from .base import ApiClient


class OpenFEMAClient(ApiClient):
    """Client for the OpenFEMA API (disaster and flood risk data)."""

    def __init__(self, timeout: float = 30.0):
        super().__init__(
            base_url="https://www.fema.gov/api/open/v2",
            timeout=timeout,
        )

    async def get_flood_risk(self, zip_code: str) -> Optional[dict]:
        """Fetch flood-related disaster declarations for a ZIP code.

        Args:
            zip_code: 5-digit US ZIP code.

        Returns:
            Disaster declarations dict, or None on failure.
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
        return await self.get("DisasterDeclarationsSummaries", params=params)
