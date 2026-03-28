from typing import Optional

from .base import ApiClient


class CensusClient(ApiClient):
    """Client for the US Census Bureau American Community Survey API."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        super().__init__(
            base_url="https://api.census.gov/data",
            api_key=api_key,
            timeout=timeout,
        )

    async def get_demographics(
        self,
        state_fips: str,
        county_fips: str | None = None,
    ) -> Optional[dict]:
        """Fetch demographic data from the ACS 5-year estimates.

        Retrieves total population (B01001_001E), median household income
        (B19013_001E), and median home value (B25077_001E).

        Args:
            state_fips: 2-digit state FIPS code (e.g. "06" for California).
            county_fips: Optional 3-digit county FIPS code. If omitted,
                returns state-level data.

        Returns:
            Dict with demographic fields, or None on failure.
        """
        if not self.api_key:
            return None

        variables = "B01001_001E,B19013_001E,B25077_001E"

        params: dict = {
            "get": variables,
            "key": self.api_key,
        }

        if county_fips:
            params["for"] = f"county:{county_fips}"
            params["in"] = f"state:{state_fips}"
        else:
            params["for"] = f"state:{state_fips}"

        data = await self.get("2022/acs/acs5", params=params)
        if data is None:
            return None

        # Census API returns a list of lists: [[header1, header2, ...], [val1, val2, ...]]
        try:
            if isinstance(data, list) and len(data) >= 2:
                headers = data[0]
                values = data[1]
                return dict(zip(headers, values))
            return data if isinstance(data, dict) else None
        except (TypeError, ValueError):
            return None
