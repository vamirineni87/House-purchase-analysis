import httpx
from typing import Optional, Any


class ApiClient:
    """Base API client with async and sync HTTP GET support."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Optional[dict]:
        """Make GET request, return JSON dict or None on failure."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.base_url}/{path.lstrip('/')}"
                resp = await client.get(url, params=params, headers=headers or {})
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, Exception):
            return None

    def get_sync(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Optional[dict]:
        """Synchronous version of get."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                url = f"{self.base_url}/{path.lstrip('/')}"
                resp = client.get(url, params=params, headers=headers or {})
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, Exception):
            return None
