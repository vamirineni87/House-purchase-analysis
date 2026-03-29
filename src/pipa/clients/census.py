"""US Census Bureau ACS API client for demographic data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)

# Common ACS 5-year variable codes
ACS_VARIABLES = {
    "total_population": "B01001_001E",
    "median_household_income": "B19013_001E",
    "median_home_value": "B25077_001E",
    "median_gross_rent": "B25064_001E",
    "owner_occupied_units": "B25003_002E",
    "renter_occupied_units": "B25003_003E",
    "median_age": "B01002_001E",
    "households_with_children": "B11005_002E",
}

# Virginia FIPS = 51, Fairfax County = 059, Loudoun County = 107
VA_FIPS = "51"
FAIRFAX_COUNTY_FIPS = "059"
LOUDOUN_COUNTY_FIPS = "107"


class CensusClient(BaseClient):
    """Client for the US Census Bureau American Community Survey API.

    API docs: https://www.census.gov/data/developers/data-sets/acs-5year.html
    """

    source_name = "census"
    base_url = "https://api.census.gov/data"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 720,  # 30 days — ACS data is annual
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    async def get_demographics(
        self,
        state_fips: str = VA_FIPS,
        county_fips: str | None = None,
    ) -> dict | None:
        """Fetch demographic data from the ACS 5-year estimates.

        Retrieves total population, median household income, and median
        home value.

        Args:
            state_fips: 2-digit state FIPS code (default: ``"51"`` for Virginia).
            county_fips: Optional 3-digit county FIPS code. If omitted,
                returns state-level data.

        Returns:
            Dict with demographic fields, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        variables = ",".join([
            ACS_VARIABLES["total_population"],
            ACS_VARIABLES["median_household_income"],
            ACS_VARIABLES["median_home_value"],
        ])

        params: dict = {
            "get": variables,
            "key": self.api_key,
        }

        if county_fips:
            params["for"] = f"county:{county_fips}"
            params["in"] = f"state:{state_fips}"
        else:
            params["for"] = f"state:{state_fips}"

        data = await self.get("/2022/acs/acs5", params=params)
        if data is None:
            return None

        # Census API returns [[header1, ...], [val1, ...]]
        try:
            if isinstance(data, list) and len(data) >= 2:
                headers = data[0]
                values = data[1]
                return dict(zip(headers, values))
            return data if isinstance(data, dict) else None
        except (TypeError, ValueError):
            return None

    async def get_extended_demographics(
        self,
        state_fips: str = VA_FIPS,
        county_fips: str | None = None,
    ) -> dict | None:
        """Fetch extended demographic data including rent and housing info.

        Args:
            state_fips: 2-digit state FIPS code.
            county_fips: Optional 3-digit county FIPS code.

        Returns:
            Dict with all ACS variable values, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        variables = ",".join(ACS_VARIABLES.values())

        params: dict = {
            "get": variables,
            "key": self.api_key,
        }

        if county_fips:
            params["for"] = f"county:{county_fips}"
            params["in"] = f"state:{state_fips}"
        else:
            params["for"] = f"state:{state_fips}"

        data = await self.get("/2022/acs/acs5", params=params)
        if data is None:
            return None

        try:
            if isinstance(data, list) and len(data) >= 2:
                headers = data[0]
                values = data[1]
                raw = dict(zip(headers, values))
                # Map to friendly names
                reverse_map = {v: k for k, v in ACS_VARIABLES.items()}
                result = {}
                for key, val in raw.items():
                    friendly = reverse_map.get(key, key)
                    try:
                        result[friendly] = int(val) if val and val != "null" else None
                    except (ValueError, TypeError):
                        result[friendly] = val
                return result
            return data if isinstance(data, dict) else None
        except (TypeError, ValueError):
            return None
