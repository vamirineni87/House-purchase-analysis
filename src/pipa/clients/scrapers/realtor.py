"""Realtor.com listing page scraper.

Extracts structured property data from Realtor.com listing pages using
Playwright for rendering and a combination of embedded JSON data
and CSS selectors.

Selectors will need adjustment when tested against real pages — all are
defined as class attributes for easy overriding.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pipa.clients.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PARSER_VERSION = "1.0.0"


def _safe_float(val: Any) -> float | None:
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
    f = _safe_float(val)
    return int(f) if f is not None else None


class RealtorScraper(BaseScraper):
    """Scrapes individual Realtor.com listing pages for property data."""

    # ------------------------------------------------------------------
    # Configurable CSS selectors (Realtor.com, as of early 2026)
    # ------------------------------------------------------------------

    SEL_PRICE = "[data-testid='list-price']"
    SEL_STATUS = "[data-testid='listing-status']"

    SEL_BEDS = "[data-testid='property-meta-beds'] .meta-value"
    SEL_BATHS = "[data-testid='property-meta-baths'] .meta-value"
    SEL_SQFT = "[data-testid='property-meta-sqft'] .meta-value"
    SEL_LOT_SIZE = "[data-testid='property-meta-lot-size'] .meta-value"

    SEL_ADDRESS_FULL = "[data-testid='address-line']"
    SEL_ADDRESS_LOCALITY = "[data-testid='address-locality']"

    SEL_YEAR_BUILT = "[data-testid='property-detail-year-built'] .detail-value"
    SEL_HOA = "[data-testid='property-detail-hoa'] .detail-value"
    SEL_PROPERTY_TYPE = "[data-testid='property-detail-type'] .detail-value"
    SEL_DAYS_ON_MARKET = "[data-testid='property-detail-days-on-market'] .detail-value"
    SEL_MLS_NUMBER = "[data-testid='property-detail-mls'] .detail-value"
    SEL_PARCEL_NUMBER = "[data-testid='property-detail-apn'] .detail-value"

    SEL_DESCRIPTION = "[data-testid='listing-description']"

    SEL_LISTING_AGENT = "[data-testid='listing-agent-name']"
    SEL_LISTING_BROKERAGE = "[data-testid='listing-brokerage-name']"

    SEL_PHOTO_IMGS = "[data-testid='gallery-photo'] img"

    SEL_SCHOOL_ROWS = "[data-testid='school-info-card']"

    SEL_WALK_SCORE = "[data-testid='walk-score-value']"
    SEL_TRANSIT_SCORE = "[data-testid='transit-score-value']"
    SEL_BIKE_SCORE = "[data-testid='bike-score-value']"

    SEL_PRICE_HISTORY_ROWS = "[data-testid='price-history-row']"
    SEL_TAX_HISTORY_ROWS = "[data-testid='tax-history-row']"

    SEL_NEARBY_SOLD = "[data-testid='nearby-home-card']"

    SEL_WAIT = "[data-testid='list-price']"

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
        """Scrape a single Realtor.com listing page and return structured data."""
        await self._ensure_browser()
        await self._rate_limit_wait()

        page = await self._context.new_page()
        result: dict[str, Any] = {"_source": "realtor", "_url": url, "_parser_version": PARSER_VERSION}

        try:
            logger.info("Scraping Realtor.com listing: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=45000)

            try:
                await page.wait_for_selector(self.SEL_WAIT, timeout=15000)
            except Exception:
                logger.warning("Price selector not found on Realtor.com; page may not have loaded fully")

            html = await page.content()

            # Save HTML snapshot
            if save_html_dir:
                path = save_html_dir / f"realtor_{self._cache_key(url)}.html"
                self._save_html_snapshot(html, path)
                result["_raw_html_path"] = str(path)

            # Save screenshot
            if save_screenshot_dir:
                import hashlib
                key = hashlib.sha256(url.encode()).hexdigest()[:16]
                ss_path = save_screenshot_dir / f"realtor_{key}.png"
                ss_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    await page.screenshot(path=str(ss_path), full_page=True)
                    result["_screenshot_path"] = str(ss_path)
                except Exception:
                    logger.debug("Failed to save Realtor.com screenshot")

            # ----------------------------------------------------------
            # Phase 1: Extract from embedded JSON data
            # ----------------------------------------------------------
            embedded_data = await self._extract_embedded_data(page)
            if embedded_data:
                result.update(self._parse_embedded_data(embedded_data))

            json_ld = await self._extract_json_ld(page)
            if json_ld:
                result.update(self._parse_json_ld(json_ld))

            # ----------------------------------------------------------
            # Phase 2: Extract from DOM selectors
            # ----------------------------------------------------------
            dom_data = await self._extract_from_dom(page)
            for key, val in dom_data.items():
                if val is not None:
                    result[key] = val

            return result
        except Exception:
            logger.exception("Failed to scrape Realtor.com listing: %s", url)
            result["_error"] = "scrape_failed"
            return result
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Embedded data extraction
    # ------------------------------------------------------------------

    async def _extract_embedded_data(self, page) -> dict | None:
        """Extract Realtor.com's __NEXT_DATA__ or similar embedded data."""
        try:
            data = await page.evaluate("""
                () => {
                    // Next.js data
                    const nextEl = document.getElementById('__NEXT_DATA__');
                    if (nextEl) return JSON.parse(nextEl.textContent);

                    // Realtor.com may use a different pattern
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        if (text.includes('__PRELOADED_STATE__') || text.includes('propertyDetails')) {
                            const match = text.match(/__PRELOADED_STATE__\\s*=\\s*({.*?});/s);
                            if (match) return JSON.parse(match[1]);
                        }
                    }
                    return null;
                }
            """)
            return data
        except Exception:
            logger.debug("No embedded data found on Realtor.com page")
            return None

    def _parse_embedded_data(self, data: dict) -> dict[str, Any]:
        """Parse fields from Realtor.com's embedded data."""
        result: dict[str, Any] = {}

        try:
            # Navigate __NEXT_DATA__ structure
            props = data.get("props", {}).get("pageProps", {})
            listing = (
                props.get("property")
                or props.get("initialData", {}).get("data", {}).get("property_detail")
                or props.get("propertyDetails")
                or {}
            )
            if not listing:
                return result

            # Basic fields
            result["list_price"] = _safe_float(listing.get("list_price") or listing.get("price"))
            result["status"] = listing.get("status", "").lower()
            result["property_type"] = listing.get("prop_type", "").lower() or listing.get("property_type", "").lower()
            result["description"] = listing.get("description", {}).get("text") if isinstance(listing.get("description"), dict) else listing.get("description")
            result["mls_number"] = listing.get("mls_id") or listing.get("listing_id")
            result["parcel_number"] = listing.get("apn")
            result["days_on_market"] = _safe_int(listing.get("days_on_market") or listing.get("list_date_dom"))
            result["year_built"] = _safe_int(listing.get("year_built"))
            result["hoa_monthly"] = _safe_float(listing.get("hoa", {}).get("fee") if isinstance(listing.get("hoa"), dict) else listing.get("hoa_fee"))

            # Beds / baths / sqft
            desc = listing.get("description", {}) if isinstance(listing.get("description"), dict) else {}
            result["beds"] = _safe_int(desc.get("beds") or listing.get("beds"))
            result["baths"] = _safe_float(desc.get("baths") or listing.get("baths"))
            result["sqft"] = _safe_float(desc.get("sqft") or listing.get("sqft"))
            result["lot_size"] = desc.get("lot_sqft") or listing.get("lot_sqft")

            # Geo
            location = listing.get("location", {})
            if isinstance(location, dict):
                coord = location.get("address", {}).get("coordinate", {})
                if isinstance(coord, dict):
                    result["latitude"] = _safe_float(coord.get("lat"))
                    result["longitude"] = _safe_float(coord.get("lon"))
                addr = location.get("address", {})
                if isinstance(addr, dict):
                    result["address"] = {
                        "street": addr.get("line", ""),
                        "city": addr.get("city", ""),
                        "state": addr.get("state_code", ""),
                        "zip": addr.get("postal_code", ""),
                    }

            # Agent / brokerage
            source = listing.get("source", {})
            if isinstance(source, dict):
                agents = source.get("agents", [])
                if isinstance(agents, list) and agents:
                    agent = agents[0]
                    result["listing_agent"] = agent.get("agent_name")
                    result["listing_brokerage"] = agent.get("office_name") or source.get("name")

            # Price history
            ph = listing.get("price_history") or listing.get("property_history")
            if isinstance(ph, list):
                result["price_history"] = [
                    {
                        "date": entry.get("date", ""),
                        "event": entry.get("event_name", ""),
                        "price": _safe_float(entry.get("price")),
                    }
                    for entry in ph
                ]

            # Tax history
            th = listing.get("tax_history")
            if isinstance(th, list):
                result["tax_history"] = [
                    {
                        "year": _safe_int(entry.get("year")),
                        "assessed_value": _safe_float(entry.get("assessment", {}).get("total") if isinstance(entry.get("assessment"), dict) else entry.get("total")),
                        "tax_amount": _safe_float(entry.get("tax")),
                    }
                    for entry in th
                ]

            # Schools
            schools = listing.get("schools") or listing.get("nearby_schools")
            if isinstance(schools, list):
                result["schools"] = [
                    {
                        "name": s.get("name", ""),
                        "rating": _safe_int(s.get("rating")),
                        "distance": _safe_float(s.get("distance_in_miles")),
                        "grades": s.get("grades", {}).get("range", "") if isinstance(s.get("grades"), dict) else s.get("grades", ""),
                    }
                    for s in schools
                ]

            # Photos
            photos = listing.get("photos") or listing.get("photo_urls")
            if isinstance(photos, list):
                urls = []
                for p in photos[:50]:
                    if isinstance(p, dict):
                        urls.append(p.get("href") or p.get("url", ""))
                    elif isinstance(p, str):
                        urls.append(p)
                if urls:
                    result["photo_urls"] = urls

            # Nearby sold
            nearby = listing.get("nearby_homes")
            if isinstance(nearby, list):
                result["nearby_sold"] = [
                    {
                        "address": n.get("location", {}).get("address", {}).get("line", "") if isinstance(n.get("location"), dict) else "",
                        "price": _safe_float(n.get("list_price")),
                        "sqft": _safe_float(n.get("description", {}).get("sqft") if isinstance(n.get("description"), dict) else None),
                        "sold_date": n.get("last_sold_date", ""),
                    }
                    for n in nearby[:20]
                ]

        except Exception:
            logger.debug("Could not fully parse Realtor.com embedded data")

        return {k: v for k, v in result.items() if v is not None}

    # ------------------------------------------------------------------
    # JSON-LD extraction
    # ------------------------------------------------------------------

    async def _extract_json_ld(self, page) -> dict | None:
        """Extract JSON-LD structured data."""
        try:
            scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in scripts:
                text = await script.inner_text()
                try:
                    data = json.loads(text)
                    if isinstance(data, dict) and data.get("@type") in (
                        "SingleFamilyResidence", "Residence", "Product", "RealEstateListing",
                    ):
                        return data
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "@type" in item:
                                return item
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        return None

    def _parse_json_ld(self, data: dict) -> dict[str, Any]:
        """Parse relevant fields from JSON-LD."""
        result: dict[str, Any] = {}

        addr = data.get("address", {})
        if isinstance(addr, dict):
            result["address"] = {
                "street": addr.get("streetAddress", ""),
                "city": addr.get("addressLocality", ""),
                "state": addr.get("addressRegion", ""),
                "zip": addr.get("postalCode", ""),
            }

        geo = data.get("geo", {})
        if isinstance(geo, dict):
            result["latitude"] = _safe_float(geo.get("latitude"))
            result["longitude"] = _safe_float(geo.get("longitude"))

        if data.get("description"):
            result["description"] = data["description"]

        return {k: v for k, v in result.items() if v is not None}

    # ------------------------------------------------------------------
    # DOM extraction
    # ------------------------------------------------------------------

    async def _extract_from_dom(self, page) -> dict[str, Any]:
        """Extract fields from Realtor.com DOM using CSS selectors."""
        result: dict[str, Any] = {}

        result["list_price"] = await self._text_as_float(page, self.SEL_PRICE)
        result["status"] = await self._text(page, self.SEL_STATUS)
        result["beds"] = await self._text_as_int(page, self.SEL_BEDS)
        result["baths"] = await self._text_as_float(page, self.SEL_BATHS)
        result["sqft"] = await self._text_as_float(page, self.SEL_SQFT)
        result["lot_size"] = await self._text(page, self.SEL_LOT_SIZE)

        # Address
        street = await self._text(page, self.SEL_ADDRESS_FULL)
        locality = await self._text(page, self.SEL_ADDRESS_LOCALITY)
        if street:
            addr = {"street": street}
            if locality:
                parts = locality.replace(",", " ").split()
                if len(parts) >= 3:
                    addr["city"] = " ".join(parts[:-2])
                    addr["state"] = parts[-2]
                    addr["zip"] = parts[-1]
            result["address"] = addr

        result["year_built"] = await self._text_as_int(page, self.SEL_YEAR_BUILT)
        result["hoa_monthly"] = await self._text_as_float(page, self.SEL_HOA)
        result["property_type"] = await self._text(page, self.SEL_PROPERTY_TYPE)
        result["days_on_market"] = await self._text_as_int(page, self.SEL_DAYS_ON_MARKET)
        result["mls_number"] = await self._text(page, self.SEL_MLS_NUMBER)
        result["parcel_number"] = await self._text(page, self.SEL_PARCEL_NUMBER)
        result["description"] = await self._text(page, self.SEL_DESCRIPTION)
        result["listing_agent"] = await self._text(page, self.SEL_LISTING_AGENT)
        result["listing_brokerage"] = await self._text(page, self.SEL_LISTING_BROKERAGE)

        result["walk_score"] = await self._text_as_int(page, self.SEL_WALK_SCORE)
        result["transit_score"] = await self._text_as_int(page, self.SEL_TRANSIT_SCORE)
        result["bike_score"] = await self._text_as_int(page, self.SEL_BIKE_SCORE)

        photo_urls = await self._attr_list(page, self.SEL_PHOTO_IMGS, "src")
        if photo_urls:
            result["photo_urls"] = photo_urls

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
                name = await self._inner_text(card, "[data-testid='school-name']")
                rating = await self._inner_text(card, "[data-testid='school-rating']")
                distance = await self._inner_text(card, "[data-testid='school-distance']")
                grades = await self._inner_text(card, "[data-testid='school-grades']")
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
    # DOM query helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _text(page, selector: str) -> str | None:
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
