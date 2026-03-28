from typing import Optional

from .base import ApiClient


class WalkScoreClient(ApiClient):
    """Client for the Walk Score API."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        super().__init__(
            base_url="https://api.walkscore.com",
            api_key=api_key,
            timeout=timeout,
        )

    async def get_score(
        self,
        lat: float,
        lon: float,
        address: str,
    ) -> Optional[dict]:
        """Fetch Walk Score, Transit Score, and Bike Score for a location.

        Args:
            lat: Latitude of the location.
            lon: Longitude of the location.
            address: Street address of the location.

        Returns:
            Score data dict, or None on failure.
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
        return await self.get("score", params=params)
