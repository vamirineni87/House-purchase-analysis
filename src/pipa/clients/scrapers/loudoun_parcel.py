"""Scraper for Loudoun County real property assessment data.

Source: https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address
(iasWorld Public Access system)

Tested against live site on 2026-03-29 for 42580 Deer Isle Dr.
Extracts data from 10 tabs: Profile, Values, Sales/Transfers, Land,
Land Use Status, Residential, Detached Structures, Commercial,
Parcel Tracking, Tax Payment/History.

The site uses ASP.NET WebForms with ViewState — navigation requires
clicking tab links within the same session (not direct URL access).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pipa.clients.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PARSER_VERSION = "1.0.0"
SEARCH_URL = "https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address"

# Tabs to scrape (in sidebar order)
TABS = [
    "Profile",
    "Values",
    "Sales / Transfers",
    "Land",
    "Land Use Status",
    "Residential",
    "Detached Structures",
    "Commercial",
    "Parcel Tracking",
    "Tax Payment/History",
]


class LoudounParcelScraper(BaseScraper):
    """Scrapes Loudoun County property assessment from the iasWorld portal.

    Usage::

        scraper = LoudounParcelScraper(headless=False)
        data = await scraper.scrape_property("42580", "DEER ISLE", "DR")
        await scraper.close()
    """

    async def scrape_property(
        self,
        house_number: str,
        street_name: str,
        street_type: str = "",
        *,
        tabs: list[str] | None = None,
        save_screenshots: bool = False,
        screenshot_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Scrape all property data for an address.

        Args:
            house_number: e.g. "42580"
            street_name: e.g. "DEER ISLE"
            street_type: e.g. "DR", "ST", "CT" (optional, dropdown value)
            tabs: which tabs to scrape (default: all)
            save_screenshots: save a screenshot of each tab
            screenshot_dir: where to save screenshots

        Returns:
            Dict with tab names as keys, each containing extracted data.
        """
        await self._ensure_browser()
        await self._rate_limit_wait()

        page = await self._context.new_page()
        result: dict[str, Any] = {
            "_source": "loudoun_county",
            "_url": SEARCH_URL,
            "_parser_version": PARSER_VERSION,
            "_scraped_at": datetime.now(timezone.utc).isoformat(),
            "_search": {
                "house_number": house_number,
                "street_name": street_name,
                "street_type": street_type,
            },
        }

        try:
            # --- Step 1: Navigate to search page ---
            logger.info("Loudoun search: %s %s %s", house_number, street_name, street_type)
            await page.goto(SEARCH_URL, timeout=30000)
            await page.wait_for_timeout(2000)

            # --- Step 2: Fill search form ---
            await page.fill("#inpNumber", house_number)
            await page.fill("#inpStreet", street_name.upper())

            if street_type:
                suffix_select = await page.query_selector("#Select1")
                if suffix_select:
                    try:
                        await suffix_select.select_option(street_type.upper())
                    except Exception:
                        logger.debug("Could not select street type: %s", street_type)

            # --- Step 3: Submit search ---
            await page.evaluate("""
                document.getElementById('hdAction').value = 'Search';
                document.forms[0].submit();
            """)
            await page.wait_for_timeout(5000)

            # Check if we landed on property detail or search results
            current_url = page.url
            if "Datalet" not in current_url:
                # Might be on search results — click first result
                result_links = await page.query_selector_all("a[href*='Datalet']")
                if result_links:
                    await result_links[0].click()
                    await page.wait_for_timeout(3000)
                elif "CommonSearch" in current_url:
                    result["_error"] = "no_results"
                    logger.warning("No results found for %s %s %s", house_number, street_name, street_type)
                    return result

            if "Datalet" not in page.url and "datalet" not in page.url:
                result["_error"] = "navigation_failed"
                logger.warning("Failed to reach property detail page: %s", page.url)
                return result

            result["_detail_url"] = page.url

            # --- Step 4: Scrape each tab ---
            tabs_to_scrape = tabs or TABS
            for tab_name in tabs_to_scrape:
                logger.debug("Scraping tab: %s", tab_name)
                tab_data = await self._scrape_tab(page, tab_name)
                result[tab_name] = tab_data

                if save_screenshots and screenshot_dir:
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    safe = tab_name.replace("/", "_").replace(" ", "_").lower()
                    path = screenshot_dir / f"loudoun_{safe}.png"
                    await page.screenshot(path=str(path))

            # --- Step 5: Build structured summary ---
            result["_summary"] = self._build_summary(result)

            logger.info(
                "Loudoun scrape complete: %s %s %s — %d tabs scraped",
                house_number, street_name, street_type, len(tabs_to_scrape),
            )
            return result

        except Exception:
            logger.exception("Failed to scrape Loudoun property")
            result["_error"] = "scrape_failed"
            return result
        finally:
            await page.close()

    async def scrape_by_address_string(
        self, address: str, **kwargs
    ) -> dict[str, Any]:
        """Parse an address string and scrape.

        Accepts: "42580 Deer Isle Dr" or "42580 DEER ISLE DR"
        """
        parts = address.strip().split()
        if len(parts) < 2:
            return {"_error": "invalid_address", "_input": address}

        house_number = parts[0]

        # Check if last part is a street type
        street_types = {
            "DR", "ST", "CT", "LN", "PL", "WAY", "TER", "RD", "AVE",
            "BLVD", "CIR", "CIRC", "PKWY", "PIKE", "HWY", "ALY", "SQ",
        }
        last = parts[-1].upper().rstrip(".,")
        if last in street_types:
            street_type = last
            street_name = " ".join(parts[1:-1])
        else:
            street_type = ""
            street_name = " ".join(parts[1:])

        return await self.scrape_property(
            house_number, street_name, street_type, **kwargs
        )

    # ==================================================================
    # Tab scraping
    # ==================================================================

    async def _scrape_tab(self, page, tab_name: str) -> dict[str, Any]:
        """Click a tab link and extract its table data."""
        # Find and click the tab
        clicked = False
        nav_links = await page.query_selector_all("a")
        for link in nav_links:
            text = (await link.text_content() or "").strip()
            href = await link.get_attribute("href") or ""
            if text == tab_name and ("Datalet" in href or "datalet" in href or "#" in href):
                try:
                    await link.click()
                    await page.wait_for_timeout(3000)
                    clicked = True
                    break
                except Exception as e:
                    logger.debug("Click failed for tab %s: %s", tab_name, e)

        if not clicked:
            # Partial match fallback
            search_term = tab_name.split("/")[0].strip().lower()
            for link in nav_links:
                text = (await link.text_content() or "").strip()
                if search_term in text.lower():
                    href = await link.get_attribute("href") or ""
                    if href:
                        try:
                            await link.click()
                            await page.wait_for_timeout(3000)
                            clicked = True
                            break
                        except Exception:
                            pass

        if not clicked:
            return {"_status": "tab_not_found"}

        # Extract all table rows
        rows_data = []
        rows = await page.query_selector_all("table tr")
        for row in rows:
            cells = await row.query_selector_all("td, th")
            texts = []
            for c in cells:
                t = (await c.text_content() or "").strip()
                t = re.sub(r"\s+", " ", t)
                if t:
                    texts.append(t)
            if texts and len(texts) <= 10:
                # Skip navigation/footer rows
                joined = " ".join(texts).lower()
                if any(skip in joined for skip in [
                    "return to search", "location google", "contact us",
                    "site links", "loudoun.gov", "printable version",
                    "printable summary", "actions", "glossary",
                    "neighborhood sales", "copyright",
                ]):
                    continue
                if any(skip in joined for skip in ["maintenance"]):
                    continue
                rows_data.append(texts)

        # Build key-value pairs from 2-column rows
        kv_pairs = {}
        for row_texts in rows_data:
            if len(row_texts) == 2:
                kv_pairs[row_texts[0]] = row_texts[1]
            elif len(row_texts) == 4:
                kv_pairs[row_texts[0]] = row_texts[1]
                kv_pairs[row_texts[2]] = row_texts[3]
            elif len(row_texts) == 6:
                kv_pairs[row_texts[0]] = row_texts[1]
                kv_pairs[row_texts[2]] = row_texts[3]
                kv_pairs[row_texts[4]] = row_texts[5]

        return {
            "_rows": rows_data,
            "_row_count": len(rows_data),
            "_key_values": kv_pairs,
        }

    # ==================================================================
    # Structured summary builder
    # ==================================================================

    def _build_summary(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Build a clean structured summary from raw tab data."""
        summary: dict[str, Any] = {}

        # Profile
        profile_kv = raw.get("Profile", {}).get("_key_values", {})
        summary["parcel_id"] = self._find_value(profile_kv, "PARID", prefix=True)
        summary["owner"] = profile_kv.get("Name")
        summary["address"] = profile_kv.get("Primary Address")
        summary["mailing_address"] = profile_kv.get("Mailing Address")
        summary["tax_map"] = profile_kv.get("Tax Map #")
        summary["state_use_class"] = profile_kv.get("State Use Class")
        summary["lot_acres"] = profile_kv.get("Total Land Area (Acreage)")
        summary["election_district"] = profile_kv.get("Election District")
        summary["billing_district"] = profile_kv.get("Billing District")
        summary["structure_occupancy"] = profile_kv.get("Structure Occupancy")
        summary["subdivision"] = profile_kv.get("Subdivision")
        summary["legal_description"] = profile_kv.get("Legal Description")
        summary["instrument_number"] = profile_kv.get("Instrument Number")
        summary["adu"] = profile_kv.get("Affordable Dwelling Unit (Y/N)")
        summary["solar"] = profile_kv.get("Solar Exemption?")

        # Values (current year)
        values_kv = raw.get("Values", {}).get("_key_values", {})
        summary["assessed_land"] = values_kv.get("Fair Market Land")
        summary["assessed_building"] = values_kv.get("Fair Market Building")
        summary["assessed_total"] = values_kv.get("Fair Market Total")
        summary["taxable_value"] = values_kv.get("Total Taxable Value")
        summary["tax_exempt_code"] = values_kv.get("Tax Exempt Code")

        # Values history (from rows)
        values_rows = raw.get("Values", {}).get("_rows", [])
        assessment_history = []
        for row in values_rows:
            if len(row) >= 4 and row[0] in ("Notice", "Landbook"):
                # Try to find the year from context (section headers like "2025 Values")
                pass
        summary["_values_rows"] = values_rows  # raw for now

        # Sales
        sales_kv = raw.get("Sales / Transfers", {}).get("_key_values", {})
        summary["sale_date"] = sales_kv.get("Sale Date")
        summary["sale_price"] = sales_kv.get("Sale Price")
        summary["seller"] = sales_kv.get("Seller")
        summary["buyer"] = sales_kv.get("Buyer")
        summary["valuation_code"] = sales_kv.get("Valuation Code")
        summary["deed_instrument"] = sales_kv.get("Instrument Number")
        summary["recordation_date"] = sales_kv.get("Recordation Date")

        # Land
        land_kv = raw.get("Land", {}).get("_key_values", {})
        summary["land_sqft"] = land_kv.get("Square Feet")
        summary["land_acres_exact"] = land_kv.get("Acres")
        summary["land_value"] = land_kv.get("Market Land Value")
        summary["primary_zoning"] = land_kv.get("Primary Zoning")
        summary["price_per_sqft_land"] = land_kv.get("$/Sq Ft")
        summary["price_per_acre"] = land_kv.get("$/Acre")
        summary["public_water"] = land_kv.get("Public Water Available")
        summary["public_sewer"] = land_kv.get("Public Sewer Available")
        summary["easements"] = land_kv.get("Easements")

        # Residential (dwelling characteristics)
        res_kv = raw.get("Residential", {}).get("_key_values", {})
        summary["year_built"] = res_kv.get("Year Built")
        summary["style"] = res_kv.get("Style")
        summary["model"] = res_kv.get("Model")
        summary["stories"] = res_kv.get("Story Height")
        summary["exterior_wall"] = res_kv.get("Exterior Wall Material")
        summary["grade"] = res_kv.get("Grade")
        summary["condition"] = res_kv.get("Condition")
        summary["sqft_above_grade"] = res_kv.get("Net SFLA (above grade)")
        summary["full_baths"] = res_kv.get("Full Baths")
        summary["half_baths"] = res_kv.get("Half Baths")
        summary["roof_type"] = res_kv.get("Roof Type")
        summary["roof_material"] = res_kv.get("Roof Material")
        summary["heating_ac"] = res_kv.get("Heating/AC")
        summary["fireplaces"] = res_kv.get("Total Fireplaces")
        summary["basement_total_sqft"] = res_kv.get("Total Basement Area")
        summary["basement_finished_sqft"] = res_kv.get("Finished Basement Sq Ft")
        summary["basement_entrance"] = res_kv.get("Basement Entrance")
        summary["foundation"] = res_kv.get("Foundation Type")
        summary["attic_type"] = res_kv.get("Attic Type")
        summary["cathedral_ceiling_sqft"] = res_kv.get("Cathedral Ceiling/Foyer")
        summary["dwelling_pct_complete"] = res_kv.get("Dwelling % Complete")

        # Detached structures
        det_rows = raw.get("Detached Structures", {}).get("_rows", [])
        structures = []
        for row in det_rows:
            if len(row) >= 6 and row[0].isdigit():
                structures.append({
                    "type": row[2] if len(row) > 2 else "",
                    "size": row[3] if len(row) > 3 else "",
                    "year_built": row[4] if len(row) > 4 else "",
                    "condition": row[6] if len(row) > 6 else "",
                    "value": row[7] if len(row) > 7 else "",
                })
        summary["detached_structures"] = structures

        # Parcel tracking
        tracking_kv = raw.get("Parcel Tracking", {}).get("_key_values", {})
        # The raw parsing is messy — extract from rows instead
        tracking_rows = raw.get("Parcel Tracking", {}).get("_rows", [])
        for row in tracking_rows:
            if len(row) == 4 and row[0].isdigit():
                summary["parcel_split"] = {
                    "year": row[0],
                    "old_parcel": row[1],
                    "new_parcel": row[2],
                    "split_number": row[3],
                }

        # Clean up None values
        summary = {k: v for k, v in summary.items() if v is not None}

        return summary

    @staticmethod
    def _find_value(kv: dict, key_contains: str, prefix: bool = False) -> Optional[str]:
        """Find a value where the key contains or starts with a string."""
        for k, v in kv.items():
            if prefix and k.startswith(key_contains):
                return k.split(key_contains)[-1].strip() if key_contains in k else v
            elif key_contains.lower() in k.lower():
                return v
        return None
