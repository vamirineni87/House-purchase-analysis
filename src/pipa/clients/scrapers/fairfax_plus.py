"""Scraper for Fairfax County PLUS (permit) portal."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

# PLUS portal base URL
_BASE_URL = "https://plus.fairfaxcounty.gov"
_SEARCH_URL = f"{_BASE_URL}/plus/search"


class FairfaxPLUSScraper(BaseScraper):
    """Scraper for Fairfax County PLUS permit lookup system.

    Target: https://plus.fairfaxcounty.gov

    Extracts building permits, renovation permits, and related
    inspection/approval records.
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

    async def get_permits_by_address(self, address: str) -> list[dict]:
        """Fetch building permits for a property by street address.

        Args:
            address: Street address (e.g. ``"4000 CHAIN BRIDGE RD"``).

        Returns:
            List of parsed permit dicts (may be empty).
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_SEARCH_URL, wait_until="networkidle", timeout=30000)

            # Fill in address search
            await page.wait_for_selector(
                "#searchAddress, input[name='address']", timeout=10000
            )
            selector = (
                "#searchAddress"
                if await page.query_selector("#searchAddress")
                else "input[name='address']"
            )
            await page.fill(selector, address)
            await page.click("#searchButton, button[type='submit']")

            # Wait for results table
            await page.wait_for_selector(
                ".permit-results, .results-table, .no-results", timeout=15000
            )
            html = await page.content()
            return self._parse_permit_list(html)
        except Exception:
            logger.exception("Failed to look up permits by address on PLUS: %s", address)
            return []
        finally:
            await page.close()

    async def get_permits_by_parcel(self, parcel_number: str) -> list[dict]:
        """Fetch building permits for a property by parcel number.

        Args:
            parcel_number: Fairfax County parcel number (e.g. ``"0571 01 0109"``).

        Returns:
            List of parsed permit dicts (may be empty).
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_SEARCH_URL, wait_until="networkidle", timeout=30000)

            # Switch to parcel search if needed
            parcel_tab = await page.query_selector("#parcelTab, [data-tab='parcel']")
            if parcel_tab:
                await parcel_tab.click()

            await page.wait_for_selector(
                "#searchParcel, input[name='parcel']", timeout=10000
            )
            selector = (
                "#searchParcel"
                if await page.query_selector("#searchParcel")
                else "input[name='parcel']"
            )
            await page.fill(selector, parcel_number)
            await page.click("#searchButton, button[type='submit']")

            await page.wait_for_selector(
                ".permit-results, .results-table, .no-results", timeout=15000
            )
            html = await page.content()
            return self._parse_permit_list(html)
        except Exception:
            logger.exception("Failed to look up permits by parcel on PLUS: %s", parcel_number)
            return []
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_permit_list(self, html: str) -> list[dict]:
        """Parse a PLUS permit results page into a list of permit dicts.

        Args:
            html: Full HTML of the PLUS search results page.

        Returns:
            List of dicts, each with keys: permit_number, type, description,
            status, issue_date, final_date, contractor, estimated_cost.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        permits: list[dict] = []

        # Locate the results table — try multiple selectors
        table = (
            soup.select_one(".permit-results table")
            or soup.select_one(".results-table")
            or soup.select_one("table.table")
        )

        if not table:
            # Try to find any table that looks like it has permit data
            for t in soup.find_all("table"):
                headers_text = " ".join(
                    th.get_text(strip=True).lower() for th in t.find_all("th")
                )
                if "permit" in headers_text or "status" in headers_text:
                    table = t
                    break

        if not table:
            logger.debug("No permit results table found in PLUS HTML")
            return permits

        # Parse header to determine column mapping
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        col_map = self._build_column_map(headers)

        # Parse data rows
        rows = table.find_all("tr")[1:]  # skip header row
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            permit: dict = {
                "permit_number": self._cell_text(cells, col_map.get("permit_number")),
                "type": self._cell_text(cells, col_map.get("type")),
                "description": self._cell_text(cells, col_map.get("description")),
                "status": self._cell_text(cells, col_map.get("status")),
                "issue_date": self._cell_text(cells, col_map.get("issue_date")),
                "final_date": self._cell_text(cells, col_map.get("final_date")),
                "contractor": self._cell_text(cells, col_map.get("contractor")),
                "estimated_cost": self._parse_currency(
                    self._cell_text(cells, col_map.get("estimated_cost"))
                ),
            }
            permits.append(permit)

        return permits

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_column_map(headers: list[str]) -> dict[str, int]:
        """Map our standard field names to column indices based on header text."""
        mapping: dict[str, int] = {}
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if "permit" in h_lower and "number" in h_lower:
                mapping["permit_number"] = idx
            elif "permit" in h_lower and "number" not in h_lower and "type" not in h_lower:
                mapping.setdefault("permit_number", idx)
            elif "type" in h_lower:
                mapping["type"] = idx
            elif "desc" in h_lower:
                mapping["description"] = idx
            elif "status" in h_lower:
                mapping["status"] = idx
            elif "issue" in h_lower or "issued" in h_lower:
                mapping["issue_date"] = idx
            elif "final" in h_lower or "complete" in h_lower:
                mapping["final_date"] = idx
            elif "contractor" in h_lower:
                mapping["contractor"] = idx
            elif "cost" in h_lower or "value" in h_lower:
                mapping["estimated_cost"] = idx
        return mapping

    @staticmethod
    def _cell_text(cells: list, idx: int | None) -> str | None:
        """Safely extract text from a cell by index."""
        if idx is None or idx >= len(cells):
            return None
        text = cells[idx].get_text(strip=True)
        return text if text else None

    @staticmethod
    def _parse_currency(val: str | None) -> int | None:
        """Parse a currency string like '$12,500' into an integer."""
        if not val:
            return None
        cleaned = re.sub(r"[^\d.]", "", val)
        try:
            return int(float(cleaned)) if cleaned else None
        except (ValueError, TypeError):
            return None
