"""PropData Real Estate Market Intelligence API client.

Aggregates Redfin, Zillow, Census, FRED data into one API.
Free tier: 50 requests/hour, all endpoints, no credit card.

Docs: https://propdata.proptechusa.ai/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import BaseClient

logger = logging.getLogger(__name__)


class PropDataClient(BaseClient):
    """Client for PropData market intelligence API."""

    source_name = "propdata"
    base_url = "https://api.propdata.proptechusa.ai/v1"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 0.8,  # ~50/hour = 0.83/min, stay under
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 24,  # market data refreshes daily
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    def _default_headers(self) -> dict[str, str]:
        headers = {"User-Agent": "PIPA/0.1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def get_market_metrics(self, zip_code: str) -> dict[str, Any] | None:
        """Get comprehensive market metrics for a ZIP code.

        Returns dict with:
          - median_sale_price, median_list_price
          - months_of_supply
          - median_dom (days on market)
          - sale_to_list_ratio
          - active_listings, new_listings
          - price_per_sqft
          - inventory
        """
        data = await self.get(f"/market/metrics", params={"zip": zip_code})
        if data is None:
            logger.warning("PropData: no market metrics for ZIP %s", zip_code)
        return data

    async def get_market_trends(
        self, zip_code: str, months: int = 12
    ) -> list[dict] | None:
        """Get monthly market trend data for a ZIP code.

        Returns list of monthly snapshots with price, inventory, DOM trends.
        """
        data = await self.get(
            f"/market/trends",
            params={"zip": zip_code, "months": months},
        )
        return data

    async def get_market_summary(self, zip_code: str) -> dict[str, Any] | None:
        """Get a high-level market summary — buyer's vs seller's market, etc."""
        data = await self.get(f"/market/summary", params={"zip": zip_code})
        return data
