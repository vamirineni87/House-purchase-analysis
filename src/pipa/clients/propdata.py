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
    base_url = "https://propdata-api-worker.sales-fd3.workers.dev/v1"

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
            headers["X-API-Key"] = self.api_key
        return headers

    async def get_market_snapshot(self, zip_code: str) -> dict[str, Any] | None:
        """Get comprehensive market snapshot for a ZIP code.

        Returns dict with nested sections:
          - snapshot.market: median_listing_price, median_days_on_market,
            active_listings, sale_to_list_ratio, price_per_sqft, homes_sold, etc.
          - snapshot.rent: median_asking_rent, FMR by bedroom count
          - snapshot.affordability: vacancy_rate, median_hh_income, rent/own split
          - snapshot.demographics: population, age, education, commute
          - location: zip, state, metro
        """
        data = await self.get("/market", params={"zip": zip_code})
        if data and data.get("error"):
            logger.warning("PropData error for ZIP %s: %s", zip_code, data["error"])
            return None
        return data

    async def get_trends(self, zip_code: str) -> dict[str, Any] | None:
        """Get historical trend data for a ZIP code."""
        data = await self.get("/trends", params={"zip": zip_code})
        if data and data.get("error"):
            return None
        return data

    def extract_market_indicators(self, data: dict) -> dict[str, Any]:
        """Extract key market indicators from a PropData snapshot.

        Normalizes into the same format used by RedfinDataClient.compute_market_indicators().
        """
        mkt = (data.get("snapshot") or {}).get("market") or {}
        aff = (data.get("snapshot") or {}).get("affordability") or {}

        months_of_supply = mkt.get("months_of_supply")
        market_type = "balanced"
        if months_of_supply is not None:
            if months_of_supply < 3:
                market_type = "seller"
            elif months_of_supply > 6:
                market_type = "buyer"
        elif mkt.get("sale_to_list_ratio"):
            # Infer from sale-to-list ratio
            stl = mkt["sale_to_list_ratio"]
            if stl > 1.02:
                market_type = "seller"
            elif stl < 0.97:
                market_type = "buyer"

        return {
            "market_type": market_type,
            "months_of_supply": months_of_supply,
            "median_sale_price": mkt.get("median_sale_price"),
            "median_list_price": mkt.get("median_listing_price"),
            "median_dom": mkt.get("median_days_on_market"),
            "homes_sold": mkt.get("homes_sold"),
            "active_listings": mkt.get("active_listings"),
            "new_listings": mkt.get("new_listings"),
            "sale_to_list_avg": mkt.get("sale_to_list_ratio"),
            "price_per_sqft": mkt.get("price_per_sqft"),
            "sold_above_list_pct": mkt.get("sold_above_list_pct"),
            "price_yoy_pct": mkt.get("price_yoy_pct"),
            "dom_yoy_pct": mkt.get("dom_yoy_pct"),
            "inventory_yoy_pct": mkt.get("inventory_yoy_pct"),
            "median_hh_income": aff.get("median_hh_income"),
            "vacancy_rate_pct": aff.get("vacancy_rate_pct"),
            "source": "propdata",
        }
