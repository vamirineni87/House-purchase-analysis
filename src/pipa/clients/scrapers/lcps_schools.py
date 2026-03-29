"""Scraper for LCPS (Loudoun County Public Schools) School Locator.

Source: https://dashboards.lcps.org/extensions/Dashboards/Label.html
(Qlik Sense dashboard)

Tested against live site on 2026-03-28 for "42580 DEER ISLE".
The dashboard uses Qlik Sense with MUI components. Navigation requires:
1. Wait for Qlik to render (~8s)
2. Expand the folded listbox
3. Search for the address
4. Click the matching row
5. Extract school assignments from Qlik objects by index

Object layout (confirmed via testing):
  Current year:
    obj[6] = ES Name, obj[7] = ES Principal
    obj[13] = MS Name, obj[14] = MS Principal
    obj[20] = HS Name, obj[21] = HS Principal
  Future year (2026-2027):
    Objects 33-53 contain future school assignments
  Also: school board member, address, phone, URL, profile link
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pipa.clients.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PARSER_VERSION = "1.0.0"
SEARCH_URL = "https://dashboards.lcps.org/extensions/Dashboards/Label.html"

# Qlik object indices for school data extraction
# Current year
_OBJ_ES_NAME = 6
_OBJ_ES_PRINCIPAL = 7
_OBJ_MS_NAME = 13
_OBJ_MS_PRINCIPAL = 14
_OBJ_HS_NAME = 20
_OBJ_HS_PRINCIPAL = 21

# Future year
_OBJ_FUTURE_ES_NAME = 33
_OBJ_FUTURE_ES_PRINCIPAL = 34
_OBJ_FUTURE_MS_NAME = 40
_OBJ_FUTURE_MS_PRINCIPAL = 41
_OBJ_FUTURE_HS_NAME = 47
_OBJ_FUTURE_HS_PRINCIPAL = 48

# Qlik render wait time (seconds)
_QLIK_RENDER_WAIT_MS = 8000

# How long to wait for search results to appear
_SEARCH_RESULT_WAIT_MS = 5000

# How long to wait for school data to update after row click
_DATA_UPDATE_WAIT_MS = 5000


class LCPSSchoolScraper(BaseScraper):
    """Scrapes LCPS School Locator dashboard for school boundary assignments.

    Usage::

        scraper = LCPSSchoolScraper(headless=False)
        data = await scraper.lookup_schools("42580 DEER ISLE")
        await scraper.close()
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._page = None  # Reuse page between calls

    async def lookup_schools(
        self,
        address: str,
        *,
        save_screenshot: bool = True,
        screenshot_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Look up assigned schools for an address.

        Args:
            address: Street address to search (e.g., "42580 DEER ISLE").
                     City/state/zip are stripped if present.
            save_screenshot: Save a screenshot after extraction.
            screenshot_dir: Where to save screenshots. Defaults to ./storage/screenshots/lcps.

        Returns:
            Dict with current and future school assignments:
            - current_year: str (e.g., "2025-2026")
            - elementary: {name, principal, address, phone, website, profile_url}
            - middle: {name, principal, address, phone, website, profile_url}
            - high: {name, principal, address, phone, website, profile_url}
            - school_board_member: str
            - future_year: str (e.g., "2026-2027")
            - future_elementary: {...}
            - future_middle: {...}
            - future_high: {...}
            - boundary_change: bool (True if future differs from current)
        """
        await self._ensure_browser()
        await self._rate_limit_wait()

        result: dict[str, Any] = {
            "_source": "lcps_official",
            "_url": SEARCH_URL,
            "_parser_version": PARSER_VERSION,
            "_scraped_at": datetime.now(timezone.utc).isoformat(),
            "_search_address": address,
        }

        # Normalize the address for search — strip city/state/zip
        search_term = self._normalize_search_address(address)

        try:
            page = await self._get_or_create_page()

            # --- Step 1: Navigate to the dashboard (or reuse if already loaded) ---
            current_url = page.url
            if SEARCH_URL not in current_url:
                logger.info("LCPS: Loading dashboard page")
                await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(_QLIK_RENDER_WAIT_MS)
            else:
                # Already on the page — clear previous search
                logger.info("LCPS: Reusing existing dashboard page")
                await page.wait_for_timeout(1000)

            # --- Step 2: Expand the folded listbox ---
            logger.debug("LCPS: Expanding folded listbox")
            folded = await page.query_selector(".folded-listbox")
            if folded:
                await folded.click()
                await page.wait_for_timeout(1500)
            else:
                # Try alternative: the listbox might already be expanded
                logger.debug("LCPS: No .folded-listbox found, may already be expanded")

            # --- Step 3: Find the search input ---
            search_input = await self._find_search_input(page)
            if not search_input:
                result["_error"] = "search_input_not_found"
                logger.warning("LCPS: Could not find search input")
                return result

            # Clear any existing text and type the address
            await search_input.click()
            await search_input.fill("")
            await page.wait_for_timeout(300)
            await search_input.type(search_term, delay=50)
            await page.wait_for_timeout(_SEARCH_RESULT_WAIT_MS)

            # --- Step 4: Find and click the matching result row ---
            clicked = await self._click_matching_row(page, search_term)
            if not clicked:
                result["_error"] = "no_matching_row"
                result["_search_term"] = search_term
                logger.warning("LCPS: No matching row found for '%s'", search_term)
                return result

            # Click elsewhere to close the listbox dropdown
            await page.click("body", position={"x": 10, "y": 10})
            await page.wait_for_timeout(_DATA_UPDATE_WAIT_MS)

            # --- Step 5: Extract school data from Qlik objects ---
            qlik_objects = await self._extract_all_qlik_objects(page)
            result["_qlik_object_count"] = len(qlik_objects)

            # --- Step 6: Parse current year schools ---
            current_year = self._detect_school_year(qlik_objects, future=False)
            result["current_year"] = current_year

            result["elementary"] = self._extract_school_info(
                qlik_objects, _OBJ_ES_NAME, _OBJ_ES_PRINCIPAL, "Elementary"
            )
            result["middle"] = self._extract_school_info(
                qlik_objects, _OBJ_MS_NAME, _OBJ_MS_PRINCIPAL, "Middle"
            )
            result["high"] = self._extract_school_info(
                qlik_objects, _OBJ_HS_NAME, _OBJ_HS_PRINCIPAL, "High"
            )

            # School board member (usually near the address/school data area)
            result["school_board_member"] = self._extract_school_board_member(qlik_objects)

            # --- Step 7: Parse future year schools ---
            future_year = self._detect_school_year(qlik_objects, future=True)
            result["future_year"] = future_year

            result["future_elementary"] = self._extract_school_info(
                qlik_objects, _OBJ_FUTURE_ES_NAME, _OBJ_FUTURE_ES_PRINCIPAL, "Elementary"
            )
            result["future_middle"] = self._extract_school_info(
                qlik_objects, _OBJ_FUTURE_MS_NAME, _OBJ_FUTURE_MS_PRINCIPAL, "Middle"
            )
            result["future_high"] = self._extract_school_info(
                qlik_objects, _OBJ_FUTURE_HS_NAME, _OBJ_FUTURE_HS_PRINCIPAL, "High"
            )

            # --- Step 8: Detect boundary changes ---
            result["boundary_change"] = self._detect_boundary_change(result)

            # --- Step 9: Fallback — extract from full page text ---
            if not result["elementary"].get("name"):
                logger.debug("LCPS: Object-based extraction empty, trying text fallback")
                text_data = await self._extract_from_page_text(page)
                if text_data:
                    for key in ("elementary", "middle", "high"):
                        if not result[key].get("name") and text_data.get(key, {}).get("name"):
                            result[key] = text_data[key]
                    for key in ("future_elementary", "future_middle", "future_high"):
                        if not result.get(key, {}).get("name") and text_data.get(key, {}).get("name"):
                            result[key] = text_data[key]

            # --- Step 10: Save screenshot ---
            if save_screenshot:
                ss_dir = screenshot_dir or Path("./storage/screenshots/lcps")
                ss_dir.mkdir(parents=True, exist_ok=True)
                safe_addr = re.sub(r"[^\w\-]", "_", search_term)[:60]
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                ss_path = ss_dir / f"lcps_{safe_addr}_{ts}.png"
                await page.screenshot(path=str(ss_path), full_page=True)
                result["_screenshot_path"] = str(ss_path)

            # Clean up None values
            result = {k: v for k, v in result.items() if v is not None}

            logger.info(
                "LCPS lookup complete for '%s': ES=%s, MS=%s, HS=%s, boundary_change=%s",
                search_term,
                result.get("elementary", {}).get("name", "?"),
                result.get("middle", {}).get("name", "?"),
                result.get("high", {}).get("name", "?"),
                result.get("boundary_change", False),
            )
            return result

        except Exception:
            logger.exception("LCPS: Failed to look up schools for '%s'", address)
            result["_error"] = "scrape_failed"
            return result

    # ==================================================================
    # Page lifecycle
    # ==================================================================

    async def _get_or_create_page(self):
        """Reuse the existing page or create a new one."""
        if self._page is not None:
            try:
                # Check if page is still alive
                await self._page.title()
                return self._page
            except Exception:
                self._page = None

        self._page = await self._context.new_page()
        return self._page

    async def close(self):
        """Close the reusable page and then the browser."""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        await super().close()

    # ==================================================================
    # Search helpers
    # ==================================================================

    @staticmethod
    def _normalize_search_address(address: str) -> str:
        """Strip city/state/zip to get just the street portion for Qlik search.

        "42580 DEER ISLE DR, CHANTILLY, VA 20152" -> "42580 DEER ISLE"
        "42580 Deer Isle Dr" -> "42580 DEER ISLE"
        """
        # Remove everything after a comma
        street = address.split(",")[0].strip()

        # Remove common street suffixes for a broader search
        # (The LCPS search matches partial addresses)
        suffix_pattern = r"\s+(DR|ST|CT|LN|PL|WAY|TER|RD|AVE|BLVD|CIR|PKWY|PIKE|SQ|RUN|LOOP)\.?$"
        street = re.sub(suffix_pattern, "", street.upper())

        return street.strip()

    async def _find_search_input(self, page) -> Optional[Any]:
        """Find the search input field in the Qlik listbox.

        Tries multiple selectors in priority order.
        """
        selectors = [
            'input[placeholder*="Search"]',
            'input[placeholder*="search"]',
            "input.MuiInputBase-input",
            '.qv-listbox input[type="text"]',
            '.qv-filterpane input[type="text"]',
            '.lui-search__input',
        ]
        for selector in selectors:
            el = await page.query_selector(selector)
            if el:
                logger.debug("LCPS: Found search input via '%s'", selector)
                return el

        # Fallback: find any visible input in the listbox area
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            if await inp.is_visible():
                inp_type = await inp.get_attribute("type") or ""
                if inp_type in ("text", "search", ""):
                    logger.debug("LCPS: Found search input via generic input scan")
                    return inp

        return None

    async def _click_matching_row(self, page, search_term: str) -> bool:
        """Find and click the result row that matches the search term.

        Rows appear as [role='row'] elements in the Qlik listbox.
        """
        rows = await page.query_selector_all("[role='row']")
        search_upper = search_term.upper()

        for row in rows:
            text = (await row.text_content() or "").strip().upper()
            if search_upper in text:
                logger.debug("LCPS: Clicking matching row: %s", text[:80])
                await row.click()
                await page.wait_for_timeout(1000)
                return True

        # Fallback: click the first row with any content
        for row in rows:
            text = (await row.text_content() or "").strip()
            if text and len(text) > 5:
                logger.debug("LCPS: Clicking first result row (fallback): %s", text[:80])
                await row.click()
                await page.wait_for_timeout(1000)
                return True

        return False

    # ==================================================================
    # Qlik object extraction
    # ==================================================================

    async def _extract_all_qlik_objects(self, page) -> dict[int, str]:
        """Extract text content from all .qv-object elements by index.

        Returns a dict mapping object index -> text content.
        """
        objects: dict[int, str] = {}

        qv_objects = await page.query_selector_all(".qv-object")
        for i, obj in enumerate(qv_objects):
            text = (await obj.text_content() or "").strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                objects[i] = text

        logger.debug("LCPS: Extracted %d Qlik objects", len(objects))
        return objects

    def _extract_school_info(
        self,
        objects: dict[int, str],
        name_idx: int,
        principal_idx: int,
        level: str,
    ) -> dict[str, Optional[str]]:
        """Extract school details from Qlik objects by known indices.

        Also tries to parse phone, address, website, and profile URL from
        adjacent objects or from the text content itself.
        """
        info: dict[str, Optional[str]] = {
            "name": None,
            "principal": None,
            "address": None,
            "phone": None,
            "website": None,
            "profile_url": None,
        }

        # School name from the known object index
        name_text = objects.get(name_idx, "")
        if name_text:
            info["name"] = self._clean_school_name(name_text, level)

        # Principal from the known object index
        principal_text = objects.get(principal_idx, "")
        if principal_text:
            info["principal"] = self._clean_principal_name(principal_text)

        # Scan nearby objects (name_idx+1 through name_idx+6) for phone, address, URL
        for offset in range(2, 7):
            nearby_idx = name_idx + offset
            text = objects.get(nearby_idx, "")
            if not text:
                continue

            # Phone number pattern
            phone = re.search(r"\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}", text)
            if phone and not info["phone"]:
                info["phone"] = phone.group(0)

            # URL pattern
            url = re.search(r"https?://[^\s]+", text)
            if url:
                url_str = url.group(0)
                if "profile" in url_str.lower() or "greatschools" in url_str.lower():
                    info["profile_url"] = url_str
                elif not info["website"]:
                    info["website"] = url_str

            # Address pattern (number + street name)
            addr = re.search(r"\d+\s+[A-Za-z].*(?:Rd|Dr|St|Ave|Blvd|Way|Ln|Pkwy)", text)
            if addr and not info["address"]:
                info["address"] = addr.group(0)

        return info

    @staticmethod
    def _clean_school_name(text: str, level: str) -> str:
        """Clean up a school name extracted from Qlik."""
        # Remove common prefixes/suffixes
        text = text.strip()
        # Sometimes the text includes the label like "Elementary School:"
        text = re.sub(r"^(Elementary|Middle|High)\s+School\s*:?\s*", "", text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _clean_principal_name(text: str) -> str:
        """Clean up a principal name extracted from Qlik."""
        text = text.strip()
        text = re.sub(r"^Principal\s*:?\s*", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _detect_school_year(self, objects: dict[int, str], future: bool = False) -> str:
        """Detect the school year from Qlik object text.

        Looks for patterns like "2025-2026" or "2026-2027" in the page text.
        """
        # Search all objects for year patterns
        year_pattern = re.compile(r"(20\d{2})\s*[-–]\s*(20\d{2})")
        years_found: list[tuple[str, str]] = []

        for text in objects.values():
            matches = year_pattern.findall(text)
            years_found.extend(matches)

        if not years_found:
            # Default based on current date
            now = datetime.now()
            if now.month >= 7:
                base_year = now.year
            else:
                base_year = now.year - 1
            if future:
                return f"{base_year + 1}-{base_year + 2}"
            return f"{base_year}-{base_year + 1}"

        # Sort by start year
        years_found.sort(key=lambda x: int(x[0]))

        if future and len(years_found) >= 2:
            return f"{years_found[-1][0]}-{years_found[-1][1]}"
        return f"{years_found[0][0]}-{years_found[0][1]}"

    def _extract_school_board_member(self, objects: dict[int, str]) -> Optional[str]:
        """Extract school board member name from Qlik objects."""
        for text in objects.values():
            match = re.search(
                r"(?:School\s+Board|Board\s+Member)\s*:?\s*(.+?)(?:\s*\||$)",
                text, re.IGNORECASE,
            )
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _detect_boundary_change(result: dict) -> bool:
        """Compare current vs future school assignments to detect boundary changes."""
        for level in ("elementary", "middle", "high"):
            current = result.get(level, {})
            future = result.get(f"future_{level}", {})
            current_name = (current.get("name") or "").strip().upper()
            future_name = (future.get("name") or "").strip().upper()
            if current_name and future_name and current_name != future_name:
                return True
        return False

    # ==================================================================
    # Text fallback extraction
    # ==================================================================

    async def _extract_from_page_text(self, page) -> dict[str, Any]:
        """Fallback: extract school data from full page text content.

        Used when Qlik object indices don't yield results (e.g., layout change).
        """
        text = await page.text_content("body") or ""

        data: dict[str, Any] = {}

        # Look for school names by level keyword
        es_match = re.search(
            r"(?:Elementary(?:\s+School)?)\s*:?\s*([\w\s]+(?:ES|Elementary))",
            text, re.IGNORECASE,
        )
        if es_match:
            data["elementary"] = {"name": es_match.group(1).strip()}

        ms_match = re.search(
            r"(?:Middle(?:\s+School)?)\s*:?\s*([\w\s]+(?:MS|Middle))",
            text, re.IGNORECASE,
        )
        if ms_match:
            data["middle"] = {"name": ms_match.group(1).strip()}

        hs_match = re.search(
            r"(?:High(?:\s+School)?)\s*:?\s*([\w\s]+(?:HS|High))",
            text, re.IGNORECASE,
        )
        if hs_match:
            data["high"] = {"name": hs_match.group(1).strip()}

        return data
