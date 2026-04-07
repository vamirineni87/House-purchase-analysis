"""Zillow listing page scraper — 3-layer extraction.

Strategy (from testing against real listings, documented in docs/zillow_scraping_strategy.md):

Layer 1 (PRIMARY) — GraphQL interception:
    The browser naturally makes /graphql/?zpid=... calls during page render.
    We intercept those responses — they contain ALL structured property data
    (325k+ chars of clean JSON: price, beds, baths, sqft, zestimate, tax history,
    price history, schools, walk score, parcel, agent, description, photos, etc.)

Layer 2 — JSON-LD:
    Always present in initial HTML. Gives price, sqft, beds, address, lat/lon,
    open house schedule. No baths, no zestimate, no history.

Layer 3 (FALLBACK) — HTML DOM parsing:
    Uses data-testid selectors and text patterns. Gives beds, baths, sqft,
    year built, HOA (from URL params), MLS, schools, walk score.
    More fragile than GraphQL but works without JS API calls.

Anti-bot handling:
    - Non-headless browser (headless gets blocked more)
    - navigator.webdriver overridden
    - AutomationControlled blink feature disabled
    - PerimeterX "Press & Hold" CAPTCHA solved via mouse hold in iframe

All CSS selectors are class attributes for easy override when Zillow changes their DOM.
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

PARSER_VERSION = "2.0.0"  # Bumped: GraphQL-first approach


class ZillowScraper(BaseScraper):
    """Scrapes Zillow listing pages using GraphQL interception + HTML fallback.

    Usage::

        scraper = ZillowScraper(headless=False)
        data = await scraper.scrape_listing(
            "https://www.zillow.com/homedetails/.../12345_zpid/"
        )
        await scraper.close()
    """

    # CSS selectors for HTML fallback (Layer 3)
    SEL_PRICE = '[data-testid="price"]'
    SEL_BED_BATH_SQFT = '[data-testid="bed-bath-sqft-fact-container"]'
    SEL_DESCRIPTION = '[data-testid="description"]'

    async def scrape_listing(
        self,
        url: str,
        *,
        save_html_dir: Path | None = None,
        save_screenshot_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Scrape a Zillow listing. Returns structured property data dict.

        The method renders the page, handles CAPTCHAs, intercepts GraphQL
        responses, and falls back to HTML parsing for any missing fields.
        """
        await self._ensure_browser()
        await self._rate_limit_wait()

        page = await self._context.new_page()
        result: dict[str, Any] = {
            "_source": "zillow",
            "_url": url,
            "_parser_version": PARSER_VERSION,
            "_scraped_at": datetime.now(timezone.utc).isoformat(),
        }

        # Collect GraphQL responses as the page loads
        graphql_bodies: list[str] = []

        async def _capture_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.status == 200:
                    resp_url = resp.url
                    if "graphql" in resp_url or "async-create-search" in resp_url:
                        body = await resp.text()
                        if len(body) > 1000:
                            graphql_bodies.append(body)
            except Exception:
                pass

        page.on("response", _capture_response)

        try:
            import random

            # --- Load cookies from exported browser session ---
            cookie_file = Path("www.zillow.com_cookies.txt")
            if cookie_file.exists():
                logger.debug("Found cookie file: %s", cookie_file.resolve())
                await self._load_cookies_from_file(cookie_file, domain_filter="zillow.com")
            else:
                logger.debug("No cookie file found at %s", cookie_file.resolve())

            # --- Navigate ---
            logger.info("Scraping Zillow: %s", url)
            logger.debug("Pre-nav mouse movement")
            await page.mouse.move(
                random.randint(100, 800), random.randint(100, 400)
            )

            logger.debug("Navigating to URL...")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            logger.debug("Page loaded, current URL: %s", page.url)
            logger.debug("Page title: %s", await page.title())
            wait_ms = random.randint(3000, 6000)
            logger.debug("Waiting %dms before CAPTCHA check", wait_ms)
            await page.wait_for_timeout(wait_ms)

            # --- CAPTCHA handling ---
            logger.debug("Checking for CAPTCHA...")
            await self._handle_captcha(page)
            logger.debug("Post-CAPTCHA URL: %s, title: %s", page.url, await page.title())

            # --- Human-like scrolling to trigger lazy API calls ---
            logger.debug("Starting scroll sequence (8 steps)")
            for i in range(8):
                try:
                    scroll_y = (i + 1) * random.randint(600, 1000)
                    await page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    await page.wait_for_timeout(random.randint(500, 1200))
                except Exception:
                    logger.debug("Scroll interrupted at step %d", i)
                    await page.wait_for_timeout(2000)
                    break
            logger.debug("Scroll complete, captured %d GraphQL responses so far", len(graphql_bodies))
            await page.wait_for_timeout(random.randint(3000, 6000))
            logger.debug("Final GraphQL response count: %d", len(graphql_bodies))

            # --- Get page HTML for fallback ---
            html = await page.content()
            logger.debug("Page HTML length: %d chars", len(html))

            # Check for bot detection in HTML
            if "captcha" in html.lower() or "blocked" in html.lower() or "access denied" in html.lower():
                logger.warning("Bot detection keywords found in page HTML")
                # Save a debug screenshot always when bot detected
                try:
                    debug_path = Path("storage/debug_bot_detected.png")
                    debug_path.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(debug_path), full_page=True)
                    logger.info("Bot detection screenshot saved to %s", debug_path)
                except Exception as e:
                    logger.warning("Failed to save debug screenshot: %s", e)

            # Save HTML snapshot
            if save_html_dir:
                save_html_dir.mkdir(parents=True, exist_ok=True)
                zpid = re.search(r"(\d+)_zpid", url)
                fname = f"zillow_{zpid.group(1) if zpid else 'unknown'}.html"
                path = save_html_dir / fname
                path.write_text(html, encoding="utf-8")
                result["_raw_html_path"] = str(path)
                logger.debug("Saved HTML snapshot: %s", path)

            # Save screenshot
            if save_screenshot_dir:
                save_screenshot_dir.mkdir(parents=True, exist_ok=True)
                zpid = re.search(r"(\d+)_zpid", url)
                fname = f"zillow_{zpid.group(1) if zpid else 'unknown'}.png"
                path = save_screenshot_dir / fname
                await page.screenshot(path=str(path), full_page=True)
                result["_screenshot_path"] = str(path)
                logger.debug("Saved screenshot: %s", path)

            # ==============================================
            # Layer 1: GraphQL interception (PRIMARY)
            # ==============================================
            logger.debug("Extracting from %d GraphQL responses...", len(graphql_bodies))
            graphql_data = self._extract_from_graphql(graphql_bodies)
            if graphql_data:
                result.update(graphql_data)
                result["_extraction_method"] = "graphql"
                logger.info("GraphQL extraction: %d fields (keys: %s)", len(graphql_data),
                           ", ".join(sorted(graphql_data.keys())[:15]))
            else:
                logger.warning("GraphQL extraction returned NO data from %d responses", len(graphql_bodies))

            # ==============================================
            # Layer 2: JSON-LD (fills gaps)
            # ==============================================
            logger.debug("Extracting from JSON-LD...")
            jsonld_data = self._extract_from_jsonld(html)
            if jsonld_data:
                filled = 0
                for k, v in jsonld_data.items():
                    if k not in result or result[k] is None:
                        result[k] = v
                        filled += 1
                if "_extraction_method" not in result:
                    result["_extraction_method"] = "jsonld"
                logger.debug("JSON-LD filled %d fields (total: %d)", filled, len(jsonld_data))
            else:
                logger.debug("JSON-LD returned no data")

            # ==============================================
            # Layer 3: HTML DOM parsing (fills remaining gaps)
            # ==============================================
            logger.debug("Extracting from HTML DOM...")
            html_data = self._extract_from_html(html)
            if html_data:
                filled = 0
                for k, v in html_data.items():
                    if k not in result or result[k] is None:
                        result[k] = v
                        filled += 1
                if "_extraction_method" not in result:
                    result["_extraction_method"] = "html_fallback"
                logger.debug("HTML DOM filled %d fields (total: %d)", filled, len(html_data))
            else:
                logger.debug("HTML DOM returned no data")

            # Clean up None values
            result = {k: v for k, v in result.items() if v is not None}

            logger.info(
                "Zillow scrape complete: %d fields via %s (price=%s, beds=%s, sqft=%s)",
                len(result),
                result.get("_extraction_method", "unknown"),
                result.get("price"), result.get("bedrooms"), result.get("sqft"),
            )
            return result

        except Exception:
            logger.exception("Failed to scrape Zillow listing: %s", url)
            result["_error"] = "scrape_failed"
            return result
        finally:
            await page.close()

    async def scrape_by_address(
        self,
        street_address: str,
        city: str = "",
        state: str = "VA",
        **kwargs,
    ) -> dict[str, Any]:
        """Scrape a Zillow listing by street address (works for sold properties too).

        Constructs a Zillow address search URL and follows through to the listing.
        """
        # Zillow address URL format: /homes/{address}-{city}-{state}_rb/
        addr_slug = re.sub(r"[^a-zA-Z0-9]+", "-", street_address.strip()).strip("-")
        city_slug = re.sub(r"[^a-zA-Z0-9]+", "-", city.strip()).strip("-") if city else ""
        parts = [addr_slug]
        if city_slug:
            parts.append(city_slug)
        parts.append(state.upper())
        search_path = "-".join(parts)
        url = f"https://www.zillow.com/homes/{search_path}_rb/"

        logger.info("Zillow address search: %s → %s", street_address, url)
        return await self.scrape_listing(url, **kwargs)

    # ==================================================================
    # CAPTCHA handling
    # ==================================================================

    async def _handle_captcha(self, page, max_attempts: int = 3):
        """Detect and solve PerimeterX Press & Hold CAPTCHA.

        The CAPTCHA element (#px-captcha) lives inside an iframe. We find it,
        get its bounding box (which is in main-page coordinates), then
        press-and-hold with the main page mouse for 10-12 seconds.
        """
        import random

        for attempt in range(max_attempts):
            captcha_el = None

            # Check for various bot detection pages
            page_title = await page.title()
            page_url = page.url
            logger.debug("CAPTCHA check — title: %r, url: %s", page_title, page_url)

            # Check for Cloudflare or other challenge pages
            content_sample = await page.evaluate("document.body?.innerText?.substring(0, 500) || ''")
            if any(kw in content_sample.lower() for kw in ["access denied", "blocked", "robot", "unusual traffic"]):
                logger.warning("Bot detection page detected: %s", content_sample[:200])
                # Save screenshot for debugging
                try:
                    debug_path = Path("storage/debug_captcha.png")
                    debug_path.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(debug_path))
                    logger.info("Saved CAPTCHA debug screenshot to %s", debug_path)
                except Exception:
                    pass

            # Search inside iframes for #px-captcha
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    el = await frame.query_selector("#px-captcha")
                    if el:
                        captcha_el = el
                        break
                except Exception:
                    pass

            # Also check main page
            if not captcha_el:
                captcha_el = await page.query_selector("#px-captcha")

            if not captcha_el:
                if attempt == 0:
                    logger.debug("No CAPTCHA detected")
                return  # No CAPTCHA, proceed

            box = await captcha_el.bounding_box()
            if not box:
                logger.warning("CAPTCHA found but no bounding box")
                return

            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2

            # If bounding box is full-page, the element is the iframe container
            # The button is roughly centered, slightly below middle
            if box["width"] > 500 and box["height"] > 500:
                cy = box["y"] + box["height"] / 2 + 30

            logger.info(
                "CAPTCHA attempt %d: pressing at (%.0f, %.0f) for ~12s",
                attempt + 1, cx, cy,
            )

            # Human-like mouse movement with randomization
            await page.mouse.move(
                cx - random.randint(20, 50),
                cy - random.randint(10, 30),
            )
            await page.wait_for_timeout(random.randint(150, 400))
            await page.mouse.move(cx + random.randint(-3, 3), cy + random.randint(-3, 3))
            await page.wait_for_timeout(random.randint(200, 500))
            await page.mouse.down()
            # Hold for 10-14 seconds (randomized)
            await page.wait_for_timeout(random.randint(10000, 14000))
            await page.mouse.up()

            # Wait for page to potentially reload
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(random.randint(4000, 7000))

            # Check if cleared
            still_there = None
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    still_there = await frame.query_selector("#px-captcha")
                    if still_there:
                        break
                except Exception:
                    pass
            if not still_there:
                still_there = await page.query_selector("#px-captcha")

            if not still_there:
                logger.info("CAPTCHA cleared on attempt %d", attempt + 1)
                await page.wait_for_timeout(random.randint(5000, 10000))
                return

            logger.warning("CAPTCHA still present after attempt %d", attempt + 1)

        logger.error("Failed to clear CAPTCHA after %d attempts", max_attempts)

    # ==================================================================
    # Layer 1: GraphQL extraction
    # ==================================================================

    def _extract_from_graphql(self, bodies: list[str]) -> dict[str, Any]:
        """Extract property data from intercepted GraphQL responses.

        Finds the main property response (largest one with bedrooms+price)
        and parses all structured fields from it.
        """
        # Find the main property response
        main_body = None
        search_body = None

        for body in bodies:
            if '"bedrooms"' in body and '"price"' in body:
                if not main_body or len(body) > len(main_body):
                    main_body = body
            if '"zestimate"' in body and '"rentZestimate"' in body:
                search_body = body

        if not main_body:
            return {}

        result: dict[str, Any] = {}

        # Simple field extraction
        simple_fields = [
            ("price", r'"price"\s*:\s*(\d+)', int),
            ("bedrooms", r'"bedrooms"\s*:\s*(\d+)', int),
            ("bathrooms", r'"bathrooms"\s*:\s*(\d+)', int),
            ("full_bathrooms", r'"fullBathrooms"\s*:\s*(\d+)', int),
            ("half_bathrooms", r'"halfBathrooms"\s*:\s*(\d+)', int),
            ("sqft", r'"livingArea"\s*:\s*(\d+)', int),
            ("above_grade_sqft", r'"aboveGradeFinishedArea"\s*:\s*"?(\d+)', int),
            ("below_grade_sqft", r'"belowGradeFinishedArea"\s*:\s*"?(\d+)', int),
            ("year_built", r'"yearBuilt"\s*:\s*(\d+)', int),
            ("hoa_monthly", r'"(?:hoaFee|monthlyHoaFee)"\s*:\s*(\d+)', int),
            ("annual_tax", r'"taxAnnualAmount"\s*:\s*(\d+)', int),
            ("tax_assessed_value", r'"taxAssessedValue"\s*:\s*(\d+)', int),
            ("tax_assessed_year", r'"taxAssessedYear"\s*:\s*(\d+)', int),
            ("days_on_zillow", r'"daysOnZillow"\s*:\s*(-?\d+)', int),
            ("lot_sqft", r'"lotSize"\s*:\s*(\d+)', int),
            ("lot_acres", r'"lotAreaValue"\s*:\s*([\d.]+)', float),
            ("latitude", r'"latitude"\s*:\s*([\d.\-]+)', float),
            ("longitude", r'"longitude"\s*:\s*([\d.\-]+)', float),
            ("status", r'"homeStatus"\s*:\s*"([^"]+)"', str),
            ("home_type", r'"homeType"\s*:\s*"([^"]+)"', str),
            ("county", r'"county"\s*:\s*"([^"]+)"', str),
            ("parcel_id", r'"parcelId"\s*:\s*"([^"]+)"', str),
            ("mls_id", r'"mlsId"\s*:\s*"([^"]+)"', str),
            ("street_address", r'"streetAddress"\s*:\s*"([^"]+)"', str),
            ("city", r'"city"\s*:\s*"([^"]+)"', str),
            ("state", r'"state"\s*:\s*"([^"]+)"', str),
            ("zipcode", r'"zipcode"\s*:\s*"([^"]+)"', str),
            ("property_tax_rate", r'"propertyTaxRate"\s*:\s*([\d.]+)', float),
            ("time_on_zillow", r'"timeOnZillow"\s*:\s*"([^"]+)"', str),
            ("page_view_count", r'"pageViewCount"\s*:\s*(\d+)', int),
            ("favorite_count", r'"favoriteCount"\s*:\s*(\d+)', int),
            ("brokerage", r'"brokerageName"\s*:\s*"([^"]+)"', str),
            ("agent_name", r'"agentName"\s*:\s*"([^"]+)"', str),
            ("agent_phone", r'"agentPhoneNumber"\s*:\s*"([^"]+)"', str),
            ("is_new_construction", r'"isNewConstruction"\s*:\s*(true|false)', str),
        ]

        for name, pat, convert in simple_fields:
            m = re.search(pat, main_body)
            if m:
                try:
                    result[name] = convert(m.group(1))
                except (ValueError, TypeError):
                    result[name] = m.group(1)

        # Compute baths as X.5 format if we have full+half
        if result.get("full_bathrooms") and result.get("half_bathrooms"):
            result["baths"] = result["full_bathrooms"] + result["half_bathrooms"] * 0.5

        # Description
        desc = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', main_body)
        if desc:
            result["description"] = (
                desc.group(1)
                .replace("\\n", "\n")
                .replace("\\u0027", "'")
                .replace('\\"', '"')
            )

        # Price history
        ph_section = re.search(r'"priceHistory"\s*:\s*\[(.*?)\]', main_body, re.DOTALL)
        if ph_section:
            entries = re.findall(
                r'"date"\s*:\s*"([^"]+)".*?"price"\s*:\s*(\d+).*?"event"\s*:\s*"([^"]*)"',
                ph_section.group(1),
            )
            if entries:
                result["price_history"] = [
                    {"date": d, "price": int(p), "event": e}
                    for d, p, e in entries
                ]

                # Compute CDOM (cumulative days on market) from price history
                # Only count "Listed for sale" events (not "Sold" events or lot listings)
                # A listing episode = Listed → (price changes) → Removed/Sold
                from datetime import date as date_type
                listed_events = []  # (date, price)
                removed_events = []  # (date,)
                sold_events = []  # (date, price)

                for d, p, e in entries:
                    try:
                        dt = date_type.fromisoformat(d)
                        e_lower = e.lower()
                        price = int(p)
                        # Skip lot listings (very low price relative to others)
                        if price < 50000:
                            continue
                        if "listed" in e_lower and "removed" not in e_lower:
                            listed_events.append((dt, price))
                        elif "removed" in e_lower:
                            removed_events.append(dt)
                        elif "sold" in e_lower:
                            sold_events.append((dt, price))
                    except (ValueError, TypeError):
                        pass

                if listed_events:
                    # Sort chronologically
                    listed_events.sort()
                    first_listed = listed_events[0][0]
                    last_listed = listed_events[-1][0]

                    # CDOM = sum of all active listing periods
                    # Each period: listed_date → next removed_date (or today)
                    cdom = 0
                    for i, (list_dt, _) in enumerate(listed_events):
                        # Find the end of this listing period
                        end_dt = date_type.today()
                        for rem_dt in sorted(removed_events):
                            if rem_dt > list_dt:
                                end_dt = rem_dt
                                break
                        for sold_dt, _ in sorted(sold_events):
                            if sold_dt > list_dt and sold_dt < end_dt:
                                end_dt = sold_dt
                                break
                        # Don't double-count overlapping periods
                        period_days = (end_dt - list_dt).days
                        cdom += max(0, period_days)

                    result["cdom"] = cdom
                    result["dom"] = result.get("days_on_zillow", (date_type.today() - last_listed).days)
                    result["first_listed_date"] = first_listed.isoformat()
                    result["current_listed_date"] = last_listed.isoformat()
                    result["listing_episodes_count"] = len(listed_events)
                    result["total_price_reductions"] = len([
                        e for _, _, e in entries if "price change" in e.lower()
                    ])
                    # Original ask vs current ask
                    if len(listed_events) >= 1:
                        result["original_ask"] = listed_events[0][1]
                        result["total_reduction"] = listed_events[0][1] - result.get("price", 0)
                    if len(listed_events) > 1:
                        result["was_relisted"] = True

        # Tax history (timestamps are Unix epoch in ms)
        th_section = re.search(r'"taxHistory"\s*:\s*\[(.*?)\]', main_body, re.DOTALL)
        if th_section:
            entries = re.findall(
                r'"time"\s*:\s*(\d+).*?"taxPaid"\s*:\s*([\d.]+).*?"value"\s*:\s*(\d+)',
                th_section.group(1),
            )
            if entries:
                result["tax_history"] = []
                for ts, paid, val in entries:
                    # Convert Unix timestamp to year
                    try:
                        year = datetime.fromtimestamp(int(ts), tz=timezone.utc).year
                    except (ValueError, OSError):
                        year = int(ts)
                    result["tax_history"].append({
                        "year": year,
                        "tax_paid": round(float(paid), 2),
                        "assessed_value": int(val),
                    })

        # Schools — parse from assignedSchools JSON array
        # Zillow provides: name, rating, grades, distance, level, enrollment,
        # studentTeacherRatio, studentCounselorRatio, link, percentageOfFullTimeTeachersWhoAreCertified
        assigned_match = re.search(r'"assignedSchools"\s*:\s*\[(.*?)\]', main_body, re.DOTALL)
        if assigned_match:
            try:
                schools_json = json.loads("[" + assigned_match.group(1) + "]")
                result["assigned_schools"] = [
                    {
                        "name": s.get("name"),
                        "rating": s.get("rating"),
                        "grades": s.get("grades"),
                        "distance_mi": s.get("distance"),
                        "level": s.get("level"),
                        "enrollment": s.get("enrollment"),
                        "student_teacher_ratio": s.get("studentTeacherRatio"),
                        "student_counselor_ratio": s.get("studentCounselorRatio"),
                        "pct_certified_teachers": s.get("percentageOfFullTimeTeachersWhoAreCertified"),
                        "greatschools_link": s.get("link"),
                        "district_name": s.get("districtName"),
                    }
                    for s in schools_json
                ]
            except (json.JSONDecodeError, TypeError):
                pass

        # Also get nearby schools (not just assigned)
        nearby_schools_match = re.search(r'"schools"\s*:\s*\[(.*?)\]', main_body)
        if nearby_schools_match and "assigned_schools" not in result:
            try:
                schools_json = json.loads("[" + nearby_schools_match.group(1) + "]")
                result["nearby_schools"] = [
                    {
                        "name": s.get("name"),
                        "rating": s.get("rating"),
                        "grades": s.get("grades"),
                        "distance_mi": s.get("distance"),
                        "greatschools_link": s.get("link"),
                    }
                    for s in schools_json
                ]
            except (json.JSONDecodeError, TypeError):
                # Fall back to regex
                school_entries = re.findall(
                    r'"name"\s*:\s*"([^"]+)".*?"rating"\s*:\s*(\d+).*?"distance"\s*:\s*([\d.]+)',
                    nearby_schools_match.group(1),
                )
                if school_entries:
                    result["nearby_schools"] = [
                        {"name": n, "rating": int(r), "distance_mi": float(d)}
                        for n, r, d in school_entries
                    ]

        # Zestimate from search response (more reliable than main)
        if search_body:
            zest = re.search(r'"zestimate"\s*:\s*(\d+)', search_body)
            if zest:
                result["zestimate"] = int(zest.group(1))
            rent_zest = re.search(r'"rentZestimate"\s*:\s*(\d+)', search_body)
            if rent_zest:
                result["rent_zestimate"] = int(rent_zest.group(1))

        # Photo URLs
        photos = re.findall(r'"(https://photos\.zillowstatic\.com/[^"]+)"', main_body)
        if photos:
            result["photo_urls"] = list(set(photos))

        return result

    # ==================================================================
    # Layer 2: JSON-LD extraction
    # ==================================================================

    def _extract_from_jsonld(self, html: str) -> dict[str, Any]:
        """Extract from JSON-LD structured data embedded in HTML."""
        result: dict[str, Any] = {}

        ld_blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        for block in ld_blocks:
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue

            types = data.get("@type", [])
            if isinstance(types, str):
                types = [types]

            if "RealEstateListing" in types or "Product" in types:
                offers = data.get("offers", {})
                if offers.get("price"):
                    result["price"] = int(offers["price"])

                item = offers.get("itemOffered", {})
                if item.get("numberOfBedrooms"):
                    result["bedrooms"] = int(item["numberOfBedrooms"])
                floor = item.get("floorSize", {})
                if isinstance(floor, dict) and floor.get("value"):
                    result["sqft"] = int(floor["value"])

                addr = item.get("address", {})
                if addr:
                    result["address"] = {
                        "street": addr.get("streetAddress", ""),
                        "city": addr.get("addressLocality", ""),
                        "state": addr.get("addressRegion", ""),
                        "zip": addr.get("postalCode", ""),
                    }
                geo = item.get("geo", {})
                if geo:
                    result["latitude"] = _safe_float(geo.get("latitude"))
                    result["longitude"] = _safe_float(geo.get("longitude"))

            elif "Event" in (types if isinstance(types, list) else [types]):
                if data.get("startDate"):
                    result["open_house"] = {
                        "start": data["startDate"],
                        "end": data.get("endDate"),
                        "name": data.get("name"),
                    }
                if data.get("performer"):
                    result["brokerage"] = data["performer"]

        return {k: v for k, v in result.items() if v is not None}

    # ==================================================================
    # Layer 3: HTML DOM parsing (fallback)
    # ==================================================================

    def _extract_from_html(self, html: str) -> dict[str, Any]:
        """Parse property data from rendered HTML using regex patterns.

        This is the fallback when GraphQL interception fails.
        """
        result: dict[str, Any] = {}

        # Bed/bath/sqft from data-testid containers
        facts = re.findall(
            r'data-testid="bed-bath-sqft-fact-container"[^>]*>.*?'
            r'<span[^>]*>([\d,\.]+)</span>\s*<span[^>]*>(\w+)</span>',
            html,
        )
        for val, label in facts:
            clean_val = val.replace(",", "")
            if label == "beds":
                result["bedrooms"] = int(clean_val)
            elif label == "baths":
                result["bathrooms"] = int(clean_val)
            elif label == "sqft":
                result["sqft"] = int(clean_val)

        # Price
        price = re.search(r'data-testid="price"[^>]*>[^$]*\$([\d,]+)', html)
        if price:
            result["price"] = int(price.group(1).replace(",", ""))

        # Text-based extractions
        text_patterns = [
            ("year_built", r"Built in (\d{4})", int),
            ("lot_acres", r"([\d\.]+)\s*[Aa]cres?", float),
            ("hoa_monthly", r"HOAFee=(\d+)", int),
            ("mls_id", r"MLS\s*#?\s*:?\s*([A-Z]{2,}\d+)", str),
            ("parcel_id", r"parcelId.*?(\d{10,})", str),
            ("walk_score", r"[Ww]alk\s*[Ss]core[^<\d]{0,30}(\d+)", int),
        ]
        for name, pat, convert in text_patterns:
            m = re.search(pat, html)
            if m:
                try:
                    result[name] = convert(m.group(1))
                except (ValueError, TypeError):
                    pass

        # Description
        desc = re.search(r'data-testid="description"[^>]*>(.*?)</div>', html, re.DOTALL)
        if desc:
            text = re.sub(r"<[^>]+>", " ", desc.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                result["description"] = text

        # Facts and features (all categories)
        fact_categories = re.findall(
            r'data-testid="fact-category"[^>]*>(.*?)(?=data-testid="fact-category"|data-testid="facts-and-features-wrapper-footer"|$)',
            html, re.DOTALL,
        )
        if fact_categories:
            features = {}
            for cat_html in fact_categories:
                cat_name = re.search(r"<h[56][^>]*>([^<]+)</h", cat_html)
                cat = cat_name.group(1).strip() if cat_name else "Other"
                items = re.findall(r"<li[^>]*>(.*?)</li>", cat_html, re.DOTALL)
                fact_list = []
                for item in items:
                    text = re.sub(r"<[^>]+>", " ", item).strip()
                    text = re.sub(r"\s+", " ", text)
                    if text and len(text) > 2:
                        fact_list.append(text)
                if fact_list:
                    features[cat] = fact_list
            if features:
                result["facts_and_features"] = features

        # Price history from date+price patterns
        date_prices = re.findall(
            r"(\d{1,2}/\d{1,2}/\d{4})[^$]{0,200}?\$([\d,]+)",
            html[:600000],
        )
        if date_prices and "price_history" not in result:
            seen = set()
            history = []
            for date, price_str in date_prices:
                key = f"{date}|{price_str}"
                if key not in seen:
                    seen.add(key)
                    history.append({"date": date, "price": int(price_str.replace(",", ""))})
            if history:
                result["price_history"] = history

        # Photo URLs
        photos = re.findall(r'"(https://photos\.zillowstatic\.com/[^"]+)"', html)
        if photos and "photo_urls" not in result:
            result["photo_urls"] = list(set(photos))

        return {k: v for k, v in result.items() if v is not None}


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
