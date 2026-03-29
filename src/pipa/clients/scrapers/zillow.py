"""Zillow listing page scraper.

Extracts structured property data from Zillow listing pages using
Playwright for rendering and a combination of JSON-LD, embedded data,
and CSS selectors for extraction.

Selectors will need adjustment when tested against real pages — all are
defined as class attributes for easy overriding.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from pipa.clients.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Parser version — bump when extraction logic changes materially
PARSER_VERSION = "1.0.0"


class ZillowScraper(BaseScraper):
    """Scrapes individual Zillow listing pages for property data.

    All CSS selectors are class attributes so subclasses or tests can
    override them without touching extraction logic.
    """

    # ------------------------------------------------------------------
    # Configurable CSS selectors (Zillow, as of early 2026)
    # ------------------------------------------------------------------

    # Top-level pricing / status
    SEL_PRICE = "[data-testid='price'] span"
    SEL_STATUS = "[data-testid='listing-status-label']"

    # Key facts row (beds, baths, sqft)
    SEL_BEDS = "[data-testid='bed-bath-item']:nth-child(1) strong"
    SEL_BATHS = "[data-testid='bed-bath-item']:nth-child(2) strong"
    SEL_SQFT = "[data-testid='bed-bath-item']:nth-child(3) strong"

    # Address parts
    SEL_ADDRESS_STREET = "h1[data-testid='bdp-street-address']"
    SEL_ADDRESS_CITY_STATE_ZIP = "h1[data-testid='bdp-street-address'] + span"

    # Facts & features section
    SEL_YEAR_BUILT = "[data-testid='facts-table'] span:has-text('Year built') + span"
    SEL_LOT_SIZE = "[data-testid='facts-table'] span:has-text('Lot size') + span"
    SEL_HOA = "[data-testid='facts-table'] span:has-text('HOA') + span"
    SEL_PROPERTY_TYPE = "[data-testid='facts-table'] span:has-text('Type') + span"
    SEL_DAYS_ON_MARKET = "[data-testid='facts-table'] span:has-text('on Zillow') + span"
    SEL_PARCEL_NUMBER = "[data-testid='facts-table'] span:has-text('Parcel') + span"
    SEL_MLS_NUMBER = "[data-testid='facts-table'] span:has-text('MLS') + span"

    # Estimates
    SEL_ZESTIMATE = "[data-testid='zestimate-text'] span"

    # Description
    SEL_DESCRIPTION = "[data-testid='description'] div"

    # Agent / brokerage
    SEL_LISTING_AGENT = "[data-testid='listing-agent-name']"
    SEL_LISTING_BROKERAGE = "[data-testid='listing-brokerage-name']"

    # Photo carousel
    SEL_PHOTO_IMGS = "ul[class*='photo-carousel'] img"

    # Schools
    SEL_SCHOOL_ROWS = "[data-testid='school-card']"

    # Walk score
    SEL_WALK_SCORE = "[data-testid='walk-score'] span"
    SEL_TRANSIT_SCORE = "[data-testid='transit-score'] span"
    SEL_BIKE_SCORE = "[data-testid='bike-score'] span"

    # Price / tax history tables
    SEL_PRICE_HISTORY_ROWS = "[data-testid='price-history'] table tbody tr"
    SEL_TAX_HISTORY_ROWS = "[data-testid='tax-history'] table tbody tr"

    # Nearby sold
    SEL_NEARBY_SOLD = "[data-testid='nearby-sales'] li"

    # Wait selector — if this is visible, the page has loaded enough
    SEL_WAIT = "[data-testid='price']"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape_listing(
        self,
        url: str,
        *,
        save_html_dir: Path | None = None,
        save_screenshot_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Scrape a single Zillow listing page and return structured data.

        Args:
            url: Full Zillow listing URL.
            save_html_dir: Optional directory to save the raw HTML snapshot.
            save_screenshot_dir: Optional directory to save a full-page screenshot.

        Returns:
            Dictionary of extracted listing fields.
        """
        await self._ensure_browser()
        await self._rate_limit_wait()

        page = await self._context.new_page()
        result: dict[str, Any] = {"_source": "zillow", "_url": url, "_parser_version": PARSER_VERSION}
        html_path: str | None = None
        screenshot_path: str | None = None

        try:
            logger.info("Scraping Zillow listing: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=45000)

            # Wait for price to appear (indicates listing data loaded)
            try:
                await page.wait_for_selector(self.SEL_WAIT, timeout=15000)
            except Exception:
                logger.warning("Price selector not found; page may not have loaded fully")

            html = await page.content()

            # Save HTML snapshot
            if save_html_dir:
                html_path = self._save_listing_html(html, url, save_html_dir)
                result["_raw_html_path"] = html_path

            # Save screenshot
            if save_screenshot_dir:
                screenshot_path = self._save_listing_screenshot(page, url, save_screenshot_dir)
                result["_screenshot_path"] = screenshot_path

            # ----------------------------------------------------------
            # Phase 1: Extract from JSON-LD / embedded script data
            # ----------------------------------------------------------
            json_ld_data = await self._extract_json_ld(page)
            if json_ld_data:
                result.update(self._parse_json_ld(json_ld_data))

            initial_data = await self._extract_initial_data(page)
            if initial_data:
                result.update(self._parse_initial_data(initial_data))

            # ----------------------------------------------------------
            # Phase 2: Extract from DOM selectors (fills gaps / overrides)
            # ----------------------------------------------------------
            dom_data = await self._extract_from_dom(page)
            # Merge — DOM values override JSON-LD where both exist
            for key, val in dom_data.items():
                if val is not None:
                    result[key] = val

            return result
        except Exception:
            logger.exception("Failed to scrape Zillow listing: %s", url)
            result["_error"] = "scrape_failed"
            return result
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # JSON-LD extraction
    # ------------------------------------------------------------------

    async def _extract_json_ld(self, page) -> dict | None:
        """Extract JSON-LD structured data from script tags."""
        try:
            scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in scripts:
                text = await script.inner_text()
                try:
                    data = json.loads(text)
                    # Zillow uses SingleFamilyResidence or similar
                    if isinstance(data, dict) and data.get("@type") in (
                        "SingleFamilyResidence", "Residence", "Product", "RealEstateListing",
                    ):
                        return data
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("@type") in (
                                "SingleFamilyResidence", "Residence", "Product", "RealEstateListing",
                            ):
                                return item
                except json.JSONDecodeError:
                    continue
        except Exception:
            logger.debug("No JSON-LD data found")
        return None

    def _parse_json_ld(self, data: dict) -> dict[str, Any]:
        """Parse relevant fields from JSON-LD schema data."""
        result: dict[str, Any] = {}

        # Address
        addr = data.get("address", {})
        if addr:
            result["address"] = {
                "street": addr.get("streetAddress", ""),
                "city": addr.get("addressLocality", ""),
                "state": addr.get("addressRegion", ""),
                "zip": addr.get("postalCode", ""),
            }

        # Geo
        geo = data.get("geo", {})
        if geo:
            result["latitude"] = _safe_float(geo.get("latitude"))
            result["longitude"] = _safe_float(geo.get("longitude"))

        # Description
        if data.get("description"):
            result["description"] = data["description"]

        # Photo URLs
        photos = data.get("photo") or data.get("image")
        if isinstance(photos, list):
            result["photo_urls"] = [
                p.get("contentUrl") or p if isinstance(p, dict) else str(p)
                for p in photos[:50]
            ]
        elif isinstance(photos, str):
            result["photo_urls"] = [photos]

        # Floor area
        floor_size = data.get("floorSize", {})
        if isinstance(floor_size, dict):
            result["sqft"] = _safe_float(floor_size.get("value"))

        # Beds / baths
        result["beds"] = _safe_int(data.get("numberOfRooms"))

        return {k: v for k, v in result.items() if v is not None}

    # ------------------------------------------------------------------
    # Initial data / Apollo state extraction
    # ------------------------------------------------------------------

    async def _extract_initial_data(self, page) -> dict | None:
        """Try to extract Zillow's __NEXT_DATA__ or inline initial data."""
        try:
            data = await page.evaluate("""
                () => {
                    // Next.js style
                    const nextEl = document.getElementById('__NEXT_DATA__');
                    if (nextEl) return JSON.parse(nextEl.textContent);

                    // Zillow inline data pattern
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        if (text.includes('gdpClientCache') || text.includes('apiCache')) {
                            const match = text.match(/({.*"apiCache".*})/s);
                            if (match) return JSON.parse(match[1]);
                        }
                    }
                    return null;
                }
            """)
            return data
        except Exception:
            logger.debug("No initial data blob found")
            return None

    def _parse_initial_data(self, data: dict) -> dict[str, Any]:
        """Extract fields from Zillow's embedded data cache.

        The structure is deeply nested and varies; this does best-effort
        extraction of the most useful fields.
        """
        result: dict[str, Any] = {}

        # Navigate common paths in the Zillow data cache
        try:
            # Try gdpClientCache path
            cache = data.get("gdpClientCache") or data.get("apiCache") or {}
            if isinstance(cache, str):
                cache = json.loads(cache)

            # Walk the cache looking for property data
            for key, value in (cache.items() if isinstance(cache, dict) else []):
                if not isinstance(value, str):
                    continue
                try:
                    parsed = json.loads(value)
                    prop = parsed.get("property") or parsed
                    if isinstance(prop, dict) and "zpid" in prop:
                        result.update(self._extract_from_cache_property(prop))
                        break
                except (json.JSONDecodeError, AttributeError):
                    continue
        except Exception:
            logger.debug("Could not parse initial data cache")

        return result

    def _extract_from_cache_property(self, prop: dict) -> dict[str, Any]:
        """Extract fields from a Zillow cache property object."""
        result: dict[str, Any] = {}

        result["list_price"] = _safe_float(prop.get("price"))
        result["status"] = prop.get("homeStatus", "").lower().replace("_", " ")
        result["beds"] = _safe_int(prop.get("bedrooms"))
        result["baths"] = _safe_float(prop.get("bathrooms"))
        result["sqft"] = _safe_float(prop.get("livingArea"))
        result["lot_size"] = prop.get("lotSize")
        result["year_built"] = _safe_int(prop.get("yearBuilt"))
        result["property_type"] = prop.get("homeType", "").lower().replace("_", " ")
        result["zestimate"] = _safe_float(prop.get("zestimate"))
        result["days_on_market"] = _safe_int(prop.get("daysOnZillow"))
        result["hoa_monthly"] = _safe_float(prop.get("monthlyHoaFee"))
        result["description"] = prop.get("description")
        result["mls_number"] = prop.get("mlsid")
        result["parcel_number"] = prop.get("parcelId")
        result["latitude"] = _safe_float(prop.get("latitude"))
        result["longitude"] = _safe_float(prop.get("longitude"))

        # Address
        addr = prop.get("address", {})
        if isinstance(addr, dict):
            result["address"] = {
                "street": addr.get("streetAddress", ""),
                "city": addr.get("city", ""),
                "state": addr.get("state", ""),
                "zip": addr.get("zipcode", ""),
            }

        # Price history
        ph = prop.get("priceHistory")
        if isinstance(ph, list):
            result["price_history"] = [
                {
                    "date": entry.get("date", ""),
                    "event": entry.get("event", ""),
                    "price": _safe_float(entry.get("price")),
                }
                for entry in ph
            ]

        # Tax history
        th = prop.get("taxHistory")
        if isinstance(th, list):
            result["tax_history"] = [
                {
                    "year": _safe_int(entry.get("time")),
                    "assessed_value": _safe_float(entry.get("value")),
                    "tax_amount": _safe_float(entry.get("taxPaid")),
                }
                for entry in th
            ]

        # Schools
        schools = prop.get("schools")
        if isinstance(schools, list):
            result["schools"] = [
                {
                    "name": s.get("name", ""),
                    "rating": _safe_int(s.get("rating")),
                    "distance": _safe_float(s.get("distance")),
                    "grades": s.get("grades", ""),
                }
                for s in schools
            ]

        # Agent / brokerage
        attr = prop.get("attributionInfo", {})
        if isinstance(attr, dict):
            result["listing_agent"] = attr.get("agentName")
            result["listing_brokerage"] = attr.get("brokerName")

        # Photo URLs
        photos = prop.get("photos") or prop.get("responsivePhotos")
        if isinstance(photos, list):
            urls = []
            for p in photos[:50]:
                if isinstance(p, dict):
                    # Nested structure: photos[].mixedSources.jpeg[].url
                    sources = p.get("mixedSources", {}).get("jpeg", [])
                    if sources:
                        # Get the largest
                        urls.append(sources[-1].get("url", ""))
                    elif p.get("url"):
                        urls.append(p["url"])
            if urls:
                result["photo_urls"] = urls

        # Walk / transit / bike scores
        result["walk_score"] = _safe_int(prop.get("walkScore"))
        result["transit_score"] = _safe_int(prop.get("transitScore"))
        result["bike_score"] = _safe_int(prop.get("bikeScore"))

        # Nearby sold
        nearby = prop.get("nearbySales") or prop.get("comps")
        if isinstance(nearby, list):
            result["nearby_sold"] = [
                {
                    "address": n.get("address", {}).get("streetAddress", "") if isinstance(n.get("address"), dict) else "",
                    "price": _safe_float(n.get("price")),
                    "sqft": _safe_float(n.get("livingArea")),
                    "sold_date": n.get("dateSold", ""),
                }
                for n in nearby[:20]
            ]

        return {k: v for k, v in result.items() if v is not None}

    # ------------------------------------------------------------------
    # DOM selector extraction
    # ------------------------------------------------------------------

    async def _extract_from_dom(self, page) -> dict[str, Any]:
        """Extract fields by querying DOM elements with CSS selectors."""
        result: dict[str, Any] = {}

        result["list_price"] = await self._text_as_float(page, self.SEL_PRICE)
        result["status"] = await self._text(page, self.SEL_STATUS)
        result["beds"] = await self._text_as_int(page, self.SEL_BEDS)
        result["baths"] = await self._text_as_float(page, self.SEL_BATHS)
        result["sqft"] = await self._text_as_float(page, self.SEL_SQFT)

        # Address
        street = await self._text(page, self.SEL_ADDRESS_STREET)
        city_state_zip = await self._text(page, self.SEL_ADDRESS_CITY_STATE_ZIP)
        if street:
            addr = {"street": street}
            if city_state_zip:
                parts = city_state_zip.replace(",", " ").split()
                if len(parts) >= 3:
                    addr["city"] = " ".join(parts[:-2])
                    addr["state"] = parts[-2]
                    addr["zip"] = parts[-1]
            result["address"] = addr

        # Facts section
        result["year_built"] = await self._text_as_int(page, self.SEL_YEAR_BUILT)
        result["lot_size"] = await self._text(page, self.SEL_LOT_SIZE)
        result["hoa_monthly"] = await self._text_as_float(page, self.SEL_HOA)
        result["property_type"] = await self._text(page, self.SEL_PROPERTY_TYPE)
        result["days_on_market"] = await self._text_as_int(page, self.SEL_DAYS_ON_MARKET)
        result["parcel_number"] = await self._text(page, self.SEL_PARCEL_NUMBER)
        result["mls_number"] = await self._text(page, self.SEL_MLS_NUMBER)
        result["zestimate"] = await self._text_as_float(page, self.SEL_ZESTIMATE)
        result["description"] = await self._text(page, self.SEL_DESCRIPTION)
        result["listing_agent"] = await self._text(page, self.SEL_LISTING_AGENT)
        result["listing_brokerage"] = await self._text(page, self.SEL_LISTING_BROKERAGE)

        # Scores
        result["walk_score"] = await self._text_as_int(page, self.SEL_WALK_SCORE)
        result["transit_score"] = await self._text_as_int(page, self.SEL_TRANSIT_SCORE)
        result["bike_score"] = await self._text_as_int(page, self.SEL_BIKE_SCORE)

        # Photo URLs from carousel
        photo_urls = await self._attr_list(page, self.SEL_PHOTO_IMGS, "src")
        if photo_urls:
            result["photo_urls"] = photo_urls

        # Price history
        price_history = await self._extract_table_rows(
            page, self.SEL_PRICE_HISTORY_ROWS,
            ["date", "event", "price"],
        )
        if price_history:
            result["price_history"] = price_history

        # Tax history
        tax_history = await self._extract_table_rows(
            page, self.SEL_TAX_HISTORY_ROWS,
            ["year", "assessed_value", "tax_amount"],
        )
        if tax_history:
            result["tax_history"] = tax_history

        # Schools
        schools = await self._extract_schools(page)
        if schools:
            result["schools"] = schools

        return {k: v for k, v in result.items() if v is not None}

    async def _extract_schools(self, page) -> list[dict] | None:
        """Extract school data from school cards."""
        try:
            cards = await page.query_selector_all(self.SEL_SCHOOL_ROWS)
            if not cards:
                return None
            schools = []
            for card in cards:
                name = await self._inner_text(card, "span[class*='name']")
                rating = await self._inner_text(card, "span[class*='rating']")
                distance = await self._inner_text(card, "span[class*='distance']")
                grades = await self._inner_text(card, "span[class*='grades']")
                schools.append({
                    "name": name or "",
                    "rating": _safe_int(rating),
                    "distance": _safe_float(distance),
                    "grades": grades or "",
                })
            return schools if schools else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _save_listing_html(self, html: str, url: str, save_dir: Path) -> str:
        """Save raw HTML and return the file path."""
        path = save_dir / f"zillow_{self._cache_key(url)}.html"
        self._save_html_snapshot(html, path)
        return str(path)

    @staticmethod
    async def _save_listing_screenshot(page, url: str, save_dir: Path) -> str | None:
        """Save full-page screenshot and return the file path."""
        import hashlib
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        path = save_dir / f"zillow_{key}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            logger.debug("Failed to save screenshot for %s", url)
            return None

    # ------------------------------------------------------------------
    # DOM query helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _text(page, selector: str) -> str | None:
        """Get trimmed inner text of first matching element, or None."""
        try:
            el = await page.query_selector(selector)
            if el:
                t = (await el.inner_text()).strip()
                return t if t else None
        except Exception:
            pass
        return None

    @staticmethod
    async def _inner_text(el, selector: str) -> str | None:
        """Get trimmed inner text from a child selector of an element."""
        try:
            child = await el.query_selector(selector)
            if child:
                t = (await child.inner_text()).strip()
                return t if t else None
        except Exception:
            pass
        return None

    @staticmethod
    async def _text_as_float(page, selector: str) -> float | None:
        """Get text of first match, strip non-numeric, return as float."""
        try:
            el = await page.query_selector(selector)
            if el:
                t = (await el.inner_text()).strip()
                return _safe_float(t)
        except Exception:
            pass
        return None

    @staticmethod
    async def _text_as_int(page, selector: str) -> int | None:
        """Get text of first match, strip non-numeric, return as int."""
        try:
            el = await page.query_selector(selector)
            if el:
                t = (await el.inner_text()).strip()
                return _safe_int(t)
        except Exception:
            pass
        return None

    @staticmethod
    async def _attr_list(page, selector: str, attr: str) -> list[str] | None:
        """Get an attribute from all matching elements."""
        try:
            elements = await page.query_selector_all(selector)
            values = []
            for el in elements:
                val = await el.get_attribute(attr)
                if val:
                    values.append(val)
            return values if values else None
        except Exception:
            return None

    @staticmethod
    async def _extract_table_rows(
        page, selector: str, column_names: list[str]
    ) -> list[dict] | None:
        """Extract table rows where each row's <td> cells map to column_names."""
        try:
            rows = await page.query_selector_all(selector)
            if not rows:
                return None
            extracted = []
            for row in rows:
                cells = await row.query_selector_all("td")
                entry = {}
                for i, name in enumerate(column_names):
                    if i < len(cells):
                        txt = (await cells[i].inner_text()).strip()
                        entry[name] = txt
                extracted.append(entry)
            return extracted if extracted else None
        except Exception:
            return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _safe_float(val: Any) -> float | None:
    """Convert a value to float, stripping currency symbols and commas."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d.\-]", "", val)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _safe_int(val: Any) -> int | None:
    """Convert a value to int, stripping non-numeric characters."""
    f = _safe_float(val)
    return int(f) if f is not None else None
