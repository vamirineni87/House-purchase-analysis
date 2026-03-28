from typing import Optional

from .base import ApiClient

_PUBLIC_API_KEY = "iiHnOKfno2Mgkt5AynpvPpUQTEyxE77jo1RU8PIv"


class FBICrimeClient(ApiClient):
    """Client for the FBI Crime Data Explorer API."""

    def __init__(self, timeout: float = 30.0):
        super().__init__(
            base_url="https://api.usa.gov/crime/fbi/sapi",
            api_key=_PUBLIC_API_KEY,
            timeout=timeout,
        )

    async def get_state_crime(
        self,
        state_abbr: str,
        year: int | None = None,
    ) -> Optional[dict]:
        """Fetch crime estimates for a US state.

        Args:
            state_abbr: Two-letter state abbreviation (e.g. "CA").
            year: Optional year to filter results.

        Returns:
            Crime data dict, or None on failure.
        """
        params: dict = {"api_key": self.api_key}
        if year is not None:
            params["year"] = year

        path = f"api/estimates/{state_abbr}"
        return await self.get(path, params=params)
