"""Automated comparable sales sourcing and enrichment.

Flow:
1. Find comp candidates from Zillow/Redfin/Realtor nearby sold + County neighborhood sales
2. For each comp, scrape Loudoun County for verified details
3. Run appraisal adjustments using county-verified data
4. Store everything as evidence
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.analysis.appraisal import run_appraisal_analysis
from pipa.clients.scrapers.loudoun_parcel import LoudounParcelScraper
from pipa.models.analysis_models import AnalysisRun
from pipa.models.listing import ListingEpisode
from pipa.models.listing_page import ListingPageSnapshot
from pipa.models.property import AddressHistory, Property
from pipa.models.source import EvidenceItem, SourceRecord
from pipa.schemas.appraisal import ComparableSale
from pipa.schemas.comp import CompCandidate, EnrichedComp

logger = logging.getLogger(__name__)

_CODE_VERSION = "0.1.0"


def _input_hash(data: dict) -> str:
    """SHA-256 hash of serialized input for change detection."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _safe_int(val: Any) -> int | None:
    """Parse an integer from a string or return None."""
    if val is None:
        return None
    try:
        cleaned = str(val).replace(",", "").strip()
        # Handle values like "2,456 sq ft" or "$450,000"
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)
        if not cleaned:
            return None
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    """Parse a float from a string or return None."""
    if val is None:
        return None
    try:
        cleaned = str(val).replace(",", "").replace("$", "").strip()
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)
        if not cleaned:
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _normalize_address(addr: str) -> str:
    """Normalize an address string for deduplication."""
    normed = addr.upper().strip()
    # Remove unit/apt/suite suffixes for matching
    normed = re.sub(r"\s*,\s*(VA|VIRGINIA)\s*\d*\s*$", "", normed)
    normed = re.sub(r"\s*,\s*[A-Z\s]+,\s*VA.*$", "", normed)
    # Normalize common abbreviations
    normed = re.sub(r"\bDR\.?\b", "DR", normed)
    normed = re.sub(r"\bST\.?\b", "ST", normed)
    normed = re.sub(r"\bCT\.?\b", "CT", normed)
    normed = re.sub(r"\bLN\.?\b", "LN", normed)
    normed = re.sub(r"\bRD\.?\b", "RD", normed)
    normed = re.sub(r"\bAVE\.?\b", "AVE", normed)
    normed = re.sub(r"\bPL\.?\b", "PL", normed)
    normed = re.sub(r"\bTER\.?\b", "TER", normed)
    normed = re.sub(r"\s+", " ", normed)
    return normed.strip()


