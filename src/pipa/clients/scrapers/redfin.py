"""Redfin listing page scraper.

Extracts structured property data from Redfin listing pages using
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


class RedfinScraper(BaseScraper):
    """Scrapes individual Redfin listing pages for property data."""

    # ------------------------------------------------------------------
    # Configurable CSS selectors (Redfin, as of early 2026)
    # ------------------------------------------------------------------

    SEL_PRICE = "[data-rf-test-id='abp-price'] .statsValue"
    SEL_STATUS = ".ListingStatusBannerSection .header-text"

    SEL_BEDS = "[data-rf-test-id='abp-beds'] .statsValue"
    SEL_BATHS = "[data-rf-test-id='abp-baths'] .statsValue"
    SEL_SQFT = "[data-rf-test-id='abp-sqFt'] .statsValue"

    SEL_ADDRESS_STREET = ".street-address"
    SEL_ADDRESS_LOCALITY = ".dp-subtext .bp-cityStateZip"

    SEL_YEAR_BUILT = ".keyDetail:has-text('Year Built') .content"
    SEL_LOT_SIZE = ".keyDetail:has-text('Lot Size') .content"
    SEL_HOA = ".keyDetail:has-text('HOA Dues') .content"
    SEL_PROPERTY_TYPE = ".keyDetail:has-text('Style') .content"
    SEL_DAYS_ON_MARKET = ".keyDetail:has-text('on Redfin') .content"
    SEL_MLS_NUMBER = ".keyDetail:has-text('MLS#') .content"
    SEL_PARCEL_NUMBER = ".keyDetail:has-text('APN') .content"

    SEL_REDFIN_ESTIMATE = "[data-rf-test-id='avmLdpPrice'] .statsValue"

    SEL_DESCRIPTION = "#marketing-remarks-scroll .remarks"

    SEL_LISTING_AGENT = ".listing-agent-name"
    SEL_LISTING_BROKERAGE = ".listing-brokerage"

    SEL_PHOTO_IMGS = ".PhotoCarousel img.img-card"

    SEL_SCHOOL_ROWS = ".SchoolCard"

    SEL_WALK_SCORE = ".walkscore .score"
    SEL_TRANSIT_SCORE = ".transitscore .score"
    SEL_BIKE_SCORE = ".bikescore .score"

    SEL_PRICE_HISTORY_ROWS = ".PropertyHistoryEventRow"
    SEL_TAX_HISTORY_ROWS = ".TaxHistoryRow"

    SEL_NEARBY_SOLD = ".nearby-sales-card"

    SEL_WAIT = "[data-rf-test-id='abp-price']"

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
        """Scrape a single Redfin listing page and return structured data."""
        await self._ensure_browser()
        await self._rate_limit_wait()

        page = await self._context.new_page()
        result: dict[str, Any] = {"_source": "redfin", "_url": url, "_parser_version": PARSER_VERSION}

        try:
            logger.info("Scraping Redfin listing: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=45000)

            try:
                await page.wait_for_selector(self.SEL_WAIT, timeout=15000)
            except Exception:
                logger.warning("Price selector not found on Redfin; page may not have loaded fully")

            html = await page.content()

            # Save HTML snapshot
            if save_html_dir:
                path = save_html_dir / f"redfin_{self._cache_key(url)}.html"
                self._save_html_snapshot(html, path)
                result["_raw_html_path"] = str(path)

            # Save screenshot
            if save_screenshot_dir:
                import hashlib
                key = hashlib.sha256(url.encode()).hexdigest()[:16]
                ss_path = save_screenshot_dir / f"redfin_{key}.png"
                ss_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    await page.screenshot(path=str(ss_path), full_page=True)
                    result["_screenshot_path"] = str(ss_path)
                except Exception:
                    logger.debug("Failed to save Redfin screenshot")

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
            logger.exception("Failed to scrape Redfin listing: %s", url)
            result["_error"] = "scrape_failed"
            return result
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Embedded data extraction
    # ------------------------------------------------------------------

    async def _extract_embedded_data(self, page) -> dict | None:
        """Extract Redfin's __NEXT_DATA__ or server-rendered data blob."""
        try:
            data = await page.evaluate("""
                () => {
                    // Next.js pattern
                    const nextEl = document.getElementById('__NEXT_DATA__');
                    if (nextEl) return JSON.parse(nextEl.textContent);

                    // Redfin sometimes embeds data in a script with specific pattern
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        if (text.includes('reactServerAgent.reply') || text.includes('rdcPageInit')) {
                            // Extract JSON object from assignment pattern
                            const match = text.match(/initialData\\s*=\\s*({.*?});/s);
                            if (match) return JSON.parse(match[1]);
                        }
                    }
                    return null;
                }
            """)
            return data
        except Exception:
            logger.debug("No embedded data found on Redfin page")
            return None

    def _parse_embedded_data(self, data: dict) -> dict[str, Any]:
        """Parse fields from Redfin's embedded data."""
        result: dict[str, Any] = {}

        # Navigate the __NEXT_DATA__ structure
        try:
            props = data.get("props", {}).get("pageProps", {})
            listing = (
                props.get("propertyData")
                or props.get("initialRedfinData", {}).get("propertyData")
                or props.get("property")
                or {}
            )
            if not listing:
                return result

            result["list_price"] = _safe_float(listing.get("listPrice") or listing.get("price"))
            result["status"] = listing.get("listingStatus", "").lower()
            result["beds"] = _safe_int(listing.get("beds") or listing.get("numBedrooms"))
            result["baths"] = _safe_float(listing.get("baths") or listing.get("numBathrooms"))
            result["sqft"] = _safe_float(listing.get("sqFt") or listing.get("sqftInfo", {}).get("amount"))
            result["lot_size"] = listing.get("lotSize")
            result["year_built"] = _safe_int(listing.get("yearBuilt"))
            result["property_type"] = listing.get("propertyType", "").lower()
            result["hoa_monthly"] = _safe_float(listing.get("hoaDues"))
            result["days_on_market"] = _safe_int(listing.get("dom") or listing.get("daysOnRedfin"))
            result["mls_number"] = listing.get("mlsId") or listing.get("listingId")
            result["parcel_number"] = listing.get("apn")
            result["description"] = listing.get("remarks") or listing.get("listingRemarks")
            result["redfin_estimate"] = _safe_float(listing.get("avm", {}).get("amount") if isinstance(listing.get("avm"), dict) else listing.get("redfinEstimate"))
            result["latitude"] = _safe_float(listing.get("latitude"))
            result["longitude"] = _safe_float(listing.get("longitude"))

            # Address
            addr_data = listing.get("address", {})
            if isinstance(addr_data, dict):
                result["address"] = {
                    "street": addr_data.get("streetAddress", ""),
                    "city": addr_data.get("city", ""),
                    "state": addr_data.get("stateOrProvince", ""),
                    "zip": addr_data.get("postalCode", ""),
                }

            # Listing agent
            agent = listing.get("listingAgent", {})
            if isinstance(agent, dict):
                result["listing_agent"] = agent.get("name")
                result["listing_brokerage"] = agent.get("officeName")

            # Price history
            ph = listing.get("priceHistory") or listing.get("propertyHistory")
            if isinstance(ph, list):
                result["price_history"] = [
                    {
                        "date": entry.get("date", ""),
                        "event": entry.get("eventDescription", ""),
                        "price": _safe_float(entry.get("price")),
                    }
                    for entry in ph
                ]

            # Tax history
            th = listing.get("taxHistory")
            if isinstance(th, list):
                result["tax_history"] = [
                    {
                        "year": _safe_int(entry.get("year")),
                        "assessed_value": _safe_float(entry.get("assessedValue")),
                        "tax_amount": _safe_float(entry.get("taxAmount")),
                    }
                    for entry in th
                ]

            # Schools
            schools = listing.get("schools")
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

            # Walk / transit / bike scores
            ws = listing.get("walkScore", {})
            if isinstance(ws, dict):
                result["walk_score"] = _safe_int(ws.get("walkscore"))
                result["transit_score"] = _safe_int(ws.get("transit", {}).get("score"))
                result["bike_score"] = _safe_int(ws.get("bike", {}).get("score"))
            else:
                result["walk_score"] = _safe_int(ws)

            # Photos
            photos = listing.get("photos")
            if isinstance(photos, list):
                result["photo_urls"] = [
                    p.get("photoUrl") or p.get("url", "") for p in photos[:50]
                    if isinstance(p, dict)
                ]

            # Nearby sold
            nearby = listing.get("nearbySoldHomes") or listing.get("comparables")
            if isinstance(nearby, list):
                result["nearby_sold"] = [
                    {
                        "address": n.get("address", ""),
                        "price": _safe_float(n.get("price")),
                        "sqft": _safe_float(n.get("sqFt")),
                        "sold_date": n.get("soldDate", ""),
                    }
                    for n in nearby[:20]
                ]
        except Exception:
            logger.debug("Could not fully parse Redfin embedded data")

        return {k: v for k, v in result.items() if v is not None}

    # ------------------------------------------------------------------
    # JSON-LD extraction
    # ------------------------------------------------------------------

    async def _extract_json_ld(self, page) -> dict | None:
        """Extract JSON-LD from Redfin page."""
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

        photos = data.get("photo") or data.get("image")
        if isinstance(photos, list):
            result["photo_urls"] = [
                p.get("contentUrl") or str(p) if isinstance(p, dict) else str(p)
                for p in photos[:50]
            ]

        return {k: v for k, v in result.items() if v is not None}

    # ------------------------------------------------------------------
    # DOM extraction
    # ------------------------------------------------------------------

    async def _extract_from_dom(self, page) -> dict[str, Any]:
        """Extract fields from Redfin DOM using CSS selectors."""
        result: dict[str, Any] = {}

        result["list_price"] = await self._text_as_float(page, self.SEL_PRICE)
        result["status"] = await self._text(page, self.SEL_STATUS)
        result["beds"] = await self._text_as_int(page, self.SEL_BEDS)
        result["baths"] = await self._text_as_float(page, self.SEL_BATHS)
        result["sqft"] = await self._text_as_float(page, self.SEL_SQFT)

        # Address
        street = await self._text(page, self.SEL_ADDRESS_STREET)
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
        result["lot_size"] = await self._text(page, self.SEL_LOT_SIZE)
        result["hoa_monthly"] = await self._text_as_float(page, self.SEL_HOA)
        result["property_type"] = await self._text(page, self.SEL_PROPERTY_TYPE)
        result["days_on_market"] = await self._text_as_int(page, self.SEL_DAYS_ON_MARKET)
        result["mls_number"] = await self._text(page, self.SEL_MLS_NUMBER)
        result["parcel_number"] = await self._text(page, self.SEL_PARCEL_NUMBER)
        result["redfin_estimate"] = await self._text_as_float(page, self.SEL_REDFIN_ESTIMATE)
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
        """Extract school data from Redfin school cards."""
        try:
            cards = await page.query_selector_all(self.SEL_SCHOOL_ROWS)
            if not cards:
                return None
            schools = []
            for card in cards:
                name = await self._inner_text(card, ".school-name")
                rating = await self._inner_text(card, ".school-rating")
                distance = await self._inner_text(card, ".school-distance")
                grades = await self._inner_text(card, ".school-grades")
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
