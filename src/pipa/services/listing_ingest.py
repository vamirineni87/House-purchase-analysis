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
        headless: bool = True,
    ):
        self.storage_dir = storage_dir
        self.headless = headless
        self._scrapers: dict[str, ZillowScraper | RedfinScraper | RealtorScraper] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_from_url(
        self,
        db: AsyncSession,
        url: str,
    ) -> tuple[Property, ListingPageSnapshot]:
        """Scrape a listing URL and create/update property records.

        Steps:
        1. Detect source site from URL.
        2. Scrape the listing page.
        3. Resolve or create the Property (by address match).
        4. Create ListingPageSnapshot with parsed_fields.
        5. Create/update AddressHistory from scraped address.
        6. Create/update ListingEpisode from scraped data.
        7. Store scraped facts as EvidenceItem records.
        8. If parcel_number found, create ParcelIdentifier.

        Returns:
            Tuple of (property, snapshot).

        Raises:
            ValueError: If URL source cannot be detected.
        """
        source_site = self.detect_source(url)
        if source_site == "unknown":
            raise ValueError(f"Cannot detect listing source from URL: {url}")

        # Scrape the page
        scraped = await self._scrape(source_site, url)

        now = datetime.now(timezone.utc)

        # Build an address string for property resolution
        address_str = self._build_address_string(scraped)
        if not address_str:
            raise ValueError("Scraper did not extract a usable address from the listing page")

        # Resolve or create property
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

        # Update address with geo data if available
        if not is_new:
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
            "Ingested %s listing for property %s from %s",
            source_site,
            prop.id,
            url,
        )
        return prop, snapshot

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

        return await scraper.scrape_listing(
            url,
            save_html_dir=html_dir,
            save_screenshot_dir=screenshot_dir,
        )

    def _get_scraper(self, source_site: str):
        """Get or create a scraper instance for the given source site."""
        if source_site not in self._scrapers:
            scraper_cls = self._SCRAPER_CLASSES.get(source_site)
            if scraper_cls is None:
                raise ValueError(f"No scraper available for source: {source_site}")
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
        """Build a comma-separated address string from scraped data."""
        addr = scraped.get("address")
        if not isinstance(addr, dict):
            return None
        street = addr.get("street", "").strip()
        city = addr.get("city", "").strip()
        state = addr.get("state", "").strip()
        zip_code = addr.get("zip", "").strip()

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

        if existing:
            # Update existing episode
            existing.status = status
            if scraped.get("list_price"):
                existing.original_list_price = scraped["list_price"]
            if scraped.get("beds"):
                existing.bedrooms = scraped["beds"]
            if scraped.get("baths"):
                existing.bathrooms = scraped["baths"]
            if scraped.get("sqft"):
                existing.sqft = scraped["sqft"]
            if scraped.get("year_built"):
                existing.year_built = scraped["year_built"]
            if scraped.get("mls_number"):
                existing.mls_number = scraped["mls_number"]
            if scraped.get("days_on_market"):
                existing.days_on_market = scraped["days_on_market"]
            await db.flush()
        else:
            # Create new episode
            episode = ListingEpisode(
                property_id=prop.id,
                source=f"{source_site}_listing",
                original_list_price=scraped.get("list_price"),
                original_list_date=now,
                status=status,
                bedrooms=scraped.get("beds"),
                bathrooms=scraped.get("baths"),
                sqft=scraped.get("sqft"),
                year_built=scraped.get("year_built"),
                mls_number=scraped.get("mls_number"),
                days_on_market=scraped.get("days_on_market"),
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
        """Store key scraped facts as EvidenceItem records."""
        # Fields to store as evidence (field_name -> scraped key)
        evidence_fields = {
            "list_price": "list_price",
            "beds": "beds",
            "baths": "baths",
            "sqft": "sqft",
            "year_built": "year_built",
            "lot_size": "lot_size",
            "hoa_monthly": "hoa_monthly",
            "property_type": "property_type",
            "days_on_market": "days_on_market",
            "zestimate": "zestimate",
            "redfin_estimate": "redfin_estimate",
            "walk_score": "walk_score",
            "transit_score": "transit_score",
            "bike_score": "bike_score",
            "listing_agent": "listing_agent",
            "listing_brokerage": "listing_brokerage",
            "mls_number": "mls_number",
            "parcel_number": "parcel_number",
            "description": "description",
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

        # Detect county from scraped address
        addr = scraped.get("address", {})
        county = detect_county(
            addr.get("city", ""),
            addr.get("state", "VA"),
            addr.get("zip", ""),
        ) or "unknown"

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