class CompService:
    """Automated comparable sales sourcing and enrichment.

    Flow:
    1. Find comp candidates from listing site nearby sold + County neighborhood sales
    2. For each comp, scrape Loudoun County for verified details
    3. Run appraisal adjustments using county-verified data
    4. Store everything as evidence
    """

    # ------------------------------------------------------------------
    # Step 1: Find comp candidates
    # ------------------------------------------------------------------

    @staticmethod
    async def find_comp_candidates(
        db: AsyncSession, property_id: str
    ) -> list[CompCandidate]:
        """Find comparable sale candidates from available sources.

        Sources checked:
        1. Listing page snapshots (nearby_sold in parsed_fields from
           Zillow, Redfin, or Realtor GraphQL data)
        2. Loudoun County Neighborhood Sales tab (if county data exists)

        Returns list of CompCandidate sorted by sale date (most recent first).
        """
        candidates: list[dict] = []
        seen_addresses: set[str] = set()

        # --- Source 1: Listing page snapshots (nearby sold + active + pending) ---
        snapshots = await db.execute(
            select(ListingPageSnapshot).where(
                ListingPageSnapshot.property_id == property_id,
                ListingPageSnapshot.scrape_success.is_(True),
            ).order_by(ListingPageSnapshot.scraped_at.desc())
        )
        for snap in snapshots.scalars().all():
            parsed = snap.parsed_fields or {}
            source_label = f"{snap.source_site}_nearby"

            # Nearby SOLD properties (primary comps)
            for key in ("nearby_sold", "nearby_homes_raw"):
                nearby = parsed.get(key)
                if not isinstance(nearby, (list, dict)):
                    continue
                # Handle dict format from HTML extraction
                if isinstance(nearby, dict):
                    addresses = nearby.get("addresses", [])
                    prices = nearby.get("prices", [])
                    for i, addr in enumerate(addresses):
                        normed = _normalize_address(addr)
                        if normed in seen_addresses:
                            continue
                        seen_addresses.add(normed)
                        price = _safe_float(prices[i]) if i < len(prices) else None
                        candidates.append({
                            "address": addr.strip(),
                            "price": price,
                            "date": "",
                            "status": "sold",
                            "source": source_label,
                        })
                    continue
                # Handle list format from GraphQL
                for entry in nearby:
                    addr = entry.get("address", "")
                    if not addr:
                        continue
                    normed = _normalize_address(addr)
                    if normed in seen_addresses:
                        continue
                    seen_addresses.add(normed)
                    status = entry.get("status", "sold").lower()
                    if "sold" in status or "closed" in status:
                        status = "sold"
                    elif "pending" in status or "contingent" in status:
                        status = "pending"
                    elif "active" in status or "for_sale" in status:
                        status = "active"
                    candidates.append({
                        "address": addr.strip(),
                        "price": _safe_float(entry.get("price")),
                        "date": entry.get("sold_date") or entry.get("sale_date") or entry.get("list_date") or "",
                        "status": status,
                        "source": source_label,
                        "distance_mi": _safe_float(entry.get("distance")),
                        "sqft": _safe_int(entry.get("sqft")),
                        "beds": _safe_int(entry.get("beds")),
                        "baths": _safe_float(entry.get("baths")),
                        "days_on_market": _safe_int(entry.get("days_on_market") or entry.get("dom")),
                    })

        # --- Source 2: County SourceRecords (neighborhood sales) ---
        county_records = await db.execute(
            select(SourceRecord).where(
                SourceRecord.property_id == property_id,
                SourceRecord.source_name.in_([
                    "loudoun_county", "loudoun_parcel",
                ]),
            ).order_by(SourceRecord.fetched_at.desc())
        )
        for record in county_records.scalars().all():
            payload = record.raw_payload or {}
            # The Loudoun scraper stores neighborhood sales in the
            # "Sales / Transfers" tab if navigated, or sometimes in
            # the raw data from the assessment portal sidebar
            sales_tab = payload.get("Sales / Transfers", {})
            rows = sales_tab.get("_rows", [])
            for row in rows:
                # County sales rows often have: [date, price, type, ...]
                if len(row) >= 2 and row[0] and row[1]:
                    # Try to parse as sale entry from neighborhood context
                    # Skip header rows
                    if row[0].lower().startswith("sale"):
                        continue

        # Filter sold comps to last 2 quarters (6 months)
        cutoff = date.today().replace(day=1)
        # Go back 6 months
        month = cutoff.month - 6
        year = cutoff.year
        if month <= 0:
            month += 12
            year -= 1
        cutoff = cutoff.replace(year=year, month=month)
        cutoff_str = cutoff.isoformat()

        filtered = []
        for c in candidates:
            if c.get("status", "sold") != "sold":
                # Active/pending always included regardless of date
                filtered.append(c)
            else:
                # Sold comps: only last 6 months
                d = c.get("date", "")
                if not d or d >= cutoff_str:
                    filtered.append(c)
                else:
                    logger.debug("Excluding old comp: %s sold %s (cutoff %s)", c.get("address"), d, cutoff_str)

        # Sort by date (most recent first), putting None dates last
        def _sort_key(c: dict) -> str:
            d = c.get("date", "")
            return d if d else "0000-00-00"

        filtered.sort(key=_sort_key, reverse=True)

        return [CompCandidate(**c) for c in filtered]

    # ------------------------------------------------------------------
    # Step 2: Enrich a single comp from county
    # ------------------------------------------------------------------

    @staticmethod
    async def enrich_comp_from_county(
        db: AsyncSession,
        comp_address: str,
        scraper: LoudounParcelScraper | None = None,
    ) -> dict:
        """Scrape Loudoun County for verified details on a comp property.

        Returns dict with county-verified fields:
        - sqft_above_grade (NOT total -- this is what matters for comps)
        - year_built, full_baths, half_baths, lot_acres
        - basement_total_sqft, basement_finished_sqft
        - condition, grade, style, stories
        - roof_material, exterior_wall
        - sale_price, sale_date (from county deed records)
        - assessed_total
        """
        owns_scraper = False
        if scraper is None:
            scraper = LoudounParcelScraper(headless=True)
            owns_scraper = True

        try:
            logger.info("Enriching comp from county: %s", comp_address)
            county_data = await scraper.scrape_by_address_string(comp_address)

            if county_data.get("_error"):
                logger.warning(
                    "County scrape failed for %s: %s",
                    comp_address,
                    county_data["_error"],
                )
                return {"_error": county_data["_error"], "address": comp_address}

            # Parse structured fields from county tabs
            residential = CompService._parse_county_residential(county_data)
            values = CompService._parse_county_values(county_data)
            sale = CompService._parse_county_sale(county_data)

            # Also pull from the _summary if the scraper built one
            summary = county_data.get("_summary", {})

            # Merge everything, preferring directly-parsed values
            enriched: dict[str, Any] = {"address": comp_address}
            enriched.update(residential)
            enriched.update(values)
            enriched.update(sale)

            # Fill gaps from summary
            for key in [
                "year_built", "style", "condition", "grade",
                "full_baths", "half_baths", "lot_acres",
                "sqft_above_grade", "basement_total_sqft",
                "basement_finished_sqft", "foundation",
                "roof_material", "exterior_wall",
                "assessed_total",
            ]:
                if enriched.get(key) is None and summary.get(key) is not None:
                    enriched[key] = summary[key]

            # Compute total_sqft = above_grade + finished basement
            above = _safe_int(enriched.get("sqft_above_grade"))
            fin_bsmt = _safe_int(enriched.get("basement_finished_sqft"))
            if above is not None:
                enriched["sqft_above_grade"] = above
                if fin_bsmt:
                    enriched["total_sqft"] = above + fin_bsmt
                else:
                    enriched["total_sqft"] = above

            # Convert lot_acres string to float
            lot = enriched.get("lot_acres")
            if lot is not None:
                enriched["lot_acres"] = _safe_float(lot)

            # Store raw county data for audit
            enriched["_raw_county"] = county_data

            return enriched

        finally:
            if owns_scraper:
                await scraper.close()

    # ------------------------------------------------------------------
    # Step 3: Full pipeline -- find, enrich, return verified comps
    # ------------------------------------------------------------------

    @staticmethod
    async def build_verified_comps(
        db: AsyncSession,
        property_id: str,
        max_comps: int = 6,
    ) -> list[EnrichedComp]:
        """Full pipeline: find candidates, enrich from county, return verified comps.

        This is the main entry point. Takes ~2 minutes for 4-6 comps
        (each county scrape takes 15-20 seconds).

        Steps:
        1. find_comp_candidates() -- get raw list from listing sites + county
        2. For each candidate (up to max_comps):
           a. enrich_comp_from_county() -- get verified details
           b. Store as EvidenceItem with source="county_verified_comp"
        3. Return list of fully enriched comps ready for appraisal engine
        """
        candidates = await CompService.find_comp_candidates(db, property_id)
        if not candidates:
            logger.warning("No comp candidates found for property %s", property_id)
            return []

        logger.info(
            "Found %d comp candidates for property %s, enriching up to %d",
            len(candidates),
            property_id,
            max_comps,
        )

        # Reuse a single scraper instance for all county lookups
        scraper = LoudounParcelScraper(headless=True)
        enriched_comps: list[EnrichedComp] = []
        now = datetime.now(timezone.utc)

        try:
            for candidate in candidates[:max_comps]:
                enriched = await CompService.enrich_comp_from_county(
                    db, candidate.address, scraper=scraper
                )

                if enriched.get("_error"):
                    logger.warning(
                        "Skipping comp %s: county enrichment failed",
                        candidate.address,
                    )
                    continue

                # Detect sqft conflict: listing site sqft vs county above-grade
                listing_sqft = candidate.sqft
                county_sqft = _safe_int(enriched.get("sqft_above_grade"))
                sqft_conflict = False
                if listing_sqft and county_sqft:
                    pct_diff = abs(listing_sqft - county_sqft) / max(listing_sqft, 1)
                    sqft_conflict = pct_diff > 0.10

                # Resolve sale_price: prefer county, fall back to listing
                sale_price = _safe_float(enriched.get("sale_price"))
                if sale_price is None:
                    sale_price = candidate.sale_price
                if sale_price is None:
                    logger.warning(
                        "Skipping comp %s: no sale price from county or listing",
                        candidate.address,
                    )
                    continue

                # Resolve sale_date: prefer county, fall back to listing
                sale_date = enriched.get("sale_date") or candidate.sale_date or ""
                if not sale_date:
                    logger.warning(
                        "Skipping comp %s: no sale date from county or listing",
                        candidate.address,
                    )
                    continue

                comp = EnrichedComp(
                    address=candidate.address,
                    sale_price=sale_price,
                    sale_date=str(sale_date),
                    sqft_above_grade=county_sqft,
                    total_sqft=_safe_int(enriched.get("total_sqft")),
                    year_built=_safe_int(enriched.get("year_built")),
                    full_baths=_safe_int(enriched.get("full_baths")),
                    half_baths=_safe_int(enriched.get("half_baths")),
                    stories=_safe_int(enriched.get("stories")),
                    style=enriched.get("style"),
                    condition=enriched.get("condition"),
                    grade=enriched.get("grade"),
                    roof_material=enriched.get("roof_material"),
                    exterior_wall=enriched.get("exterior_wall"),
                    basement_total_sqft=_safe_int(enriched.get("basement_total_sqft")),
                    basement_finished_sqft=_safe_int(enriched.get("basement_finished_sqft")),
                    foundation=enriched.get("foundation"),
                    lot_acres=_safe_float(enriched.get("lot_acres")),
                    assessed_total=_safe_float(enriched.get("assessed_total")),
                    zillow_sqft=listing_sqft,
                    county_sqft=county_sqft,
                    sqft_conflict=sqft_conflict,
                )
                enriched_comps.append(comp)

                # Store as EvidenceItem for audit trail
                raw_county = enriched.pop("_raw_county", {})
                source_record = SourceRecord(
                    property_id=property_id,
                    source_name="county_verified_comp",
                    source_url=raw_county.get("_detail_url", ""),
                    raw_payload=raw_county,
                    fetched_at=now,
                )
                db.add(source_record)
                await db.flush()

                evidence = EvidenceItem(
                    property_id=property_id,
                    field_name=f"comp:{candidate.address}",
                    field_value=json.dumps(comp.model_dump(), default=str),
                    source_record_id=source_record.id,
                    observed_at=now,
                    confidence="confirmed",
                )
                db.add(evidence)

            await db.flush()
            logger.info(
                "Enriched %d/%d comps with county data for property %s",
                len(enriched_comps),
                len(candidates[:max_comps]),
                property_id,
            )
            return enriched_comps

        finally:
            await scraper.close()

    # ------------------------------------------------------------------
    # Step 4: End-to-end -- source comps, enrich, run appraisal
    # ------------------------------------------------------------------

    @staticmethod
    async def run_comp_analysis(
        db: AsyncSession,
        property_id: str,
        subject_data: dict | None = None,
        max_comps: int = 6,
    ) -> dict:
        """End-to-end: source comps, enrich, run appraisal analysis.

        Args:
            subject_data: dict with list_price, sqft, beds, baths, year_built
                         for the target property. If None, loads from DB.
            max_comps: maximum number of comps to enrich (each takes 15-20s).

        Returns dict with:
        - comps: list of verified comparable sales with county data
        - appraisal_result: AppraisalResult from the analysis engine
        - data_quality: dict with comp_count, county_verified_count,
                        avg_adjustment, confidence
        - conflicts: list of listing-site vs county discrepancies found
        """
        # 1. Load subject property data if not provided
        if subject_data is None:
            subject_data = await CompService._load_subject_data(db, property_id)

        list_price = subject_data.get("list_price", 0)
        sqft = subject_data.get("sqft", 0)
        beds = subject_data.get("beds", 0)
        baths = subject_data.get("baths", 0.0)
        year_built = subject_data.get("year_built")

        # 2. Find all candidates and separate by status
        all_candidates = await CompService.find_comp_candidates(db, property_id)
        sold_candidates = [c for c in all_candidates if c.status == "sold"]
        active_candidates = [c for c in all_candidates if c.status == "active"]
        pending_candidates = [c for c in all_candidates if c.status in ("pending", "contingent")]

        logger.info(
            "Comp candidates: %d sold, %d active, %d pending",
            len(sold_candidates), len(active_candidates), len(pending_candidates),
        )

        # 3. Build verified comps (county enrichment — only for sold)
        enriched_comps = await CompService.build_verified_comps(
            db, property_id, max_comps=max_comps
        )

        # 3. Convert EnrichedComp -> ComparableSale for the appraisal engine
        comparable_sales: list[ComparableSale] = []
        for comp in enriched_comps:
            # Use sqft_above_grade from county for adjustments, not total sqft
            comp_sqft = comp.sqft_above_grade or comp.total_sqft or 0
            comp_baths = (comp.full_baths or 0) + (comp.half_baths or 0) * 0.5

            # Parse sale_date to date object
            sale_date = _parse_date(comp.sale_date)
            if sale_date is None:
                sale_date = date.today()

            # Estimate bedrooms from county data or fall back to listing
            # County doesn't always have bedroom count, so we estimate
            # from sqft if needed
            comp_beds = beds  # default to subject beds if county has no data

            cs = ComparableSale(
                address=comp.address,
                sale_price=comp.sale_price,
                sale_date=sale_date,
                square_feet=comp_sqft,
                bedrooms=comp_beds,
                bathrooms=comp_baths,
                year_built=comp.year_built,
                price_per_sqft=round(comp.sale_price / max(comp_sqft, 1), 2),
            )
            comparable_sales.append(cs)

        # 4. Run appraisal analysis
        appraisal_result = run_appraisal_analysis(
            list_price=list_price,
            sqft=sqft,
            beds=beds,
            baths=baths,
            year_built=year_built,
            comps=comparable_sales,
        )

        # 5. Check for listing-site vs county conflicts
        conflicts: list[dict] = []
        for comp in enriched_comps:
            if comp.sqft_conflict:
                conflicts.append({
                    "address": comp.address,
                    "field": "sqft",
                    "listing_value": comp.zillow_sqft,
                    "county_value": comp.county_sqft,
                    "note": (
                        f"Listing site reports {comp.zillow_sqft} sqft, "
                        f"county above-grade SFLA is {comp.county_sqft} sqft "
                        f"(>{10}% difference). County value used for adjustments."
                    ),
                })

        # 6. Build data quality summary
        county_verified = sum(
            1 for c in enriched_comps if c.county_sqft is not None
        )
        avg_adjustment = 0.0
        if appraisal_result.comparables:
            total_adj = sum(
                abs(sum(c.adjustments.values()))
                for c in appraisal_result.comparables
                if c.adjustments
            )
            avg_adjustment = total_adj / len(appraisal_result.comparables)

        data_quality = {
            "comp_count": len(enriched_comps),
            "county_verified_count": county_verified,
            "avg_adjustment": round(avg_adjustment, 2),
            "confidence": appraisal_result.confidence,
        }

        # 7. Store analysis run for reproducibility
        run_input = {
            "property_id": property_id,
            "subject_data": subject_data,
            "max_comps": max_comps,
            "comp_addresses": [c.address for c in enriched_comps],
        }
        run = AnalysisRun(
            property_id=property_id,
            analysis_type="comp_appraisal",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(run_input),
            output_json={
                "appraisal": appraisal_result.model_dump(),
                "data_quality": data_quality,
                "conflict_count": len(conflicts),
            },
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        # 8. Build market context from active/pending listings
        market_context = {
            "active_count": len(active_candidates),
            "pending_count": len(pending_candidates),
            "sold_count": len(sold_candidates),
        }
        if active_candidates:
            active_prices = [c.price for c in active_candidates if c.price]
            if active_prices:
                market_context["active_price_range"] = {
                    "low": min(active_prices),
                    "high": max(active_prices),
                    "median": sorted(active_prices)[len(active_prices) // 2],
                }
                market_context["asking_vs_active"] = (
                    "below" if list_price < min(active_prices)
                    else "above" if list_price > max(active_prices)
                    else "within"
                )
        if pending_candidates:
            pending_prices = [c.price for c in pending_candidates if c.price]
            if pending_prices:
                market_context["pending_price_range"] = {
                    "low": min(pending_prices),
                    "high": max(pending_prices),
                }

        return {
            "sold_comps": [c.model_dump() for c in enriched_comps],
            "active_listings": [c.model_dump() for c in active_candidates],
            "pending_listings": [c.model_dump() for c in pending_candidates],
            "appraisal": appraisal_result.model_dump(),
            "data_quality": data_quality,
            "conflicts": conflicts,
            "market_context": market_context,
        }

    # ------------------------------------------------------------------
    # County data parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_county_residential(county_data: dict) -> dict:
        """Extract structured dwelling details from county scraper output.

        The Loudoun scraper returns raw tab data with _key_values dicts.
        This method extracts the specific fields needed for comp analysis
        from the Residential tab.
        """
        res = county_data.get("Residential", {})
        kv = res.get("_key_values", {})

        return {
            "sqft_above_grade": kv.get("Net SFLA (above grade)"),
            "year_built": kv.get("Year Built"),
            "full_baths": kv.get("Full Baths"),
            "half_baths": kv.get("Half Baths"),
            "stories": kv.get("Story Height"),
            "style": kv.get("Style"),
            "condition": kv.get("Condition"),
            "grade": kv.get("Grade"),
            "roof_material": kv.get("Roof Material"),
            "exterior_wall": kv.get("Exterior Wall Material"),
            "basement_total_sqft": kv.get("Total Basement Area"),
            "basement_finished_sqft": kv.get("Finished Basement Sq Ft"),
            "foundation": kv.get("Foundation Type"),
        }

    @staticmethod
    def _parse_county_values(county_data: dict) -> dict:
        """Extract assessment values from county Values tab."""
        values = county_data.get("Values", {})
        kv = values.get("_key_values", {})

        return {
            "assessed_land": kv.get("Fair Market Land"),
            "assessed_building": kv.get("Fair Market Building"),
            "assessed_total": kv.get("Fair Market Total"),
        }

    @staticmethod
    def _parse_county_sale(county_data: dict) -> dict:
        """Extract most recent sale from county Sales tab."""
        sales = county_data.get("Sales / Transfers", {})
        kv = sales.get("_key_values", {})

        return {
            "sale_date": kv.get("Sale Date"),
            "sale_price": kv.get("Sale Price"),
            "seller": kv.get("Seller"),
            "buyer": kv.get("Buyer"),
        }

    # ------------------------------------------------------------------
    # Subject property loader
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_subject_data(
        db: AsyncSession, property_id: str
    ) -> dict:
        """Load subject property data from the DB.

        Pulls from ListingEpisode (most recent active/pending) and
        ListingPageSnapshot (most recent parsed_fields) to build a dict
        with list_price, sqft, beds, baths, year_built.
        """
        # Try ListingEpisode first (most reliable structured data)
        episode_result = await db.execute(
            select(ListingEpisode)
            .where(ListingEpisode.property_id == property_id)
            .order_by(ListingEpisode.created_at.desc())
            .limit(1)
        )
        episode = episode_result.scalar_one_or_none()

        subject: dict[str, Any] = {}
        if episode:
            subject["list_price"] = episode.original_list_price or 0
            subject["sqft"] = int(episode.sqft) if episode.sqft else 0
            subject["beds"] = episode.bedrooms or 0
            subject["baths"] = episode.bathrooms or 0.0
            subject["year_built"] = episode.year_built

        # Fill gaps from listing page snapshot parsed_fields
        snap_result = await db.execute(
            select(ListingPageSnapshot)
            .where(
                ListingPageSnapshot.property_id == property_id,
                ListingPageSnapshot.scrape_success.is_(True),
            )
            .order_by(ListingPageSnapshot.scraped_at.desc())
            .limit(1)
        )
        snap = snap_result.scalar_one_or_none()
        if snap and snap.parsed_fields:
            pf = snap.parsed_fields
            if not subject.get("list_price"):
                subject["list_price"] = pf.get("price") or pf.get("list_price") or 0
            if not subject.get("sqft"):
                subject["sqft"] = pf.get("sqft") or pf.get("livingArea") or 0
            if not subject.get("beds"):
                subject["beds"] = pf.get("bedrooms") or pf.get("beds") or 0
            if not subject.get("baths"):
                baths = pf.get("baths") or pf.get("bathrooms")
                if baths:
                    subject["baths"] = float(baths)
                else:
                    full = pf.get("full_bathrooms", 0) or 0
                    half = pf.get("half_bathrooms", 0) or 0
                    subject["baths"] = full + half * 0.5
            if not subject.get("year_built"):
                subject["year_built"] = pf.get("year_built")

        return subject

    # ------------------------------------------------------------------
    # Stored results loader
    # ------------------------------------------------------------------

    @staticmethod
    async def get_stored_results(
        db: AsyncSession, property_id: str
    ) -> dict | None:
        """Load the most recent comp analysis run from the database.

        Returns the stored output_json from the AnalysisRun, or None
        if no comp analysis has been run for this property.
        """
        result = await db.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.property_id == property_id,
                AnalysisRun.analysis_type == "comp_appraisal",
            )
            .order_by(AnalysisRun.computed_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return None

        # The output_json has {appraisal, data_quality, conflict_count}
        # Also load the enriched comp evidence items
        evidence_result = await db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.property_id == property_id,
                EvidenceItem.field_name.like("comp:%"),
                EvidenceItem.confidence == "confirmed",
            )
            .order_by(EvidenceItem.observed_at.desc())
        )
        comp_evidence = evidence_result.scalars().all()

        comps = []
        for ev in comp_evidence:
            try:
                comp_data = json.loads(ev.field_value)
                comps.append(comp_data)
            except (json.JSONDecodeError, TypeError):
                continue

        output = run.output_json or {}
        output["comps"] = comps
        output["computed_at"] = run.computed_at.isoformat() if run.computed_at else None
        return output


def _parse_date(date_str: str) -> date | None:
    """Try multiple date formats to parse a date string."""
    if not date_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    # Try to extract date-like pattern
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", date_str)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None
