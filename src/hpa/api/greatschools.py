from typing import Optional

from .base import ApiClient


class GreatSchoolsClient(ApiClient):
    """Client for the GreatSchools API (school ratings)."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        super().__init__(
            base_url="https://gs-api.greatschools.org",
            api_key=api_key,
            timeout=timeout,
        )

    async def get_nearby_schools(
        self,
        lat: float,
        lon: float,
        radius: int = 5,
        limit: int = 10,
    ) -> Optional[list[dict]]:
        """Fetch nearby schools with ratings.

        Args:
            lat: Latitude of the location.
            lon: Longitude of the location.
            radius: Search radius in miles.
            limit: Maximum number of schools to return.

        Returns:
            List of school dicts, or None on failure.
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
        data = await self.get("schools/nearby", params=params)
        if data is None:
            return None

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("schools", [])
        return None
