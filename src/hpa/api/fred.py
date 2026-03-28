from typing import Optional

from .base import ApiClient

_SERIES_MAP = {
    30: "MORTGAGE30US",
    15: "MORTGAGE15US",
}


class FredClient(ApiClient):
    """Client for the FRED (Federal Reserve Economic Data) API."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        super().__init__(
            base_url="https://api.stlouisfed.org/fred",
            api_key=api_key,
            timeout=timeout,
        )

    async def get_current_rate(self, term_years: int = 30) -> Optional[float]:
        """Return the latest mortgage rate as a decimal (e.g. 0.065 for 6.5%).

        Args:
            term_years: 30 for 30-year fixed, 15 for 15-year fixed.

        Returns:
            The latest mortgage rate as a decimal, or None on failure.
        """
        if not self.api_key:
            return None

        series_id = _SERIES_MAP.get(term_years)
        if series_id is None:
            return None

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }

        data = await self.get("series/observations", params=params)
        if data is None:
            return None

        try:
            observations = data.get("observations", [])
            if not observations:
                return None
            value = float(observations[0]["value"])
            return value / 100.0
        except (KeyError, ValueError, IndexError, TypeError):
            return None
