"""Scraper for Loudoun County LandMARC permit portal."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

# LandMARC portal URL
_BASE_URL = "https://aca-loudoun.accela.com"
_SEARCH_URL = f"{_BASE_URL}/citizenaccess/cap/capHome.aspx"


class LoudounLandMARCScraper(BaseScraper):
    """Scraper for Loudoun County LandMARC (Accela Citizen Access) permit portal.

    Target: https://aca-loudoun.accela.com

    Extracts building permits, renovation permits, and related records
    from Loudoun County's LandMARC system (Accela-based).
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
            address: Street address (e.g. ``"100 MAIN ST"``).

        Returns:
            List of parsed permit dicts (may be empty).
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_SEARCH_URL, wait_until="networkidle", timeout=30000)

            # Accela Citizen Access uses ASP.NET forms with long IDs
            # Navigate to the "Search by Address" section
            address_input = await page.query_selector(
                "input[id*='txtAddress'], input[id*='StreetName'], input[name*='Address']"
            )
            if address_input:
                await address_input.fill(address)

            # Click search button
            search_btn = await page.query_selector(
                "a[id*='btnSearch'], input[id*='btnSearch'], button[id*='btnSearch']"
            )
            if search_btn:
                await search_btn.click()

            # Wait for results grid
            await page.wait_for_selector(
                "table[id*='GridView'], .ACA_Grid_Row, .no-results, #divNoResults",
                timeout=20000,
            )
            html = await page.content()
            return self._parse_permit_list(html)
        except Exception:
            logger.exception("Failed to look up permits by address on LandMARC: %s", address)
            return []
        finally:
            await page.close()

    async def get_permits_by_parcel(self, parcel_number: str) -> list[dict]:
        """Fetch building permits for a property by parcel number.

        Args:
            parcel_number: Loudoun County parcel identification number.

        Returns:
            List of parsed permit dicts (may be empty).
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._rate_limit_wait()
            await page.goto(_SEARCH_URL, wait_until="networkidle", timeout=30000)

            # Find parcel/PIN input
            parcel_input = await page.query_selector(
                "input[id*='txtParcel'], input[id*='ParcelNumber'], input[name*='Parcel']"
            )
            if parcel_input:
                await parcel_input.fill(parcel_number)

            search_btn = await page.query_selector(
                "a[id*='btnSearch'], input[id*='btnSearch'], button[id*='btnSearch']"
            )
            if search_btn:
                await search_btn.click()

            await page.wait_for_selector(
                "table[id*='GridView'], .ACA_Grid_Row, .no-results, #divNoResults",
                timeout=20000,
            )
            html = await page.content()
            return self._parse_permit_list(html)
        except Exception:
            logger.exception("Failed to look up permits by parcel on LandMARC: %s", parcel_number)
            return []
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_permit_list(self, html: str) -> list[dict]:
        """Parse a LandMARC / Accela results page into a list of permit dicts.

        Accela Citizen Access uses ASP.NET GridView tables with long
        auto-generated IDs. We look for rows in any table that appears
        to contain permit data.

        Args:
            html: Full HTML of the search results page.

        Returns:
            List of dicts, each with keys: permit_number, type, description,
            status, issue_date, final_date, contractor, estimated_cost.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        permits: list[dict] = []

        # Find the Accela results grid
        grid = soup.find("table", id=re.compile(r"GridView", re.IGNORECASE))
        if not grid:
            # Fallback: any table with permit-like headers
            for t in soup.find_all("table"):
                text = " ".join(th.get_text(strip=True).lower() for th in t.find_all("th"))
                if "permit" in text or "record" in text or "status" in text:
                    grid = t
                    break

        if not grid:
            logger.debug("No permit results grid found in LandMARC HTML")
            return permits

        headers = [th.get_text(strip=True).lower() for th in grid.find_all("th")]
        col_map = self._build_column_map(headers)

        rows = grid.find_all("tr")
        for row in rows:
            # Skip header rows and spacer rows
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue
            # Skip rows that look like headers (all text is bold)
            if all(cell.find("th") for cell in cells):
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
            # Only include rows that have at least a permit number
            if permit["permit_number"]:
                permits.append(permit)

        return permits

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_column_map(headers: list[str]) -> dict[str, int]:
        """Map standard field names to column indices based on header text."""
        mapping: dict[str, int] = {}
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if "record" in h_lower and ("number" in h_lower or "no" in h_lower):
                mapping["permit_number"] = idx
            elif "permit" in h_lower and ("number" in h_lower or "no" in h_lower):
                mapping["permit_number"] = idx
            elif "type" in h_lower or "module" in h_lower:
                mapping.setdefault("type", idx)
            elif "desc" in h_lower:
                mapping["description"] = idx
            elif "status" in h_lower:
                mapping["status"] = idx
            elif "open" in h_lower or "issue" in h_lower or "filed" in h_lower:
                mapping["issue_date"] = idx
            elif "final" in h_lower or "close" in h_lower or "complete" in h_lower:
                mapping["final_date"] = idx
            elif "contractor" in h_lower or "applicant" in h_lower:
                mapping["contractor"] = idx
            elif "cost" in h_lower or "value" in h_lower or "fee" in h_lower:
                mapping["estimated_cost"] = idx
        return mapping

    @staticmethod
    def _cell_text(cells: list, idx: int | None) -> str | None:
        if idx is None or idx >= len(cells):
            return None
        text = cells[idx].get_text(strip=True)
        return text if text else None

    @staticmethod
    def _parse_currency(val: str | None) -> int | None:
        if not val:
            return None
        cleaned = re.sub(r"[^\d.]", "", val)
        try:
            return int(float(cleaned)) if cleaned else None
        except (ValueError, TypeError):
            return None
