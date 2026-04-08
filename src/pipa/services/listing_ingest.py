"""Listing ingest service — import properties from listing URLs.

The primary entry point for the buyer copilot: paste a Zillow/Redfin/Realtor
URL and this service scrapes the page, creates (or resolves) a Property,
stores the snapshot, and wires up evidence items.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.clients.scrapers.realtor import RealtorScraper
from pipa.clients.scrapers.redfin import RedfinScraper
from pipa.clients.scrapers.zillow import ZillowScraper
from pipa.models.listing import ListingEpisode
from pipa.models.listing_page import ListingPageSnapshot
from pipa.models.property import AddressHistory, ParcelIdentifier, Property
from pipa.models.source import EvidenceItem, SourceRecord
from pipa.services.property_resolver import PropertyResolverService
from pipa.utils.geo import detect_county, normalize_address

logger = logging.getLogger(__name__)


# Match a Zillow detail-page URL slug:
#   /homedetails/22817-Portico-Pl-Ashburn-VA-20148/82567800_zpid/
_ZILLOW_DETAIL_RE = re.compile(r"/homedetails/([^/]+)/(\d+)_zpid")


def _parse_zillow_url_slug(url: str) -> Optional[dict]:
    """Best-effort placeholder address parse from a Zillow detail URL.

    Returns a dict with street/city/state/zip_code/address_str/zpid, or
    None if the URL is not a Zillow detail page or the slug can't be split.

    The result is a *placeholder* — used so the property record can be
    created instantly. The background Zillow scrape later overwrites the
    address row with the real Zillow address (which may differ in
    abbreviation/casing/multi-word city handling).

    Heuristic: Zillow slugs are dash-separated:
        {house}-{street-words...}-{city-words...}-{STATE}-{ZIP}
    Working from the right: zip is 5 digits, state is 2 uppercase letters,
    city is the next single token (multi-word cities like "Falls Church"
    will be slightly wrong but get fixed by the bg scrape).
    """
    m = _ZILLOW_DETAIL_RE.search(url)
    if not m:
        return None
    slug = m.group(1)
    zpid = m.group(2)

    parts = slug.split("-")
    if len(parts) < 5:
        return None

    # zip = last token (5 digits)
    if not (parts[-1].isdigit() and len(parts[-1]) == 5):
        return None
    zip_code = parts[-1]

    # state = second-to-last (2 uppercase letters)
    if not (len(parts[-2]) == 2 and parts[-2].isupper()):
        return None
    state = parts[-2]

    # city = third-to-last single token (best-effort)
    city = parts[-3]

    # street = everything before the city, joined
    street_parts = parts[:-3]
    if not street_parts:
        return None
    street = " ".join(street_parts)

    address_str = f"{street}, {city}, {state} {zip_code}"
    return {
        "street": street,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "address_str": address_str,
        "zpid": zpid,
    }


class ListingIngestService:
    """Imports properties from listing site URLs or manual address entry.

    Orchestrates scraping, property resolution, snapshot storage, and
    evidence item creation.
    """

    # Map of source site -> scraper class
    _SCRAPER_CLASSES = {
        "zillow": ZillowScraper,
        "redfin": RedfinScraper,
        "realtor": RealtorScraper,
    }

    def __init__(
        self,
        storage_dir: Path = Path("./storage"),
        headless: bool = False,  # Non-headless works much better for CAPTCHA bypass
    ):
        self.storage_dir = storage_dir
        self.headless = headless
        self._scrapers: dict[str, ZillowScraper | RedfinScraper | RealtorScraper] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_placeholder_from_url(
        self,
        db: AsyncSession,
        url: str,
    ) -> Property:
        """Create a Property + placeholder AddressHistory from a Zillow URL.

        Used by the /properties/ingest endpoint to return a 201 in ~100ms.
        The slow Zillow scrape (and everything after it) runs in the
        background via run_post_ingest_chain. The placeholder address may
        be off in casing/abbreviation/multi-word-city splits — the bg
        scrape overwrites the address row with the real one.

        Raises ValueError if the URL is not a recognised listing source or
        if the slug can't be parsed into an address.
        """
        source_site = self.detect_source(url)
        if source_site == "unknown":
            raise ValueError(f"Cannot detect listing source from URL: {url}")

        if source_site != "zillow":
            # For now only Zillow URLs have a reliable address slug parser.
            # Redfin/Realtor will need their own.
            raise ValueError(
                f"Instant ingest currently only supports Zillow URLs (got {source_site})"
            )

        parsed = _parse_zillow_url_slug(url)
        if not parsed:
            raise ValueError(f"Could not extract address from Zillow URL: {url}")

        logger.info(
            "Creating placeholder property from URL slug: %s (zpid=%s)",
            parsed["address_str"], parsed["zpid"],
        )

        prop, is_new = await PropertyResolverService.resolve_or_create(
            db,
            parsed["address_str"],
            property_type="single_family",
        )

        # Reload with relationships for the response
        result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == prop.id)
        )
        prop = result.scalar_one()

        if is_new:
            logger.info("Placeholder property %s created for %s", prop.id, url)
        else:
            logger.info("Resolved existing property %s for %s", prop.id, url)
        return prop

    async def ingest_from_url(
        self,
        db: AsyncSession,
        url: str,
    ) -> tuple[Property, ListingPageSnapshot]:
        """Scrape a listing URL and create/update property records.

        Synchronous full-scrape ingest path. The instant API path uses
        create_placeholder_from_url + run_post_ingest_chain instead.
        This method is kept for CLI usage (run_pipeline.py) and tests.
        """
        source_site = self.detect_source(url)
        logger.debug("Detected source: %s for URL: %s", source_site, url)
        if source_site == "unknown":
            raise ValueError(f"Cannot detect listing source from URL: {url}")

        # Scrape the page
        logger.info("Starting scrape for %s listing: %s", source_site, url)
        scraped = await self._scrape(source_site, url)
        logger.info("Scrape returned %d fields, extraction_method=%s",
                    len(scraped), scraped.get("_extraction_method", "none"))
        logger.debug("Scraped keys: %s", sorted(scraped.keys()))

        if scraped.get("_error"):
            logger.error("Scraper returned error: %s", scraped["_error"])

        prop, snapshot = await self._persist_scrape(db, source_site, url, scraped)
        return prop, snapshot

    async def _persist_scrape(
        self,
        db: AsyncSession,
        source_site: str,
        url: str,
        scraped: dict,
        existing_property: Optional[Property] = None,
    ) -> tuple[Property, ListingPageSnapshot]:
        """Persist scraped listing data into the DB.

        Resolves the property by address (or uses ``existing_property`` if
        provided — used by the bg flow where the placeholder property was
        already created from the URL slug). Creates SourceRecord,
        ListingPageSnapshot, ListingEpisode, EvidenceItems, ParcelIdentifier.

        Returns (property, snapshot).
        """
        now = datetime.now(timezone.utc)

        address_str = self._build_address_string(scraped)
        logger.debug("Built address string: %r from scraped address: %r",
                     address_str, scraped.get("address"))
        if not address_str and existing_property is None:
            logger.error("No usable address extracted. Scraped data keys: %s",
                        sorted(scraped.keys()))
            raise ValueError("Scraper did not extract a usable address from the listing page")

        # Resolve property: use the placeholder if provided, otherwise
        # resolve-or-create from the scraped address.
        if existing_property is not None:
            prop = existing_property
            is_new = False
        else:
            prop, is_new = await PropertyResolverService.resolve_or_create(
                db, address_str, property_type=self._infer_property_type(scraped)
            )

        # Create SourceRecord for audit trail
        source_record = SourceRecord(
            property_id=prop.id,
            source_name=f"{source_site}_listing",
            source_url=url,
            raw_payload=scraped,
            fetched_at=now,
        )
        db.add(source_record)
        await db.flush()

        # Create ListingPageSnapshot
        snapshot = ListingPageSnapshot(
            property_id=prop.id,
            source_site=source_site,
            listing_url=url,
            scraped_at=now,
            parsed_fields=scraped,
            raw_html_path=scraped.get("_raw_html_path"),
            screenshot_path=scraped.get("_screenshot_path"),
            parser_version=scraped.get("_parser_version", "1.0.0"),
        )
        db.add(snapshot)
        await db.flush()

        # If we came in via the placeholder path (existing_property passed),
        # clean up the placeholder address with the real scraped values.
        if existing_property is not None:
            await self._clean_placeholder_address(db, prop, scraped)

        # Update lat/lon if scrape returned them
        await self._update_address_geo(db, prop, scraped)

        # Create or update ListingEpisode
        await self._create_listing_episode(db, prop, scraped, source_site, now)

        # Store evidence items for key facts
        await self._create_evidence_items(db, prop, scraped, source_record, now)

        # Create ParcelIdentifier if parcel_number found
        if scraped.get("parcel_number"):
            await self._create_parcel_identifier(db, prop, scraped, source_record)

        # Reload property with relationships
        result = await db.execute(
            select(Property)
            .options(
                selectinload(Property.addresses),
                selectinload(Property.parcel_identifiers),
            )
            .where(Property.id == prop.id)
        )
        prop = result.scalar_one()

        logger.info(
            "Persisted %s listing scrape for property %s from %s",
            source_site, prop.id, url,
        )
        return prop, snapshot

    # ------------------------------------------------------------------
    # Background auto-chain (runs AFTER the HTTP response is sent)
    # ------------------------------------------------------------------

    @staticmethod
    async def run_post_ingest_chain(
        property_id: str,
        listing_url: Optional[str] = None,
        source_site: str = "zillow",
    ) -> None:
        """Run the full ingest pipeline in the background.

        Steps (each with its own DB session, committing after each so the
        UI can see partial progress immediately):
            0. Scrape the listing (Zillow / Redfin / Realtor) and persist
               the snapshot, evidence items, and listing episode. Cleans
               up the URL-slug placeholder address with the real one.
            1. County scrape (assessments, permits, deeds, components,
               neighborhood sales).
            2. School boundaries.
            3. Quick comp (uses the Neighborhood Sales tab + listing nearby).
            4. Full analysis pipeline (AI Pass 1, resolver, financial,
               condition, warning engine, AI Pass 2, decision packet).

        Each step is wrapped in try/except so a failure (or 5-minute Claude
        CLI hang on AI Pass 1) doesn't block earlier steps from being
        visible. Per-step timing is logged so we can see which step is
        currently running when the UI refreshes mid-pipeline.
        """
        import time
        from pipa.core.dependencies import get_config, get_session_factory

        factory = get_session_factory()
        chain_start = time.monotonic()
        logger.info("[bg] === Post-ingest chain START for property %s ===", property_id)

        listing_data: dict | None = None

        # --- 0. Listing scrape (replaces the URL-slug placeholder) ---
        if listing_url:
            step_start = time.monotonic()
            logger.info("[bg] step 0/4: Listing scrape START (%s)", listing_url)
            async with factory() as db:
                config = get_config()
                bg_service = ListingIngestService(
                    storage_dir=config.storage_dir,
                    headless=config.scrapers.playwright_headless,
                )
                try:
                    # Reload the placeholder property so we can pass it through
                    result = await db.execute(
                        select(Property)
                        .options(
                            selectinload(Property.addresses),
                            selectinload(Property.parcel_identifiers),
                        )
                        .where(Property.id == property_id)
                    )
                    prop = result.scalar_one_or_none()
                    if prop is None:
                        logger.error("[bg] Placeholder property %s not found", property_id)
                        return

                    scraped = await bg_service._scrape(source_site, listing_url)
                    logger.info(
                        "[bg] Scrape returned %d fields, extraction_method=%s",
                        len(scraped), scraped.get("_extraction_method", "none"),
                    )

                    await bg_service._persist_scrape(
                        db, source_site, listing_url, scraped,
                        existing_property=prop,
                    )
                    await db.commit()
                    listing_data = scraped
                    logger.info(
                        "[bg] step 0/4: Listing scrape DONE in %.1fs",
                        time.monotonic() - step_start,
                    )
                except Exception:
                    await db.rollback()
                    logger.warning(
                        "[bg] step 0/4: Listing scrape FAILED for %s after %.1fs",
                        property_id, time.monotonic() - step_start, exc_info=True,
                    )
                finally:
                    await bg_service.close()

        # --- 1. County scrape (must run before quick_comp) ---
        step_start = time.monotonic()
        logger.info("[bg] step 1/4: County scrape START")
        async with factory() as db:
            try:
                from pipa.services.data_refresh import DataRefreshService
                county_result = await DataRefreshService.refresh_source(db, property_id, "county")
                await db.commit()
                logger.info(
                    "[bg] step 1/4: County scrape DONE in %.1fs (%s)",
                    time.monotonic() - step_start, county_result,
                )
            except Exception:
                await db.rollback()
                logger.warning(
                    "[bg] step 1/4: County scrape FAILED after %.1fs",
                    time.monotonic() - step_start, exc_info=True,
                )

        # --- 2. School boundaries (LCPS) ---
        step_start = time.monotonic()
        logger.info("[bg] step 2/4: School scrape START")
        async with factory() as db:
            try:
                from pipa.services.data_refresh import DataRefreshService
                school_result = await DataRefreshService.refresh_source(db, property_id, "schools")
                await db.commit()
                logger.info(
                    "[bg] step 2/4: School scrape DONE in %.1fs (%s)",
                    time.monotonic() - step_start, school_result,
                )
            except Exception:
                await db.rollback()
                logger.warning(
                    "[bg] step 2/4: School scrape FAILED after %.1fs",
                    time.monotonic() - step_start, exc_info=True,
                )

        # --- 3. Quick comp (consumes the county Neighborhood Sales) ---
        step_start = time.monotonic()
        logger.info("[bg] step 3/4: Quick comp START")
        async with factory() as db:
            try:
                from pipa.services.comp_service import CompService
                await CompService.quick_comp(db, property_id)
                await db.commit()
                logger.info(
                    "[bg] step 3/4: Quick comp DONE in %.1fs",
                    time.monotonic() - step_start,
                )
            except Exception:
                await db.rollback()
                logger.warning(
                    "[bg] step 3/4: Quick comp FAILED after %.1fs",
                    time.monotonic() - step_start, exc_info=True,
                )

        # --- 4. Full analysis pipeline (AI + financial + condition + decision)
        # Mid-run checkpoint commit after `condition` so the UI sees AI Pass 1,
        # resolver, financial, tax, and condition results immediately, without
        # having to wait for the slow tail (offer/stress/warning_engine/AI
        # Pass 2/decision_packet) to finish.
        step_start = time.monotonic()
        logger.info("[bg] step 4/4: Full pipeline START")
        async with factory() as db:
            try:
                from pipa.services.pipeline_orchestrator import PipelineOrchestrator
                run = await PipelineOrchestrator.start_run(
                    db, property_id, "full_pipeline", initiated_by="ingest_bg"
                )
                await db.commit()
                run = await PipelineOrchestrator.execute_run(
                    db, run.id,
                    listing_data=listing_data,
                    commit_after_tasks={"condition"},
                )
                await db.commit()
                logger.info(
                    "[bg] step 4/4: Full pipeline DONE in %.1fs (status=%s)",
                    time.monotonic() - step_start, run.status,
                )
            except Exception:
                await db.rollback()
                logger.warning(
                    "[bg] step 4/4: Full pipeline FAILED after %.1fs",
                    time.monotonic() - step_start, exc_info=True,
                )

        logger.info(
            "[bg] === Post-ingest chain DONE for property %s in %.1fs ===",
            property_id, time.monotonic() - chain_start,
        )

    async def ingest_from_address(
        self,
        db: AsyncSession,
        address: str,
        property_type: str = "single_family",
    ) -> Property:
        """Create a property from a manual address entry (no URL).

        Resolves existing property by address or creates a new one.
        Does not perform any scraping.

        Returns:
            The resolved or created Property.
        """
        prop, is_new = await PropertyResolverService.resolve_or_create(
            db, address, property_type=property_type
        )

        if is_new:
            logger.info("Created property %s from manual address: %s", prop.id, address)
        else:
            logger.info("Resolved existing property %s for address: %s", prop.id, address)

        return prop

    # ------------------------------------------------------------------
    # Source detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_source(url: str) -> str:
        """Detect the listing source site from a URL.

        Returns:
            One of: "zillow", "redfin", "realtor", or "unknown".
        """
        try:
            parsed = urlparse(url.strip().lower())
            host = parsed.hostname or ""
        except Exception:
            return "unknown"

        if "zillow.com" in host:
            return "zillow"
        if "redfin.com" in host:
            return "redfin"
        if "realtor.com" in host:
            return "realtor"

        return "unknown"

    # ------------------------------------------------------------------
    # Scraping orchestration
    # ------------------------------------------------------------------

    async def _scrape(self, source_site: str, url: str) -> dict:
        """Get or create a scraper and scrape the listing."""
        scraper = self._get_scraper(source_site)

        html_dir = self.storage_dir / "html_snapshots" / source_site
        screenshot_dir = self.storage_dir / "screenshots" / source_site
        logger.debug("Scrape dirs — html: %s, screenshot: %s", html_dir, screenshot_dir)

        result = await scraper.scrape_listing(
            url,
            save_html_dir=html_dir,
            save_screenshot_dir=screenshot_dir,
        )
        logger.debug("Scraper.scrape_listing returned %d keys", len(result))
        return result

    def _get_scraper(self, source_site: str):
        """Get or create a scraper instance for the given source site."""
        if source_site not in self._scrapers:
            scraper_cls = self._SCRAPER_CLASSES.get(source_site)
            if scraper_cls is None:
                raise ValueError(f"No scraper available for source: {source_site}")
            logger.debug("Creating %s scraper (headless=%s)", source_site, self.headless)
            self._scrapers[source_site] = scraper_cls(headless=self.headless)
        return self._scrapers[source_site]

    async def close(self):
        """Close all scraper browser instances."""
        for scraper in self._scrapers.values():
            await scraper.close()
        self._scrapers.clear()

    # ------------------------------------------------------------------
    # Data wiring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_address_string(scraped: dict) -> str | None:
        """Build a comma-separated address string from scraped data.

        Reads from both the GraphQL top-level fields (street_address /
        city / state / zipcode) and the JSON-LD nested address dict so
        we don't miss data depending on which extraction layer fired.
        """
        addr = scraped.get("address") if isinstance(scraped.get("address"), dict) else {}
        street = (scraped.get("street_address") or addr.get("street") or "").strip()
        city = (scraped.get("city") or addr.get("city") or "").strip()
        state = (scraped.get("state") or addr.get("state") or "").strip()
        zip_code = (
            scraped.get("zipcode")
            or scraped.get("zip_code")
            or scraped.get("zip")
            or addr.get("zip")
            or addr.get("zip_code")
            or ""
        ).strip()

        if not street or not city:
            return None

        parts = [street, city]
        if state and zip_code:
            parts.append(f"{state} {zip_code}")
        elif state:
            parts.append(state)

        return ", ".join(parts)

    @staticmethod
    def _infer_property_type(scraped: dict) -> str:
        """Infer property_type from scraped data."""
        raw = (scraped.get("property_type") or "").lower()

        type_map = {
            "single family": "single_family",
            "single_family": "single_family",
            "singlefamily": "single_family",
            "house": "single_family",
            "condo": "condo",
            "condominium": "condo",
            "townhouse": "townhouse",
            "townhome": "townhouse",
            "multi family": "multi_family",
            "multi_family": "multi_family",
            "multifamily": "multi_family",
            "duplex": "multi_family",
            "triplex": "multi_family",
        }

        for key, value in type_map.items():
            if key in raw:
                return value

        return "single_family"

    async def _update_address_geo(
        self, db: AsyncSession, prop: Property, scraped: dict
    ):
        """Update existing address with latitude/longitude if available."""
        lat = scraped.get("latitude")
        lon = scraped.get("longitude")
        if lat is None and lon is None:
            return

        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.property_id == prop.id,
                AddressHistory.is_current.is_(True),
                AddressHistory.address_type == "situs",
            )
        )
        addr = result.scalar_one_or_none()
        if addr:
            if lat is not None:
                addr.latitude = lat
            if lon is not None:
                addr.longitude = lon
            await db.flush()

    async def _clean_placeholder_address(
        self, db: AsyncSession, prop: Property, scraped: dict
    ):
        """Replace any placeholder address text with the real scraped address.

        Used by the bg flow: the property was created from a URL-slug
        placeholder (e.g. "Stone Ridge" mistakenly split as city="Ridge"),
        then the real Zillow scrape comes back with the canonical address.
        We update the existing AddressHistory row in place — no new
        history row — since the placeholder isn't actual history, just a
        stand-in for "we hadn't scraped yet".

        Field-level merge: each field is only overwritten when the scrape
        actually returned a value for it. The placeholder zip survives if
        Zillow GraphQL didn't return one. After merging the individual
        fields, ``raw_address`` and ``normalized_address`` are rebuilt
        from the *merged* row state so they stay consistent.

        Reads from BOTH the GraphQL top-level fields (street_address /
        city / state / zipcode) AND the JSON-LD nested address dict, so
        we don't miss data depending on which extraction layer fired.
        """
        # Prefer GraphQL top-level fields. JSON-LD's nested address dict
        # ("address": {street, city, state, zip}) is the fallback. Note:
        # scraped["address"] is sometimes a dict and sometimes absent.
        addr_dict = scraped.get("address") if isinstance(scraped.get("address"), dict) else {}

        scraped_street = (scraped.get("street_address") or addr_dict.get("street") or "").strip()
        scraped_city = (scraped.get("city") or addr_dict.get("city") or "").strip()
        scraped_state = (scraped.get("state") or addr_dict.get("state") or "").strip()
        scraped_zip = (
            scraped.get("zipcode")
            or scraped.get("zip_code")
            or scraped.get("zip")
            or addr_dict.get("zip")
            or addr_dict.get("zip_code")
            or ""
        ).strip()

        if not (scraped_street or scraped_city or scraped_state or scraped_zip):
            return  # Nothing usable

        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.property_id == prop.id,
                AddressHistory.is_current.is_(True),
                AddressHistory.address_type == "situs",
            )
        )
        addr = result.scalar_one_or_none()
        if addr is None:
            return

        # --- Per-field merge: only overwrite when scrape returned a value ---
        changed = False

        # The placeholder doesn't have a separate "street" column on
        # AddressHistory; it lives only inside raw_address. So we track
        # the street value in a local and rebuild raw_address at the end.
        merged_street = scraped_street if scraped_street else self._extract_street_from_raw(addr.raw_address)

        if scraped_city and addr.city != scraped_city:
            addr.city = scraped_city
            changed = True
        if scraped_state and addr.state != scraped_state:
            addr.state = scraped_state
            changed = True
        if scraped_zip and addr.zip_code != scraped_zip:
            addr.zip_code = scraped_zip
            changed = True

        # Re-detect county based on the *merged* city/state/zip values
        # (not just scrape values, since some may have come from placeholder).
        new_county = detect_county(addr.city or "", addr.state or "", addr.zip_code or "")
        if new_county and addr.county != new_county:
            addr.county = new_county
            changed = True

        # Rebuild raw_address + normalized_address from the FINAL merged
        # row state so they stay consistent with the per-field columns.
        merged_raw_parts = [merged_street, addr.city or "",
                            f"{addr.state or ''} {addr.zip_code or ''}".strip()]
        new_raw = ", ".join(p for p in merged_raw_parts if p)
        new_normalized = normalize_address(new_raw) if new_raw else addr.normalized_address

        if new_raw and addr.raw_address != new_raw:
            addr.raw_address = new_raw
            changed = True
        if new_normalized and addr.normalized_address != new_normalized:
            addr.normalized_address = new_normalized
            changed = True

        if changed:
            logger.info(
                "Cleaned placeholder address for property %s -> %r",
                prop.id, new_raw,
            )
            await db.flush()

    @staticmethod
    def _extract_street_from_raw(raw_address: Optional[str]) -> str:
        """Pull the street portion out of a raw_address string.

        raw_address is stored as "street, city, state zip". We just take
        everything before the first comma.
        """
        if not raw_address:
            return ""
        return raw_address.split(",", 1)[0].strip()

    async def _create_listing_episode(
        self,
        db: AsyncSession,
        prop: Property,
        scraped: dict,
        source_site: str,
        now: datetime,
    ):
        """Create or update a ListingEpisode from scraped data."""
        # Check for existing active episode from same source
        result = await db.execute(
            select(ListingEpisode).where(
                ListingEpisode.property_id == prop.id,
                ListingEpisode.source == f"{source_site}_listing",
                ListingEpisode.status.in_(["active", "pending", "for sale"]),
            )
        )
        existing = result.scalar_one_or_none()

        status = scraped.get("status", "active")
        if isinstance(status, str):
            status = status.lower().strip()
        if not status:
            status = "active"

        # Map current scraper output keys → ListingEpisode columns.
        # The scraper writes: price, bedrooms, bathrooms, sqft, year_built,
        # mls_id, days_on_zillow. The old keys (list_price/beds/baths/
        # mls_number/days_on_market) were never populated by GraphQL.
        list_price = scraped.get("price")
        bedrooms = scraped.get("bedrooms")
        bathrooms = scraped.get("bathrooms") or scraped.get("baths")
        sqft = scraped.get("sqft")
        year_built = scraped.get("year_built")
        mls_number = scraped.get("mls_id") or scraped.get("mls_number")
        days_on_market = scraped.get("days_on_zillow") or scraped.get("days_on_market")

        if existing:
            existing.status = status
            if list_price is not None:
                existing.original_list_price = list_price
            if bedrooms is not None:
                existing.bedrooms = bedrooms
            if bathrooms is not None:
                existing.bathrooms = bathrooms
            if sqft is not None:
                existing.sqft = sqft
            if year_built is not None:
                existing.year_built = year_built
            if mls_number is not None:
                existing.mls_number = mls_number
            if days_on_market is not None:
                existing.days_on_market = days_on_market
            await db.flush()
        else:
            episode = ListingEpisode(
                property_id=prop.id,
                source=f"{source_site}_listing",
                original_list_price=list_price,
                original_list_date=now,
                status=status,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                sqft=sqft,
                year_built=year_built,
                mls_number=mls_number,
                days_on_market=days_on_market,
            )
            db.add(episode)
            await db.flush()

    async def _create_evidence_items(
        self,
        db: AsyncSession,
        prop: Property,
        scraped: dict,
        source_record: SourceRecord,
        now: datetime,
    ):
        """Store key scraped facts as EvidenceItem records.

        Field names match the current Zillow scraper output (price,
        bedrooms, bathrooms, lot_sqft, etc.) — NOT the older list_price /
        beds / baths / lot_size which were never populated by the
        modern GraphQL-first extractor.
        """
        # Fields to store as evidence (evidence_field_name -> scraped key)
        evidence_fields = {
            "list_price": "price",
            "beds": "bedrooms",
            "baths": "bathrooms",
            "sqft": "sqft",
            "year_built": "year_built",
            "lot_sqft": "lot_sqft",
            "lot_acres": "lot_acres",
            "hoa_monthly": "hoa_monthly",
            "property_type": "home_type",
            "days_on_market": "days_on_zillow",
            "zestimate": "zestimate",
            "rent_zestimate": "rent_zestimate",
            "walk_score": "walk_score",
            "transit_score": "transit_score",
            "bike_score": "bike_score",
            "listing_agent": "agent_name",
            "listing_brokerage": "brokerage",
            "mls_number": "mls_id",
            "parcel_number": "parcel_id",
            "description": "description",
            # Construction (from facts_and_features normalization)
            "architectural_style": "architectural_style",
            "builder_model": "builder_model",
            "zillow_condition": "zillow_condition",
            "subdivision": "subdivision",
        }

        for field_name, scraped_key in evidence_fields.items():
            value = scraped.get(scraped_key)
            if value is None:
                continue
            # Truncate long descriptions for evidence storage
            str_value = str(value)
            if len(str_value) > 500:
                str_value = str_value[:497] + "..."

            evidence = EvidenceItem(
                property_id=prop.id,
                field_name=field_name,
                field_value=str_value,
                source_record_id=source_record.id,
                observed_at=now,
                confidence="estimated",
            )
            db.add(evidence)

        await db.flush()

    async def _create_parcel_identifier(
        self,
        db: AsyncSession,
        prop: Property,
        scraped: dict,
        source_record: SourceRecord,
    ):
        """Create a ParcelIdentifier if not already present."""
        parcel_number = scraped.get("parcel_number")
        if not parcel_number:
            return

        # Detect county from scraped address. Read from BOTH the
        # GraphQL top-level fields AND the JSON-LD nested address dict
        # so we never trip on a None or missing key. Defaults to "unknown"
        # if nothing usable is found.
        addr_dict = scraped.get("address") if isinstance(scraped.get("address"), dict) else {}
        city = scraped.get("city") or addr_dict.get("city") or ""
        state = scraped.get("state") or addr_dict.get("state") or "VA"
        zip_code = (
            scraped.get("zipcode")
            or scraped.get("zip_code")
            or scraped.get("zip")
            or addr_dict.get("zip")
            or addr_dict.get("zip_code")
            or ""
        )
        county = detect_county(city, state, zip_code) or "unknown"

        # Check if this parcel ID already exists
        result = await db.execute(
            select(ParcelIdentifier).where(
                ParcelIdentifier.property_id == prop.id,
                ParcelIdentifier.identifier_type == "parcel_number",
                ParcelIdentifier.identifier_value == str(parcel_number),
            )
        )
        if result.scalar_one_or_none() is not None:
            return  # Already exists

        pid = ParcelIdentifier(
            property_id=prop.id,
            county=county,
            identifier_type="parcel_number",
            identifier_value=str(parcel_number),
            is_current=True,
            valid_from=datetime.now(timezone.utc),
            source_record_id=source_record.id,
        )
        db.add(pid)
        await db.flush()
