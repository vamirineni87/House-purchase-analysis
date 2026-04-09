"""Automated comparable sales sourcing and enrichment.

Two-stage comp system:

QUICK COMP — runs automatically on every new listing, instant, no county scraping.
    Finds candidates from already-scraped listing data, filters by similarity,
    produces a rough value band from portal prices.

DEEP COMP — runs only when user clicks "Run Deep Comp" for shortlisted homes.
    County-scrapes top candidates, runs full appraisal adjustment engine,
    produces county-verified value range with confidence score.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import statistics
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
from pipa.schemas.comp import CompCandidate, DeepCompResult, EnrichedComp, QuickCompResult

logger = logging.getLogger(__name__)

_CODE_VERSION = "0.2.0"


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
    """2-stage comp system: quick comp (auto) + deep comp (on-demand).

    QUICK COMP: fast (<2s), uses only already-scraped listing data.
    DEEP COMP: slow (~2 min), county-scrapes top candidates for verification.
    """

    # ==================================================================
    # QUICK COMP — runs on every listing, instant, no county scraping
    # ==================================================================

    @staticmethod
    async def quick_comp(
        db: AsyncSession,
        property_id: str,
        subject_data: dict | None = None,
    ) -> dict:
        """Fast comp analysis — no county scraping.

        1. Find 10-20 candidates from listing nearby + county neighborhood
        2. Filter to 5-8 likely comps by similarity to subject
        3. Produce rough value band from portal prices
        4. Quick confidence score
        5. Asking vs comps assessment

        Returns QuickCompResult dict.
        """
        # Load subject data if not provided
        if subject_data is None:
            subject_data = await CompService._load_subject_data(db, property_id)

        list_price = _safe_float(subject_data.get("list_price")) or 0

        # Find all candidates from stored data (no external calls)
        all_candidates = await CompService.find_comp_candidates(db, property_id)

        # Separate by status
        sold = [c for c in all_candidates if c.status == "sold"]
        active = [c for c in all_candidates if c.status == "active"]
        pending = [c for c in all_candidates if c.status in ("pending", "contingent")]

        # Filter sold comps to likely matches based on subject
        filtered = CompService.filter_comps(sold, subject_data)

        # Cap at 8 best matches
        filtered = filtered[:8]

        # Compute rough value band from filtered comps
        rough_value_band = CompService.compute_quick_value_band(filtered, subject_data)

        # Assess confidence
        avg_similarity = 0.0
        if filtered:
            scores = [c.similarity_score or 0.0 for c in filtered]
            avg_similarity = statistics.mean(scores)

        # Date spread: how many months between oldest and newest comp
        date_spread = CompService._compute_date_spread(filtered)
        quick_confidence = CompService.assess_confidence(
            len(filtered), avg_similarity, date_spread
        )

        # Warnings
        warnings: list[str] = []
        if len(filtered) < 3:
            warnings.append("Few comparable sales found in the area")
        if len(filtered) == 0:
            warnings.append("No comparable sales found — value band is unreliable")
        if date_spread > 5:
            warnings.append("Comp sales span more than 5 months — market may have shifted")
        old_only = all(
            (c.date or "") < (date.today().replace(day=1).isoformat())
            for c in filtered if c.date
        )
        if old_only and filtered:
            warnings.append("All comps are from prior months — no very recent sales")
        if len(active) == 0 and len(pending) == 0:
            warnings.append("No active or pending listings found for market context")

        # Assessment context: try to load county assessment if available
        assessment_context = await CompService._load_assessment_context(db, property_id)

        # Asking vs comps
        asking_vs_comps = "at"
        if rough_value_band and rough_value_band.get("mid"):
            mid = rough_value_band["mid"]
            if list_price > 0:
                pct = (list_price - mid) / mid if mid else 0
                if pct < -0.05:
                    asking_vs_comps = "below"
                elif pct > 0.05:
                    asking_vs_comps = "above"
                else:
                    asking_vs_comps = "at"

        result = {
            "candidates": [c.model_dump() for c in all_candidates],
            "filtered_comps": [c.model_dump() for c in filtered],
            "sold_count": len(sold),
            "active_count": len(active),
            "pending_count": len(pending),
            "rough_value_band": rough_value_band,
            "quick_confidence": quick_confidence,
            "warnings": warnings,
            "assessment_context": assessment_context,
            "asking_vs_comps": asking_vs_comps,
        }

        # Store as analysis run for retrieval
        run_input = {
            "property_id": property_id,
            "subject_data": subject_data,
            "type": "quick_comp",
        }
        run = AnalysisRun(
            property_id=property_id,
            analysis_type="quick_comp",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(run_input),
            output_json=result,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        return result

    # ==================================================================
    # DEEP COMP — shortlisted homes only, county-verified
    # ==================================================================

    @staticmethod
    async def deep_comp(
        db: AsyncSession,
        property_id: str,
        subject_data: dict | None = None,
        max_comps: int = 6,
    ) -> dict:
        """County-verified comp analysis — slow (~2 min).

        1. Find candidates (reuse quick_comp candidates if available)
        2. Rank top 4-8 by similarity to subject
        3. County-enrich ONLY those top candidates
        4. Run full appraisal adjustment engine on county-verified data
        5. Output comp pack with value range + confidence

        Returns DeepCompResult dict.
        """
        # Load subject data
        if subject_data is None:
            subject_data = await CompService._load_subject_data(db, property_id)

        list_price = subject_data.get("list_price", 0)
        sqft = subject_data.get("sqft", 0)
        beds = subject_data.get("beds", 0)
        baths = subject_data.get("baths", 0.0)
        year_built = subject_data.get("year_built")

        # Find all candidates and separate by status
        all_candidates = await CompService.find_comp_candidates(db, property_id)
        sold_candidates = [c for c in all_candidates if c.status == "sold"]
        active_candidates = [c for c in all_candidates if c.status == "active"]
        pending_candidates = [c for c in all_candidates if c.status in ("pending", "contingent")]

        # Filter and rank sold candidates by similarity
        ranked_sold = CompService.filter_comps(sold_candidates, subject_data)

        logger.info(
            "Deep comp candidates: %d sold (ranked), %d active, %d pending",
            len(ranked_sold), len(active_candidates), len(pending_candidates),
        )

        # County-enrich only the top candidates
        top_candidates = ranked_sold[:max_comps]
        enriched_comps = await CompService._enrich_candidates(
            db, property_id, top_candidates
        )

        # Convert EnrichedComp -> ComparableSale for appraisal engine
        comparable_sales: list[ComparableSale] = []
        for comp in enriched_comps:
            comp_sqft = comp.sqft_above_grade or comp.total_livable_sqft or 0
            comp_baths = (comp.full_baths or 0) + (comp.half_baths or 0) * 0.5
            sale_date = _parse_date(comp.sale_date)
            if sale_date is None:
                sale_date = date.today()

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

        # Run appraisal analysis
        appraisal_result = run_appraisal_analysis(
            list_price=list_price,
            sqft=sqft,
            beds=beds,
            baths=baths,
            year_built=year_built,
            comps=comparable_sales,
        )

        # Build adjustments summary (per-comp explanation)
        adjustments_summary: dict[str, Any] = {}
        for comp_result in (appraisal_result.comparables or []):
            net_adj = sum(comp_result.adjustments.values()) if comp_result.adjustments else 0
            net_pct = (net_adj / comp_result.sale_price * 100) if comp_result.sale_price else 0
            adjustments_summary[comp_result.address] = {
                "adjustments": comp_result.adjustments,
                "adjusted_price": comp_result.adjusted_price,
                "net_adjustment_pct": round(net_pct, 1),
            }

        # Value range from adjusted comps
        value_range: dict[str, Any] = {}
        if appraisal_result.comparables:
            adj_prices = [
                c.adjusted_price for c in appraisal_result.comparables
                if c.adjusted_price
            ]
            if adj_prices:
                value_range = {
                    "low": min(adj_prices),
                    "mid": round(statistics.median(adj_prices), 0),
                    "high": max(adj_prices),
                }

        # Detect conflicts
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
                        f"(>10% difference). County value used for adjustments."
                    ),
                })

        # Data quality summary
        county_verified = sum(1 for c in enriched_comps if c.county_sqft is not None)
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

        # Unresolved unknowns
        unresolved: list[str] = []
        for comp in enriched_comps:
            if comp.sqft_above_grade is None:
                unresolved.append(f"{comp.address}: county sqft not available")
            if comp.year_built is None:
                unresolved.append(f"{comp.address}: year built unknown")
            if comp.condition is None:
                unresolved.append(f"{comp.address}: condition not rated by county")

        # AI comp interpretation — ask Claude to rank, flag outliers, value opinion
        ai_interpretation: dict = {}
        try:
            from pipa.services.ai_extraction import interpret_comps

            ai_subject = {
                **subject_data,
                "address": (await CompService._load_subject_address(db, property_id)),
            }

            # Load school data for context (school zone differences affect value)
            school_info = None
            try:
                school_result = await db.execute(
                    select(SourceRecord).where(
                        SourceRecord.property_id == property_id,
                        SourceRecord.source_name == "lcps_official",
                    ).order_by(SourceRecord.fetched_at.desc()).limit(1)
                )
                school_record = school_result.scalar_one_or_none()
                if school_record and school_record.raw_payload:
                    school_info = school_record.raw_payload
            except Exception:
                pass

            # Load condition data
            condition_info = None
            try:
                cond_result = await db.execute(
                    select(AnalysisRun).where(
                        AnalysisRun.property_id == property_id,
                        AnalysisRun.analysis_type == "condition",
                    ).order_by(AnalysisRun.computed_at.desc()).limit(1)
                )
                cond_run = cond_result.scalar_one_or_none()
                if cond_run and cond_run.output_json:
                    condition_info = cond_run.output_json
            except Exception:
                pass

            # Load flood data
            flood_info = None
            try:
                flood_result = await db.execute(
                    select(SourceRecord).where(
                        SourceRecord.property_id == property_id,
                        SourceRecord.source_name == "fema_flood_zone",
                    ).order_by(SourceRecord.fetched_at.desc()).limit(1)
                )
                flood_record = flood_result.scalar_one_or_none()
                if flood_record and flood_record.raw_payload:
                    flood_info = flood_record.raw_payload
            except Exception:
                pass

            # Load financial data
            financial_info = None
            try:
                fin_result = await db.execute(
                    select(AnalysisRun).where(
                        AnalysisRun.property_id == property_id,
                        AnalysisRun.analysis_type == "financial",
                    ).order_by(AnalysisRun.computed_at.desc()).limit(1)
                )
                fin_run = fin_result.scalar_one_or_none()
                if fin_run and fin_run.output_json:
                    financial_info = fin_run.output_json
            except Exception:
                pass

            # Load ZIP-level market data (Redfin)
            market_indicators = None
            try:
                addr_result = await db.execute(
                    select(AddressHistory).where(
                        AddressHistory.property_id == property_id
                    ).order_by(AddressHistory.created_at.desc()).limit(1)
                )
                addr_rec = addr_result.scalar_one_or_none()
                if addr_rec and addr_rec.zip_code:
                    from pipa.clients.redfin_data import RedfinDataClient
                    redfin = RedfinDataClient()
                    zip_metrics = await redfin.get_zip_metrics(addr_rec.zip_code[:5], months=6)
                    if zip_metrics:
                        market_indicators = redfin.compute_market_indicators(zip_metrics)
                        logger.debug("[enrich] Market indicators: %s market, %.1f months supply",
                                     market_indicators.get("market_type", "?"),
                                     market_indicators.get("months_of_supply") or 0)
            except Exception:
                logger.debug("Could not load Redfin market data for AI comp")

            ai_market_ctx = {
                "active_count": len(active_candidates),
                "pending_count": len(pending_candidates),
                "sold_count": len(sold_candidates),
            }
            if school_info:
                ai_market_ctx["subject_schools"] = school_info
            if market_indicators:
                ai_market_ctx["market_indicators"] = market_indicators

            # Load mortgage rate history (last 6 months = ~26 weekly observations)
            rate_history = None
            try:
                from pipa.core.config import load_config
                cfg = load_config()
                fred_key = cfg.get("fred_api_key") or cfg.get("FRED_API_KEY")
                if fred_key:
                    from pipa.clients.fred import FREDClient
                    fred = FREDClient(api_key=fred_key)
                    rate_history = await fred.get_rate_history(term_years=30, limit=26)
                    logger.debug("[enrich] Loaded %d rate observations", len(rate_history or []))
            except Exception:
                logger.debug("Could not load FRED rate history for AI comp")

            ai_interpretation = await interpret_comps(
                subject=ai_subject,
                comps=[c.model_dump() for c in enriched_comps],
                market_context=ai_market_ctx,
                condition_data=condition_info,
                flood_data=flood_info,
                financial_data=financial_info,
                rate_history=rate_history,
            )
            logger.info("AI comp interpretation: confidence=%s", ai_interpretation.get("confidence"))
        except Exception:
            logger.exception("AI comp interpretation failed — continuing with math-only results")

        # Market context
        market_context: dict[str, Any] = {
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

        result = {
            "sold_comps": [c.model_dump() for c in enriched_comps],
            "active_listings": [c.model_dump() for c in active_candidates],
            "pending_listings": [c.model_dump() for c in pending_candidates],
            "appraisal": appraisal_result.model_dump(),
            "adjustments_summary": adjustments_summary,
            "value_range": value_range,
            "confidence": appraisal_result.confidence or "low",
            "data_quality": data_quality,
            "conflicts": conflicts,
            "market_context": market_context,
            "unresolved_unknowns": unresolved,
            "ai_interpretation": ai_interpretation,
        }

        # Store analysis run
        run_input = {
            "property_id": property_id,
            "subject_data": subject_data,
            "max_comps": max_comps,
            "comp_addresses": [c.address for c in enriched_comps],
            "type": "deep_comp",
        }
        # Ensure result is JSON-serializable (date objects → strings)
        json_safe_result = json.loads(json.dumps(result, default=str))
        run = AnalysisRun(
            property_id=property_id,
            analysis_type="deep_comp",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(run_input),
            output_json=json_safe_result,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        return result

    # ==================================================================
    # SHARED: Find comp candidates (used by both quick and deep)
    # ==================================================================

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
                        "year_built": _safe_int(entry.get("year_built")),
                        "property_type": entry.get("property_type") or entry.get("homeType"),
                    })

        # --- Source 2: County neighborhood sales (Loudoun parcel viewer) ---
        # Schema produced by LoudounParcelScraper._parse_neighborhood_sales:
        #   parcel_id, address, style, model, builder, year_built,
        #   sale_date (ISO), sale_price (float), subdivision, sale_validity
        # Note: county tab does not expose sqft / beds / baths.
        county_records = await db.execute(
            select(SourceRecord).where(
                SourceRecord.property_id == property_id,
                SourceRecord.source_name.in_([
                    "loudoun_county", "loudoun_parcel",
                ]),
            ).order_by(SourceRecord.fetched_at.desc()).limit(1)
        )
        for record in county_records.scalars().all():
            payload = record.raw_payload or {}
            ns = payload.get("Neighborhood Sales", {})
            sales_list = ns.get("sales", [])
            for sale in sales_list:
                # Filter to true market sales — skip family transfers,
                # foreclosures, etc., which would skew the comp set.
                validity = (sale.get("sale_validity") or "").strip()
                if validity and not validity.startswith("1 -"):
                    continue

                addr = sale.get("address") or sale.get("parcel_id") or ""
                if not addr:
                    continue
                normed = _normalize_address(addr)
                if normed in seen_addresses:
                    continue
                seen_addresses.add(normed)
                candidates.append({
                    "address": addr.strip(),
                    "price": _safe_float(sale.get("sale_price")),
                    "date": sale.get("sale_date") or "",
                    "status": "sold",
                    "source": "loudoun_neighborhood_sales",
                    # sqft/beds/baths not available from this tab
                    "year_built": _safe_int(sale.get("year_built")),
                    # property_type left None — filter_comps skips when either
                    # side is unknown. The county "style" (COLONIAL) is not
                    # comparable to Zillow's "single_family" property_type.
                    "parcel_id": sale.get("parcel_id"),
                    "style": sale.get("style"),
                    "model": sale.get("model"),
                    "builder": sale.get("builder"),
                    "subdivision": sale.get("subdivision"),
                    "sale_validity": validity or None,
                })

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

    # ==================================================================
    # SHARED: Filter comps by similarity to subject
    # ==================================================================

    @staticmethod
    def filter_comps(
        candidates: list[CompCandidate],
        subject_data: dict,
    ) -> list[CompCandidate]:
        """Filter candidates to likely comps based on subject property.

        Filters (appraisal-grade tolerances):
        - same property type (if known)
        - sqft within +/-15% of subject
        - year_built within +/-10 years
        - beds within +/-1
        - baths within +/-1
        - sold within last 6 months (already done in find_comp_candidates)

        Returns sorted by similarity score (best match first), with
        similarity_score set on each candidate.
        """
        subject_sqft = _safe_int(subject_data.get("sqft")) or 0
        subject_year = _safe_int(subject_data.get("year_built"))
        subject_beds = _safe_int(subject_data.get("beds")) or 0
        subject_baths = _safe_float(subject_data.get("baths")) or 0.0
        subject_type = (subject_data.get("property_type") or "").lower()

        scored: list[CompCandidate] = []

        for c in candidates:
            # --- Hard filters ---

            # Property type filter (skip if either side unknown)
            if subject_type and c.property_type:
                if subject_type != c.property_type.lower():
                    continue

            # Sqft filter: within +/-15% (skip if unknown)
            if subject_sqft and c.sqft:
                pct = abs(c.sqft - subject_sqft) / subject_sqft
                if pct > 0.15:
                    continue

            # Year built filter: within +/-10 years (skip if unknown)
            if subject_year and c.year_built:
                if abs(c.year_built - subject_year) > 10:
                    continue

            # Beds filter: within +/-1 (skip if unknown)
            if subject_beds and c.beds:
                if abs(c.beds - subject_beds) > 1:
                    continue

            # Baths filter: within +/-1 (skip if unknown)
            if subject_baths and c.baths:
                if abs(c.baths - subject_baths) > 1.0:
                    continue

            # --- Similarity scoring (0-100) ---
            score = CompService._compute_similarity(
                c, subject_sqft, subject_year, subject_beds, subject_baths
            )
            c.similarity_score = round(score, 1)
            scored.append(c)

        # Sort by similarity score descending (best match first)
        scored.sort(key=lambda x: x.similarity_score or 0, reverse=True)
        return scored

    @staticmethod
    def _compute_similarity(
        comp: CompCandidate,
        subject_sqft: int,
        subject_year: int | None,
        subject_beds: int,
        subject_baths: float,
    ) -> float:
        """Compute a 0-100 similarity score for a comp vs subject.

        Weights:
        - sqft closeness:  35 pts
        - year built:      20 pts
        - beds match:      15 pts
        - baths match:     15 pts
        - recency of sale: 15 pts
        """
        score = 0.0

        # Sqft closeness (35 pts): 0% diff = 35, 15% diff = 0
        if subject_sqft and comp.sqft:
            pct_diff = abs(comp.sqft - subject_sqft) / subject_sqft
            score += max(0, 35 * (1 - pct_diff / 0.15))
        elif not comp.sqft:
            # Unknown sqft — give partial credit
            score += 10

        # Year built (20 pts): 0 year diff = 20, 10 year diff = 0
        if subject_year and comp.year_built:
            year_diff = abs(comp.year_built - subject_year)
            score += max(0, 20 * (1 - year_diff / 10))
        elif not comp.year_built:
            score += 5

        # Beds match (15 pts): exact = 15, +-1 = 8
        if subject_beds and comp.beds:
            bed_diff = abs(comp.beds - subject_beds)
            if bed_diff == 0:
                score += 15
            elif bed_diff == 1:
                score += 8
        elif not comp.beds:
            score += 5

        # Baths match (15 pts): exact = 15, +-0.5 = 10, +-1 = 5
        if subject_baths and comp.baths:
            bath_diff = abs(comp.baths - subject_baths)
            if bath_diff <= 0.1:
                score += 15
            elif bath_diff <= 0.5:
                score += 10
            elif bath_diff <= 1.0:
                score += 5
        elif not comp.baths:
            score += 5

        # Recency (15 pts): today = 15, 6 months ago = 0
        if comp.date:
            sale_date = _parse_date(comp.date)
            if sale_date:
                days_ago = (date.today() - sale_date).days
                score += max(0, 15 * (1 - days_ago / 180))
        else:
            score += 3  # unknown date, small credit

        return score

    # ==================================================================
    # SHARED: Quick value band computation
    # ==================================================================

    @staticmethod
    def compute_quick_value_band(
        comps: list[CompCandidate],
        subject_data: dict,
    ) -> dict:
        """Compute rough value band from portal prices.

        Uses price per sqft from comps applied to subject sqft.
        Returns {low, mid, high}. Empty dict if insufficient data.
        """
        subject_sqft = _safe_int(subject_data.get("sqft")) or 0

        if not comps or not subject_sqft:
            # Fall back to raw prices if no sqft data
            prices = [c.price for c in comps if c.price]
            if not prices:
                return {}
            return {
                "low": min(prices),
                "mid": round(statistics.median(prices), 0),
                "high": max(prices),
            }

        # Compute $/sqft for each comp that has both price and sqft
        ppsf_values: list[float] = []
        for c in comps:
            if c.price and c.sqft and c.sqft > 0:
                ppsf_values.append(c.price / c.sqft)

        if ppsf_values:
            # Apply $/sqft to subject sqft
            low_ppsf = min(ppsf_values)
            high_ppsf = max(ppsf_values)
            mid_ppsf = statistics.median(ppsf_values)

            return {
                "low": round(low_ppsf * subject_sqft, 0),
                "mid": round(mid_ppsf * subject_sqft, 0),
                "high": round(high_ppsf * subject_sqft, 0),
            }

        # Fallback: use raw prices
        prices = [c.price for c in comps if c.price]
        if not prices:
            return {}
        return {
            "low": min(prices),
            "mid": round(statistics.median(prices), 0),
            "high": max(prices),
        }

    # ==================================================================
    # SHARED: Confidence assessment
    # ==================================================================

    @staticmethod
    def assess_confidence(
        comp_count: int,
        avg_similarity: float,
        date_spread: float,
    ) -> str:
        """Rate comp confidence: strong/moderate/weak/insufficient.

        - strong: 5+ comps within 6 months and avg similarity >= 50
        - moderate: 3-4 comps
        - weak: 1-2 comps
        - insufficient: 0 comps
        """
        if comp_count == 0:
            return "insufficient"
        if comp_count >= 5 and avg_similarity >= 50:
            return "strong"
        if comp_count >= 3:
            return "moderate"
        return "weak"

    # ==================================================================
    # DEEP COMP INTERNALS: County enrichment
    # ==================================================================

    @staticmethod
    async def enrich_comp_from_county(
        db: AsyncSession,
        comp_address: str,
        subject_property_id: str | None = None,
        scraper: LoudounParcelScraper | None = None,
        force_refresh: bool = False,
        ttl_hours: int = 168,  # 7 days — sold comp data doesn't change often
    ) -> dict:
        """Get county-verified details for a comp property.

        Checks SourceRecord cache first (by parcel ID or address match).
        On fresh scrape, stores raw payload as SourceRecord for reuse.

        Returns dict with county-verified fields.
        """
        normed = _normalize_address(comp_address)
        from datetime import timedelta

        logger.debug("[enrich] comp_address=%s normed=%s force_refresh=%s ttl=%dh subject_pid=%s",
                     comp_address, normed, force_refresh, ttl_hours, subject_property_id)

        # --- Check cache: do we already have county data for this comp? ---
        if not force_refresh:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

            # Search by comp_lookup_key (parcel ID or normalized address)
            cached_records = await db.execute(
                select(SourceRecord).where(
                    SourceRecord.source_name == "county_comp_enrichment",
                ).order_by(SourceRecord.fetched_at.desc())
            )
            all_cached = cached_records.scalars().all()
            logger.debug("[enrich] county_comp_enrichment records found: %d", len(all_cached))
            for record in all_cached:
                payload = record.raw_payload or {}
                lookup_key = payload.get("_comp_lookup_key", "")
                logger.debug("[enrich]   record id=%s lookup_key=%r fetched=%s",
                             record.id[:12] if record.id else "?", lookup_key,
                             record.fetched_at.isoformat() if record.fetched_at else "None")

                if lookup_key and (lookup_key == normed or lookup_key == comp_address):
                    if record.fetched_at and record.fetched_at >= cutoff:
                        logger.info("Cache hit for comp %s (fetched %s)", comp_address, record.fetched_at.isoformat())
                        return CompService._parse_all_county_tabs(payload, comp_address)
                    else:
                        logger.info("Stale cache for comp %s (fetched %s, ttl %dh)",
                                    comp_address, record.fetched_at.isoformat(), ttl_hours)

            # Also check subject property's county records (might already be scraped)
            cached_county = await db.execute(
                select(SourceRecord).where(
                    SourceRecord.source_name.in_(["loudoun_county", "loudoun_parcel"]),
                ).order_by(SourceRecord.fetched_at.desc()).limit(20)
            )
            for record in cached_county.scalars().all():
                payload = record.raw_payload or {}
                summary_addr = _normalize_address(
                    payload.get("_summary", {}).get("address", "")
                    or payload.get("Profile", {}).get("_key_values", {}).get("Primary Address", "")
                )
                if summary_addr and (normed in summary_addr or summary_addr in normed):
                    if record.fetched_at and record.fetched_at >= cutoff:
                        logger.info("Found comp %s in existing county record (fetched %s)",
                                    comp_address, record.fetched_at.isoformat())
                        return CompService._parse_all_county_tabs(payload, comp_address)

            logger.debug("[enrich] No cache match for %s — will scrape", comp_address)

        # --- No cache or stale: scrape the county website ---
        owns_scraper = False
        if scraper is None:
            scraper = LoudounParcelScraper(headless=True)
            owns_scraper = True

        try:
            logger.info("Scraping county for comp %s", comp_address)
            county_data = await scraper.scrape_by_address_string(comp_address)

            if county_data.get("_error"):
                logger.warning(
                    "County scrape failed for %s: %s",
                    comp_address,
                    county_data["_error"],
                )
                return {"_error": county_data["_error"], "address": comp_address}

            # Store raw payload for reuse — keyed by comp address/parcel ID
            county_data["_comp_lookup_key"] = normed
            county_data["_comp_raw_address"] = comp_address
            logger.debug("[enrich] Storing with lookup_key=%r property_id=%s", normed, subject_property_id)
            now = datetime.now(timezone.utc)
            try:
                sr = SourceRecord(
                    property_id=subject_property_id,
                    source_name="county_comp_enrichment",
                    source_url=county_data.get("_detail_url"),
                    raw_payload=county_data,
                    fetched_at=now,
                )
                db.add(sr)
                await db.flush()
                logger.info("Stored county data for comp %s (id=%s)", comp_address, sr.id[:12] if sr.id else "?")
            except Exception as store_err:
                logger.error("Failed to store comp data for %s: %s", comp_address, store_err)

            # Parse all tabs and return enriched data
            return CompService._parse_all_county_tabs(county_data, comp_address)

        finally:
            if owns_scraper:
                await scraper.close()

    @staticmethod
    async def _enrich_candidates(
        db: AsyncSession,
        property_id: str,
        candidates: list[CompCandidate],
    ) -> list[EnrichedComp]:
        """County-enrich a list of candidates. Reused by deep_comp and build_verified_comps.

        Performance + correctness notes:
        - Both scrapers (Loudoun + Zillow) are created ONCE outside the loop
          and reused across all comps. Previously the Zillow scraper was
          created and torn down inside the loop, launching a new Chromium
          browser per comp (~3-5s wasted overhead × N comps).
        - We commit the DB after EACH comp's evidence is flushed. The old
          code held a single open transaction for the entire 25-comp scrape
          loop (~10+ minutes). SQLite was write-locked the entire time,
          which starved APScheduler ('database is locked') and any other
          concurrent API request that needed to write.
        """
        if not candidates:
            return []

        from pipa.clients.scrapers.zillow import ZillowScraper

        scraper = LoudounParcelScraper(headless=True)
        # Reused across the entire loop. headless=False so the Zillow CAPTCHA
        # bypass + cookie loading still works.
        zillow_scraper = ZillowScraper(headless=False)
        enriched_comps: list[EnrichedComp] = []
        now = datetime.now(timezone.utc)

        try:
            for candidate in candidates:
                enriched = await CompService.enrich_comp_from_county(
                    db, candidate.address,
                    subject_property_id=property_id,
                    scraper=scraper,
                )

                if enriched.get("_error"):
                    logger.warning(
                        "Skipping comp %s: county enrichment failed",
                        candidate.address,
                    )
                    continue

                # Try Zillow scrape for extra details (HOA, description, price history)
                zillow_data: dict = {}
                comp_street = enriched.get("address") or ""
                if comp_street and not comp_street.isdigit():
                    try:
                        zillow_data = await zillow_scraper.scrape_by_address(
                            comp_street, city="", state="VA"
                        )
                        if zillow_data.get("_error"):
                            logger.debug("Zillow scrape failed for comp %s: %s",
                                         comp_street, zillow_data.get("_error"))
                            zillow_data = {}
                        else:
                            logger.info("Zillow enrichment for comp %s: %d fields",
                                        comp_street, len(zillow_data))
                    except Exception:
                        logger.debug("Zillow enrichment failed for comp %s", comp_street, exc_info=True)

                # Detect sqft conflict
                listing_sqft = candidate.sqft or _safe_int(zillow_data.get("sqft") or zillow_data.get("livingArea"))
                county_sqft = _safe_int(enriched.get("sqft_above_grade"))
                sqft_conflict = False
                if listing_sqft and county_sqft:
                    pct_diff = abs(listing_sqft - county_sqft) / max(listing_sqft, 1)
                    sqft_conflict = pct_diff > 0.10

                # Resolve sale_price: prefer county, fall back to listing
                sale_price = _safe_float(enriched.get("sale_price"))
                if sale_price is None:
                    sale_price = candidate.price
                if sale_price is None:
                    logger.warning(
                        "Skipping comp %s: no sale price from county or listing",
                        candidate.address,
                    )
                    continue

                # Resolve sale_date: prefer county, fall back to listing
                sale_date = enriched.get("sale_date") or candidate.date or ""
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
                    total_livable_sqft=_safe_int(enriched.get("total_livable_sqft")),
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
                    hoa_monthly=_safe_float(zillow_data.get("hoa_monthly") or zillow_data.get("monthlyHoaFee")),
                    zillow_description=(zillow_data.get("description") or zillow_data.get("homeDescription") or "")[:2000] or None,
                    zillow_price_history=zillow_data.get("price_history") or zillow_data.get("priceHistory"),
                    zillow_days_on_market=_safe_int(zillow_data.get("days_on_zillow") or zillow_data.get("daysOnZillow")),
                    zillow_list_price=_safe_float(zillow_data.get("list_price") or zillow_data.get("price")),
                    zillow_url=zillow_data.get("_url"),
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

                # Commit after each comp so the SQLite write lock is
                # released between scrapes. Without this, the entire 25-
                # comp loop holds the lock for 10+ minutes and starves
                # APScheduler ('database is locked') and any other
                # concurrent API request that needs to write.
                await db.commit()

            return enriched_comps

        finally:
            try:
                await scraper.close()
            except Exception:
                logger.debug("Loudoun scraper close failed", exc_info=True)
            try:
                await zillow_scraper.close()
            except Exception:
                logger.debug("Zillow scraper close failed", exc_info=True)

    # ==================================================================
    # LEGACY: build_verified_comps and run_comp_analysis
    # Keep for backward compatibility — delegate to new methods internally
    # ==================================================================

    @staticmethod
    async def build_verified_comps(
        db: AsyncSession,
        property_id: str,
        max_comps: int = 6,
    ) -> list[EnrichedComp]:
        """Full pipeline: find candidates, enrich from county, return verified comps.

        Legacy method — now delegates to find_comp_candidates + _enrich_candidates.
        """
        candidates = await CompService.find_comp_candidates(db, property_id)
        if not candidates:
            logger.warning("No comp candidates found for property %s", property_id)
            return []

        # Filter to sold only for enrichment
        sold = [c for c in candidates if c.status == "sold"]

        logger.info(
            "Found %d comp candidates for property %s, enriching up to %d",
            len(sold),
            property_id,
            max_comps,
        )

        return await CompService._enrich_candidates(
            db, property_id, sold[:max_comps]
        )

    @staticmethod
    async def run_comp_analysis(
        db: AsyncSession,
        property_id: str,
        subject_data: dict | None = None,
        max_comps: int = 6,
    ) -> dict:
        """End-to-end: source comps, enrich, run appraisal analysis.

        Legacy method — internally runs deep_comp and reshapes to old format.
        """
        deep_result = await CompService.deep_comp(
            db, property_id, subject_data=subject_data, max_comps=max_comps
        )

        # Reshape to legacy format (without the new fields)
        return {
            "sold_comps": deep_result["sold_comps"],
            "active_listings": deep_result["active_listings"],
            "pending_listings": deep_result["pending_listings"],
            "appraisal": deep_result["appraisal"],
            "data_quality": deep_result["data_quality"],
            "conflicts": deep_result["conflicts"],
            "market_context": deep_result["market_context"],
        }

    # ==================================================================
    # Unified county data parser (used by both cached and fresh paths)
    # ==================================================================

    @staticmethod
    def _parse_all_county_tabs(county_data: dict, comp_address: str) -> dict:
        """Parse ALL county tabs into a single enriched dict.

        Used by both cached (from SourceRecord) and fresh (from scraper) paths.
        """
        residential = CompService._parse_county_residential(county_data)
        values = CompService._parse_county_values(county_data)
        sale = CompService._parse_county_sale(county_data)
        profile = CompService._parse_county_profile(county_data)
        land = CompService._parse_county_land(county_data)
        detached = CompService._parse_county_detached(county_data)

        summary = county_data.get("_summary", {})

        enriched: dict[str, Any] = {"address": comp_address}
        enriched.update(residential)
        enriched.update(values)
        enriched.update(sale)
        enriched["profile"] = profile
        enriched["land"] = land
        enriched["detached_structures"] = detached

        # Fill gaps from summary
        for key in [
            "year_built", "style", "condition", "grade",
            "full_baths", "half_baths", "lot_acres",
            "sqft_above_grade", "basement_total_sqft",
            "basement_finished_sqft", "foundation",
            "roof_material", "exterior_wall",
            "assessed_total", "parcel_id", "subdivision",
        ]:
            if enriched.get(key) is None and summary.get(key) is not None:
                enriched[key] = summary[key]

        # Pull parcel_id and subdivision from profile if not in summary
        if not enriched.get("parcel_id") and profile.get("parcel_id"):
            enriched["parcel_id"] = profile["parcel_id"]
        if not enriched.get("subdivision") and profile.get("subdivision"):
            enriched["subdivision"] = profile["subdivision"]

        # Builder from seller in sale record
        seller = enriched.get("seller", "")
        if seller and any(kw in seller.upper() for kw in ["NVR", "HOVNANIAN", "TOLL", "PULTE", "RYAN", "LENNAR", "DR HORTON"]):
            enriched["builder"] = seller

        # Compute total_livable_sqft = above_grade + finished basement
        above = _safe_int(enriched.get("sqft_above_grade"))
        fin_bsmt = _safe_int(enriched.get("basement_finished_sqft"))
        if above is not None:
            enriched["sqft_above_grade"] = above
            if fin_bsmt:
                enriched["total_livable_sqft"] = above + fin_bsmt
            else:
                enriched["total_livable_sqft"] = above

        # Convert lot_acres string to float
        lot = enriched.get("lot_acres")
        if lot is not None:
            enriched["lot_acres"] = _safe_float(lot)

        # Land sqft
        land_sqft = land.get("land_sqft")
        if land_sqft:
            enriched["lot_sqft"] = _safe_int(land_sqft)

        # Store raw county data for full audit trail
        enriched["_raw_county"] = county_data

        return enriched

    # ==================================================================
    # Individual tab parsers
    # ==================================================================

    @staticmethod
    def _parse_county_residential(county_data: dict) -> dict:
        """Extract ALL dwelling details from county Residential tab.

        Captures every field the county exposes — nothing is omitted.
        """
        res = county_data.get("Residential", {})
        kv = res.get("_key_values", {})
        rows = res.get("_rows", [])

        result = {
            # Core dwelling
            "sqft_above_grade": kv.get("Net SFLA (above grade)"),
            "year_built": kv.get("Year Built"),
            "full_baths": kv.get("Full Baths"),
            "half_baths": kv.get("Half Baths"),
            "stories": kv.get("Story Height"),
            "style": kv.get("Style"),
            "model": kv.get("Model"),
            "condition": kv.get("Condition"),
            "grade": kv.get("Grade"),
            "exterior_wall": kv.get("Exterior Wall Material"),
            "dwelling_pct_complete": kv.get("Dwelling % Complete"),
            "occupancy": kv.get("Occupancy"),
            # Roof
            "roof_type": kv.get("Roof Type"),
            "roof_material": kv.get("Roof Material"),
            # Heating / cooling
            "heating_ac": kv.get("Heating/AC"),
            # Interior features
            "fireplaces": kv.get("Total Fireplaces"),
            "cathedral_ceiling_sqft": kv.get("Cathedral Ceiling/Foyer"),
            "additional_fixtures": kv.get("5.Additional Fixtures"),
            "unfinished_area": kv.get("Unfinished Area"),
            # Basement
            "basement_total_sqft": kv.get("Total Basement Area"),
            "basement_entrance": kv.get("Basement Entrance"),
            "basement_finished_sqft": kv.get("Finished Basement Sq Ft"),
            "basement_bedrooms": kv.get("Bsmnt Dens/Bdrms"),
            "basement_garage_cars": kv.get("Bsmnt Garage # Cars"),
            # Foundation / attic
            "foundation": kv.get("Foundation Type"),
            "attic_type": kv.get("Attic Type"),
            "attic_sqft": kv.get("Total Attic Area"),
            # Address / location
            "property_address": kv.get("Property Address"),
            "city_state_zip": kv.get("City, State, Zip"),
            "card": kv.get("Card"),
        }

        # Compute derived fields
        bsmt_total = _safe_int(result.get("basement_total_sqft"))
        bsmt_finished = _safe_int(result.get("basement_finished_sqft"))
        if bsmt_total is not None and bsmt_finished is not None:
            result["basement_unfinished_sqft"] = bsmt_total - bsmt_finished

        above = _safe_int(result.get("sqft_above_grade"))
        if above is not None and bsmt_finished is not None:
            result["total_livable_sqft"] = above + bsmt_finished

        # Parse attached structures from rows
        # Format: [card, line, type1, type2?, sqft, yr_built?, pct_complete]
        structures = []
        for row in rows:
            if len(row) >= 3 and row[0].isdigit():
                # This is a structure line
                struct = {"raw": row}
                # Identify by keywords
                row_joined = " ".join(row).upper()
                if "GARAGE" in row_joined:
                    struct["type"] = "garage"
                elif "DECK" in row_joined:
                    struct["type"] = "deck"
                elif "PORCH" in row_joined or "PATIO" in row_joined or "COVERED" in row_joined:
                    struct["type"] = "porch"
                elif "AREA OVER GARAGE" in row_joined:
                    struct["type"] = "area_over_garage"
                elif "BASEMENT" in row_joined:
                    struct["type"] = "basement"
                elif "PRIMARY" in row_joined:
                    struct["type"] = "primary"
                elif "ADDN" in row_joined or "ADDITION" in row_joined:
                    struct["type"] = "addition"
                else:
                    struct["type"] = "other"
                # Try to extract sqft from the row
                for val in row:
                    sqft = _safe_int(val)
                    if sqft and 10 < sqft < 50000:
                        struct["sqft"] = sqft
                        break
                # Try to extract year
                for val in row:
                    yr = _safe_int(val)
                    if yr and 1900 < yr < 2100:
                        struct["year_built"] = yr
                        break
                structures.append(struct)

        result["attached_structures"] = structures

        # Extract specific structure sqft for easy access
        for s in structures:
            stype = s.get("type", "")
            sqft = s.get("sqft")
            if stype == "garage" and sqft:
                result["garage_sqft"] = sqft
            elif stype == "deck" and sqft:
                result["deck_sqft"] = result.get("deck_sqft", 0) + sqft
            elif stype == "porch" and sqft:
                result["porch_sqft"] = result.get("porch_sqft", 0) + sqft
            elif stype == "area_over_garage" and sqft:
                result["area_over_garage_sqft"] = sqft

        return result

    @staticmethod
    def _parse_county_values(county_data: dict) -> dict:
        """Extract ALL assessment values from county Values tab."""
        values = county_data.get("Values", {})
        kv = values.get("_key_values", {})
        rows = values.get("_rows", [])

        result = {
            # Current year
            "assessed_land": kv.get("Fair Market Land"),
            "assessed_building": kv.get("Fair Market Building"),
            "prorated_building": kv.get("Prorated Bldg"),
            "assessed_total": kv.get("Fair Market Total"),
            "land_use_value": kv.get("Land Use Value"),
            "taxable_value": kv.get("Total Taxable Value"),
            "deferred_land_use": kv.get("*Deferred Land Use Value"),
            "tax_exempt_code": kv.get("Tax Exempt Code"),
            "tax_exempt_land": kv.get("Tax Exempt Land"),
            "tax_exempt_building": kv.get("Tax Exempt Building"),
            "tax_exempt_total": kv.get("Tax Exempt Total"),
        }

        # Parse assessment history from rows
        # Look for year headers like "2025 Values", "2024 Values"
        history = []
        current_year = None
        for row in rows:
            row_joined = " ".join(row)
            # Check for year header
            year_match = re.search(r"(20[12]\d)\s*Values", row_joined)
            if year_match:
                current_year = int(year_match.group(1))
                continue
            # Check for Notice/Landbook rows with values
            if current_year and len(row) >= 4 and row[0] in ("Notice", "Landbook"):
                entry = {
                    "year": current_year,
                    "process_type": row[0],
                    "land": row[1] if len(row) > 1 else None,
                    "building": row[2] if len(row) > 2 else None,
                }
                # Find the total (usually the last dollar amount)
                for val in reversed(row):
                    if val.startswith("$"):
                        entry["total"] = val
                        break
                history.append(entry)

        result["assessment_history"] = history

        return result

    @staticmethod
    def _parse_county_sale(county_data: dict) -> dict:
        """Extract ALL sale/transfer data from county Sales tab."""
        sales = county_data.get("Sales / Transfers", {})
        kv = sales.get("_key_values", {})
        rows = sales.get("_rows", [])

        result = {
            # Most recent sale details
            "sale_date": kv.get("Sale Date"),
            "sale_price": kv.get("Sale Price"),
            "seller": kv.get("Seller"),
            "buyer": kv.get("Buyer"),
            "valuation_code": kv.get("Valuation Code"),
            "instrument_number": kv.get("Instrument Number"),
            "recordation_date": kv.get("Recordation Date"),
            "deed_book_page": kv.get("Deed Book and Page"),
            "multi_parcel": kv.get("Multi-Parcel Sale (# of Parcels)"),
        }

        # Parse sale history from rows
        sale_history = []
        for row in rows:
            if len(row) >= 3 and re.match(r"\d{2}/\d{2}/\d{4}", row[0]):
                sale_history.append({
                    "date": row[0],
                    "price": row[1],
                    "buyer": row[2] if len(row) > 2 else None,
                })
        result["sale_history"] = sale_history

        return result

    @staticmethod
    def _parse_county_profile(county_data: dict) -> dict:
        """Extract profile/parcel data from county Profile tab."""
        profile = county_data.get("Profile", {})
        kv = profile.get("_key_values", {})

        return {
            "parcel_id": kv.get("PARID") or next(
                (v for k, v in kv.items() if k.startswith("PARID")), None
            ),
            "owner": kv.get("Name"),
            "mailing_address": kv.get("Mailing Address"),
            "tax_map": kv.get("Tax Map #"),
            "state_use_class": kv.get("State Use Class"),
            "lot_acres": kv.get("Total Land Area (Acreage)"),
            "election_district": kv.get("Election District"),
            "billing_district": kv.get("Billing District"),
            "structure_occupancy": kv.get("Structure Occupancy"),
            "subdivision": kv.get("Subdivision"),
            "legal_description": kv.get("Legal Description"),
            "instrument_number": kv.get("Instrument Number"),
            "adu": kv.get("Affordable Dwelling Unit (Y/N)"),
            "solar_exemption": kv.get("Solar Exemption?"),
            "special_tax_district": kv.get("Special Ad Valorem Tax District"),
        }

    @staticmethod
    def _parse_county_land(county_data: dict) -> dict:
        """Extract land details from county Land tab."""
        land = county_data.get("Land", {})
        kv = land.get("_key_values", {})

        return {
            "land_sqft": kv.get("Square Feet"),
            "land_acres": kv.get("Acres"),
            "land_value": kv.get("Market Land Value"),
            "land_type": kv.get("Land Type"),
            "land_code": kv.get("Land Code"),
            "primary_zoning": kv.get("Primary Zoning"),
            "price_per_sqft_land": kv.get("$/Sq Ft"),
            "price_per_acre": kv.get("$/Acre"),
            "public_water": kv.get("Public Water Available"),
            "public_sewer": kv.get("Public Sewer Available"),
            "easements": kv.get("Easements"),
            "location_code": kv.get("Location Code"),
            "municipality": kv.get("Municipality"),
            "zoning_breakout": kv.get("Zoning Breakout (Code/Acres)"),
            "flood_plain_acres": kv.get("Major Flood Plain Acres"),
            "steep_slope_acres": kv.get("Greater than 25% Steep Slope Acres"),
        }

    @staticmethod
    def _parse_county_detached(county_data: dict) -> list[dict]:
        """Extract detached structures from county Detached Structures tab."""
        det = county_data.get("Detached Structures", {})
        rows = det.get("_rows", [])

        structures = []
        for row in rows:
            if len(row) >= 6 and row[0].isdigit():
                structures.append({
                    "card": row[0],
                    "line": row[1] if len(row) > 1 else None,
                    "type": row[2] if len(row) > 2 else None,
                    "size": row[3] if len(row) > 3 else None,
                    "year_built": row[4] if len(row) > 4 else None,
                    "quality": row[5] if len(row) > 5 else None,
                    "condition": row[6] if len(row) > 6 else None,
                    "value": row[7] if len(row) > 7 else None,
                })
        return structures

    # ==================================================================
    # Subject property loader
    # ==================================================================

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

    @staticmethod
    async def _load_subject_address(db: AsyncSession, property_id: str) -> str:
        """Load the subject property's address string."""
        result = await db.execute(
            select(AddressHistory)
            .where(AddressHistory.property_id == property_id)
            .order_by(AddressHistory.created_at.desc())
            .limit(1)
        )
        addr = result.scalar_one_or_none()
        if addr:
            return addr.normalized_address or addr.raw_address or "Unknown address"
        return "Unknown address"

    # ==================================================================
    # Assessment context loader (for quick comp)
    # ==================================================================

    @staticmethod
    async def _load_assessment_context(
        db: AsyncSession, property_id: str
    ) -> dict | None:
        """Load county assessment context if available (no scraping)."""
        result = await db.execute(
            select(SourceRecord).where(
                SourceRecord.property_id == property_id,
                SourceRecord.source_name.in_([
                    "loudoun_county", "loudoun_parcel",
                ]),
            ).order_by(SourceRecord.fetched_at.desc()).limit(1)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        payload = record.raw_payload or {}
        values = payload.get("Values", {})
        kv = values.get("_key_values", {})

        assessed_total = kv.get("Fair Market Total")
        if assessed_total is None:
            return None

        return {
            "assessed_total": _safe_float(assessed_total),
            "assessed_land": _safe_float(kv.get("Fair Market Land")),
            "assessed_building": _safe_float(kv.get("Fair Market Building")),
            "source": "loudoun_county",
            "fetched_at": record.fetched_at.isoformat() if record.fetched_at else None,
        }

    # ==================================================================
    # Date spread helper
    # ==================================================================

    @staticmethod
    def _compute_date_spread(comps: list[CompCandidate]) -> float:
        """Compute months between oldest and newest comp sale date."""
        dates: list[date] = []
        for c in comps:
            if c.date:
                d = _parse_date(c.date)
                if d:
                    dates.append(d)

        if len(dates) < 2:
            return 0.0

        oldest = min(dates)
        newest = max(dates)
        delta = newest - oldest
        return delta.days / 30.0

    # ==================================================================
    # Stored results loader
    # ==================================================================

    @staticmethod
    async def get_stored_results(
        db: AsyncSession, property_id: str
    ) -> dict | None:
        """Load the most recent comp analysis results from the database.

        Returns a dict with quick_comp and/or deep_comp results,
        or None if no analysis has been run.
        """
        output: dict[str, Any] = {}

        # Load most recent quick_comp
        quick_result = await db.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.property_id == property_id,
                AnalysisRun.analysis_type == "quick_comp",
            )
            .order_by(AnalysisRun.computed_at.desc())
            .limit(1)
        )
        quick_run = quick_result.scalar_one_or_none()
        if quick_run:
            output["quick_comp"] = quick_run.output_json or {}
            output["quick_comp"]["computed_at"] = (
                quick_run.computed_at.isoformat() if quick_run.computed_at else None
            )

        # Load most recent deep_comp
        deep_result = await db.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.property_id == property_id,
                AnalysisRun.analysis_type.in_(["deep_comp", "comp_appraisal"]),
            )
            .order_by(AnalysisRun.computed_at.desc())
            .limit(1)
        )
        deep_run = deep_result.scalar_one_or_none()
        if deep_run:
            deep_data = deep_run.output_json or {}

            # Also load enriched comp evidence items
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

            deep_data["comps"] = comps
            deep_data["computed_at"] = (
                deep_run.computed_at.isoformat() if deep_run.computed_at else None
            )
            output["deep_comp"] = deep_data

        if not output:
            return None

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
