"""Scraper for Loudoun County parcel/assessment data."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Loudoun County parcel database portal
_BASE_URL = "https://www.loudoun.gov/parceldatabase"


class LoudounParcelScraper(BaseScraper):
    """Scraper for Loudoun County parcel database / assessment portal.

    Target: https://www.loudoun.gov/parceldatabase

    Extracts assessed values, property characteristics, owner info,
    and sale history.
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
        """Look up a property by street address on Loudoun's parcel database.

        Args:
            address: Street address (e.g. ``"100 MAIN ST"``).

        Returns:
            Parsed property dict, or ``None`` if not found.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_BASE_URL, wait_until="networkidle", timeout=30000)

            # The parcel database typically has a search form
            await page.wait_for_selector(
                "input[name='address'], #txtAddress, #searchAddress", timeout=10000
            )

            # Find and fill the address input
            for sel in ["#txtAddress", "#searchAddress", "input[name='address']"]:
                elem = await page.query_selector(sel)
                if elem:
                    await page.fill(sel, address)
                    break

            # Submit
            for sel in ["#btnSearch", "#searchButton", "button[type='submit']", "input[type='submit']"]:
                elem = await page.query_selector(sel)
                if elem:
                    await elem.click()
                    break

            # Wait for results
            await page.wait_for_selector(
                ".property-detail, .parcel-detail, .search-results, .no-results",
                timeout=15000,
            )
            html = await page.content()

            # If results list, click first
            first_link = await page.query_selector(
                ".search-results a, .results-table tbody tr:first-child a"
            )
            if first_link:
                await first_link.click()
                await page.wait_for_selector(
                    ".property-detail, .parcel-detail", timeout=15000
                )
                html = await page.content()

            return self._parse_property_page(html)
        except Exception:
            logger.exception("Failed to look up address on Loudoun parcel DB: %s", address)
            return None
        finally:
            await page.close()

    async def get_property_by_parcel(self, parcel_number: str) -> dict | None:
        """Look up a property by parcel number on Loudoun's parcel database.

        Args:
            parcel_number: Loudoun County parcel identification number.

        Returns:
            Parsed property dict, or ``None`` if not found.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_BASE_URL, wait_until="networkidle", timeout=30000)

            # Switch to parcel number search if tabs exist
            for sel in ["#parcelTab", "[data-tab='parcel']", "a:has-text('Parcel')"]:
                elem = await page.query_selector(sel)
                if elem:
                    await elem.click()
                    break

            # Fill parcel number
            for sel in ["#txtParcel", "#searchParcel", "input[name='parcel']"]:
                elem = await page.query_selector(sel)
                if elem:
                    await page.fill(sel, parcel_number)
                    break

            # Submit
            for sel in ["#btnSearch", "#searchButton", "button[type='submit']", "input[type='submit']"]:
                elem = await page.query_selector(sel)
                if elem:
                    await elem.click()
                    break

            await page.wait_for_selector(
                ".property-detail, .parcel-detail, .search-results, .no-results",
                timeout=15000,
            )
            html = await page.content()

            first_link = await page.query_selector(
                ".search-results a, .results-table tbody tr:first-child a"
            )
            if first_link:
                await first_link.click()
                await page.wait_for_selector(
                    ".property-detail, .parcel-detail", timeout=15000
                )
                html = await page.content()

            return self._parse_property_page(html)
        except Exception:
            logger.exception("Failed to look up parcel on Loudoun parcel DB: %s", parcel_number)
            return None
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_property_page(self, html: str) -> dict | None:
        """Parse a Loudoun County property detail page into a structured dict.

        Args:
            html: Full HTML of the property detail page.

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

        def _find_value(label_text: str) -> str | None:
            for tag in soup.find_all(["th", "dt", "label", "span", "td"]):
                if label_text.lower() in (tag.get_text(strip=True) or "").lower():
                    sibling = tag.find_next_sibling(["td", "dd", "span", "div"])
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

        # Assessment values
        result["assessed_land_value"] = _parse_currency(_find_value("Land"))
        result["assessed_improvement_value"] = _parse_currency(_find_value("Improvement"))
        result["total_assessed_value"] = _parse_currency(
            _find_value("Total") or _find_value("Assessed")
        )

        # Property characteristics
        result["year_built"] = _parse_int(_find_value("Year Built"))
        result["sqft"] = _parse_int(
            _find_value("Living Area") or _find_value("Finished") or _find_value("Sq Ft")
        )
        result["bedrooms"] = _parse_int(_find_value("Bedroom"))
        result["bathrooms"] = _parse_float(
            _find_value("Full Bath") or _find_value("Bathroom")
        )
        half_baths = _parse_int(_find_value("Half Bath"))
        if half_baths and result["bathrooms"] is not None:
            result["bathrooms"] += half_baths * 0.5
        elif half_baths:
            result["bathrooms"] = half_baths * 0.5

        result["stories"] = _parse_float(_find_value("Stories") or _find_value("Story"))
        result["construction_type"] = _find_value("Construction") or _find_value("Exterior")
        result["owner_name"] = _find_value("Owner") or _find_value("Owner Name")

        # Sale history
        sale_history = []
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if any("sale" in h or "date" in h for h in headers):
                for row in table.find_all("tr")[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        sale_history.append({
                            "date": cells[0].get_text(strip=True) if len(cells) > 0 else None,
                            "price": _parse_currency(cells[1].get_text(strip=True)) if len(cells) > 1 else None,
                            "type": cells[2].get_text(strip=True) if len(cells) > 2 else None,
                        })
                break
        result["sale_history"] = sale_history

        has_data = any(v is not None and v != [] for v in result.values())
        return result if has_data else None
