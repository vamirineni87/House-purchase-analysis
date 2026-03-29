"""Scraper for Fairfax County iCare property assessment portal."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

# iCare portal base URL
_BASE_URL = "https://icare.fairfaxcounty.gov"
_SEARCH_URL = f"{_BASE_URL}/ffxcare/search"


class FairfaxICareScraper(BaseScraper):
    """Scraper for Fairfax County iCare property assessment system.

    Target: https://icare.fairfaxcounty.gov

    Extracts assessed values, property characteristics, owner info,
    and sale history from the county assessment portal.
    """

    def __init__(
        self,
        headless: bool = True,
        rate_limit: float = 1.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 24,
    ):
        super().__init__(
            headless=headless,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def get_property_by_address(self, address: str) -> dict | None:
        """Look up a property by street address on iCare.

        Args:
            address: Street address (e.g. ``"4000 CHAIN BRIDGE RD"``).

        Returns:
            Parsed property dict, or ``None`` if not found.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_SEARCH_URL, wait_until="networkidle", timeout=30000)

            # Fill in the address search field
            await page.wait_for_selector("#searchAddress", timeout=10000)
            await page.fill("#searchAddress", address)
            await page.click("#searchButton")

            # Wait for results
            await page.wait_for_selector(
                ".property-details, .search-results, .no-results", timeout=15000
            )

            html = await page.content()

            # If we landed on a results list, click the first result
            if await page.query_selector(".search-results .result-row"):
                await page.click(".search-results .result-row:first-child a")
                await page.wait_for_selector(".property-details", timeout=15000)
                html = await page.content()

            return self._parse_property_page(html)
        except Exception:
            logger.exception("Failed to look up address on iCare: %s", address)
            return None
        finally:
            await page.close()

    async def get_property_by_parcel(self, parcel_number: str) -> dict | None:
        """Look up a property by parcel number on iCare.

        Args:
            parcel_number: Fairfax County parcel number (e.g. ``"0571 01 0109"``).

        Returns:
            Parsed property dict, or ``None`` if not found.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_SEARCH_URL, wait_until="networkidle", timeout=30000)

            # Switch to parcel search tab if needed
            parcel_tab = await page.query_selector("#parcelTab, [data-tab='parcel']")
            if parcel_tab:
                await parcel_tab.click()

            await page.wait_for_selector("#searchParcel, #parcelNumber", timeout=10000)
            selector = "#searchParcel" if await page.query_selector("#searchParcel") else "#parcelNumber"
            await page.fill(selector, parcel_number)
            await page.click("#searchButton, button[type='submit']")

            await page.wait_for_selector(
                ".property-details, .search-results, .no-results", timeout=15000
            )
            html = await page.content()

            # If we landed on a results list, click the first result
            if await page.query_selector(".search-results .result-row"):
                await page.click(".search-results .result-row:first-child a")
                await page.wait_for_selector(".property-details", timeout=15000)
                html = await page.content()

            return self._parse_property_page(html)
        except Exception:
            logger.exception("Failed to look up parcel on iCare: %s", parcel_number)
            return None
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_property_page(self, html: str) -> dict | None:
        """Parse a property detail page into a structured dict.

        Args:
            html: Full HTML of the iCare property detail page.

        Returns:
            Dict with keys: assessed_land_value, assessed_improvement_value,
            total_assessed_value, year_built, sqft, bedrooms, bathrooms,
            stories, construction_type, owner_name, sale_history.
            Returns ``None`` if parsing fails completely.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        result: dict = {
            "assessed_land_value": None,
            "assessed_improvement_value": None,
            "total_assessed_value": None,
            "year_built": None,
            "sqft": None,
            "bedrooms": None,
            "bathrooms": None,
            "stories": None,
            "construction_type": None,
            "owner_name": None,
            "sale_history": [],
        }

        # Helper to extract text by label from table rows or definition lists
        def _find_value(label_text: str) -> str | None:
            """Find a value cell adjacent to a label containing the given text."""
            # Try table row pattern: <th>Label</th><td>Value</td>
            for th in soup.find_all(["th", "dt", "label", "span"]):
                if label_text.lower() in (th.get_text(strip=True) or "").lower():
                    # Check next sibling or paired element
                    sibling = th.find_next_sibling(["td", "dd", "span", "div"])
                    if sibling:
                        return sibling.get_text(strip=True)
            return None

        def _parse_currency(val: str | None) -> int | None:
            if not val:
                return None
            cleaned = re.sub(r"[^\d.]", "", val)
            try:
                return int(float(cleaned))
            except (ValueError, TypeError):
                return None

        def _parse_int(val: str | None) -> int | None:
            if not val:
                return None
            cleaned = re.sub(r"[^\d]", "", val)
            try:
                return int(cleaned) if cleaned else None
            except (ValueError, TypeError):
                return None

        def _parse_float(val: str | None) -> float | None:
            if not val:
                return None
            cleaned = re.sub(r"[^\d.]", "", val)
            try:
                return float(cleaned) if cleaned else None
            except (ValueError, TypeError):
                return None

        # --- Assessment values ---
        result["assessed_land_value"] = _parse_currency(_find_value("Land"))
        result["assessed_improvement_value"] = _parse_currency(_find_value("Improvement"))
        result["total_assessed_value"] = _parse_currency(
            _find_value("Total") or _find_value("Assessed Value")
        )

        # --- Property characteristics ---
        result["year_built"] = _parse_int(_find_value("Year Built"))
        result["sqft"] = _parse_int(
            _find_value("Living Area") or _find_value("Finished Area") or _find_value("Sq Ft")
        )
        result["bedrooms"] = _parse_int(_find_value("Bedroom"))
        result["bathrooms"] = _parse_float(
            _find_value("Full Bath") or _find_value("Bathroom")
        )
        # Add half baths if present
        half_baths = _parse_int(_find_value("Half Bath"))
        if half_baths and result["bathrooms"] is not None:
            result["bathrooms"] += half_baths * 0.5
        elif half_baths:
            result["bathrooms"] = half_baths * 0.5

        result["stories"] = _parse_float(_find_value("Stories") or _find_value("Story"))
        result["construction_type"] = _find_value("Construction") or _find_value("Exterior")

        # --- Owner ---
        result["owner_name"] = _find_value("Owner") or _find_value("Owner Name")

        # --- Sale history ---
        sale_history = []
        # Look for a sales history table
        sales_table = None
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if any("sale" in h or "date" in h for h in headers):
                sales_table = table
                break

        if sales_table:
            rows = sales_table.find_all("tr")[1:]  # skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    sale_entry: dict = {
                        "date": cells[0].get_text(strip=True) if len(cells) > 0 else None,
                        "price": _parse_currency(cells[1].get_text(strip=True)) if len(cells) > 1 else None,
                        "type": cells[2].get_text(strip=True) if len(cells) > 2 else None,
                    }
                    sale_history.append(sale_entry)

        result["sale_history"] = sale_history

        # Return None only if we got absolutely nothing useful
        has_data = any(
            v is not None and v != []
            for v in result.values()
        )
        return result if has_data else None
