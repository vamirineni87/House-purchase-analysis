"""Unified data refresh service.

Coordinates refreshing all data sources for a property: listings,
county records, school boundaries, hazard profiles, and more.
Checks data freshness against DataFreshnessPolicy TTLs and runs
cross-reference checks across sources to flag conflicts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.freshness import DataFreshnessPolicy
from pipa.models.property import AddressHistory, Property
from pipa.models.source import EvidenceItem, SourceRecord

logger = logging.getLogger(__name__)

# Source name -> entity_type mapping for freshness checks.
# Keys are the user-facing source slugs; values are the entity_type
# used in DataFreshnessPolicy and SourceRecord.source_name patterns.
SOURCE_MAP = {
    "zillow": "listing",
    "redfin": "listing",
    "county": "parcel",
    "schools": "schools",
    "hazard": "hazard",
    "census": "census",
    "walkscore": "walkscore",
}

# Default TTLs (hours) when no DataFreshnessPolicy row exists
DEFAULT_TTL: dict[str, int] = {
    "listing": 4,          # Listing data goes stale fast
    "parcel": 720,         # County parcel: 30 days
    "assessment": 720,     # County assessment: 30 days
    "permit": 168,         # Permits: 7 days
    "deed": 720,           # Deeds: 30 days
    "schools": 2160,       # School boundaries: 90 days
    "hazard": 8760,        # Hazard data: 1 year
    "census": 8760,        # Census data: 1 year
    "walkscore": 720,      # Walk score: 30 days
    "hoa": 720,            # HOA docs: 30 days
}

# Default stale behavior per entity type
DEFAULT_STALE_BEHAVIOR: dict[str, str] = {
    "listing": "refresh_before_use",
    "parcel": "warn_only",
    "assessment": "warn_only",
    "permit": "warn_only",
    "deed": "use_cached",
    "schools": "warn_only",
    "hazard": "use_cached",
    "census": "use_cached",
    "walkscore": "warn_only",
    "hoa": "use_cached",
}


class DataRefreshService:
    """Coordinates refreshing all data sources for a property."""

    # ------------------------------------------------------------------
    # Refresh all sources
    # ------------------------------------------------------------------

    @staticmethod
    async def refresh_all(
        db: AsyncSession,
        property_id: str,
    ) -> dict[str, Any]:
        """Refresh all data sources for a property.

        Returns dict with status per source::

            {
                "zillow": {"status": "refreshed", "fields_updated": 25},
                "county": {"status": "refreshed", "fields_updated": 18},
                "schools": {"status": "refreshed", "fields_updated": 6},
                ...
            }
        """
        # Verify property exists
        prop = await _load_property_with_address(db, property_id)
        if prop is None:
            return {"_error": "property_not_found"}

        results: dict[str, Any] = {}
        for source in SOURCE_MAP:
            try:
                result = await DataRefreshService.refresh_source(
                    db, property_id, source
                )
                results[source] = result
            except Exception:
                logger.exception(
                    "Error refreshing %s for property %s", source, property_id
                )
                results[source] = {"status": "error", "error": "refresh_failed"}

        return results

    # ------------------------------------------------------------------
    # Refresh a single source
    # ------------------------------------------------------------------

    @staticmethod
    async def refresh_source(
        db: AsyncSession,
        property_id: str,
        source: str,
    ) -> dict[str, Any]:
        """Refresh a single data source.

        Args:
            db: Database session.
            property_id: Property to refresh.
            source: One of "zillow", "redfin", "county", "schools",
                    "hazard", "census", "walkscore".

        Returns:
            Dict with "status" and "fields_updated" or "error".
        """
        source = source.lower().strip()

        if source == "schools":
            return await _refresh_schools(db, property_id)
        elif source == "county":
            return await _refresh_county(db, property_id)
        elif source == "hazard":
            return await _refresh_hazard(db, property_id)
        elif source in ("zillow", "redfin"):
            return await _refresh_listing(db, property_id, source)
        elif source == "walkscore":
            return await _refresh_stub(db, property_id, source)
        elif source == "census":
            return await _refresh_stub(db, property_id, source)
        else:
            return {"status": "unknown_source", "source": source}

    # ------------------------------------------------------------------
    # Check freshness
    # ------------------------------------------------------------------

    @staticmethod
    async def check_freshness(
        db: AsyncSession,
        property_id: str,
    ) -> dict[str, Any]:
        """Check data freshness for all sources.

        Returns dict per source with:
        - last_fetched: datetime or None
        - ttl_hours: int
        - is_stale: bool
        - stale_behavior: str
        """
        now = datetime.now(timezone.utc)

        # Load freshness policies from DB
        policies = await _load_freshness_policies(db)

        freshness: dict[str, Any] = {}
        for source_slug, entity_type in SOURCE_MAP.items():
            ttl_hours = policies.get(entity_type, {}).get(
                "ttl_hours", DEFAULT_TTL.get(entity_type, 24)
            )
            stale_behavior = policies.get(entity_type, {}).get(
                "stale_behavior", DEFAULT_STALE_BEHAVIOR.get(entity_type, "warn_only")
            )

            # Find the most recent SourceRecord for this source
            last_fetched = await _get_last_fetched(db, property_id, source_slug)

            is_stale = True
            if last_fetched is not None:
                cutoff = now - timedelta(hours=ttl_hours)
                is_stale = last_fetched < cutoff

            freshness[source_slug] = {
                "last_fetched": last_fetched.isoformat() if last_fetched else None,
                "ttl_hours": ttl_hours,
                "is_stale": is_stale,
                "stale_behavior": stale_behavior,
            }

        return freshness

    # ------------------------------------------------------------------
    # Cross-reference all sources
    # ------------------------------------------------------------------

    @staticmethod
    async def cross_reference_all(
        db: AsyncSession,
        property_id: str,
    ) -> dict[str, Any]:
        """Run cross-reference checks across all sources.

        Compares: Zillow vs County, Zillow vs LCPS, listing vs assessment, etc.
        Returns list of conflicts with severity.
        """
        conflicts: list[dict[str, Any]] = []

        # 1. LCPS vs Zillow school cross-reference
        try:
            from pipa.services.school_service import SchoolService
            school_xref = await SchoolService.cross_reference_zillow(db, property_id)
            for mismatch in school_xref.get("mismatches", []):
                conflicts.append({
                    "field": f"school_{mismatch['level']}",
                    "source_a": "lcps_official",
                    "value_a": mismatch["lcps_says"],
                    "source_b": "zillow",
                    "value_b": mismatch["zillow_says"],
                    "severity": "medium",
                    "note": "School boundary mismatch — LCPS is authoritative",
                })
            if school_xref.get("boundary_change_warning"):
                conflicts.append({
                    "field": "school_boundary",
                    "source_a": "lcps_official",
                    "value_a": "boundary_change_pending",
                    "source_b": None,
                    "value_b": None,
                    "severity": "high",
                    "note": "Future school boundary differs from current year",
                })
        except Exception:
            logger.exception("Error in LCPS vs Zillow cross-reference")

        # 2. Listing price vs county assessment
        try:
            price_conflict = await _cross_ref_price_vs_assessment(db, property_id)
            if price_conflict:
                conflicts.append(price_conflict)
        except Exception:
            logger.exception("Error in price vs assessment cross-reference")

        # 3. Year built cross-reference (Zillow vs County)
        try:
            yb_conflict = await _cross_ref_field(
                db, property_id, "year_built",
                source_a_pattern="%zillow%",
                source_b_pattern="%county%",
                severity="low",
            )
            if yb_conflict:
                conflicts.append(yb_conflict)
        except Exception:
            logger.exception("Error in year_built cross-reference")

        # 4. Square footage cross-reference
        try:
            sqft_conflict = await _cross_ref_field(
                db, property_id, "sqft",
                source_a_pattern="%zillow%",
                source_b_pattern="%county%",
                severity="medium",
                tolerance_pct=5.0,
            )
            if sqft_conflict:
                conflicts.append(sqft_conflict)
        except Exception:
            logger.exception("Error in sqft cross-reference")

        # 5. Lot size cross-reference
        try:
            lot_conflict = await _cross_ref_field(
                db, property_id, "lot_size",
                source_a_pattern="%zillow%",
                source_b_pattern="%county%",
                severity="low",
                tolerance_pct=5.0,
            )
            if lot_conflict:
                conflicts.append(lot_conflict)
        except Exception:
            logger.exception("Error in lot_size cross-reference")

        return {
            "property_id": property_id,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
        }


# ======================================================================
# Internal refresh helpers
# ======================================================================


async def _load_property_with_address(
    db: AsyncSession,
    property_id: str,
) -> Optional[Property]:
    """Load a property with its addresses."""
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses))
        .where(Property.id == property_id)
    )
    return result.scalar_one_or_none()


async def _get_property_address(
    db: AsyncSession,
    property_id: str,
) -> Optional[str]:
    """Get the current situs address for a property."""
    result = await db.execute(
        select(AddressHistory).where(
            AddressHistory.property_id == property_id,
            AddressHistory.is_current.is_(True),
            AddressHistory.address_type == "situs",
        )
    )
    addr = result.scalar_one_or_none()
    if addr:
        return addr.normalized_address
    return None


async def _get_last_fetched(
    db: AsyncSession,
    property_id: str,
    source_slug: str,
) -> Optional[datetime]:
    """Find the most recent SourceRecord fetch time for a source slug."""
    # Map slug to source_name patterns
    patterns = {
        "zillow": "zillow%",
        "redfin": "redfin%",
        "county": "loudoun_%",  # or fairfax_
        "schools": "lcps_%",
        "hazard": "hazard%",
        "census": "census%",
        "walkscore": "walkscore%",
    }
    pattern = patterns.get(source_slug, f"{source_slug}%")

    result = await db.execute(
        select(SourceRecord.fetched_at)
        .where(
            SourceRecord.property_id == property_id,
            SourceRecord.source_name.like(pattern),
        )
        .order_by(SourceRecord.fetched_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def _load_freshness_policies(db: AsyncSession) -> dict[str, dict]:
    """Load TTL policies from the database."""
    result = await db.execute(select(DataFreshnessPolicy))
    policies = result.scalars().all()

    policy_map: dict[str, dict] = {}
    for p in policies:
        policy_map[p.entity_type] = {
            "ttl_hours": p.ttl_hours,
            "stale_behavior": p.stale_behavior,
            "refresh_priority": p.refresh_priority,
        }
    return policy_map


async def _refresh_schools(
    db: AsyncSession,
    property_id: str,
) -> dict[str, Any]:
    """Refresh school boundary data from LCPS."""
    from pipa.services.school_service import SchoolService

    data = await SchoolService.refresh(db, property_id)
    if data.get("_error"):
        return {"status": "error", "error": data["_error"]}

    # Count how many school-related evidence items we stored
    fields = sum(
        1 for key in ("elementary", "middle", "high",
                       "future_elementary", "future_middle", "future_high")
        if data.get(key, {}).get("name")
    )
    return {"status": "refreshed", "fields_updated": fields}


async def _refresh_county(
    db: AsyncSession,
    property_id: str,
) -> dict[str, Any]:
    """Refresh county assessment/parcel data."""
    from pipa.services.county_service import CountyService

    result = await CountyService.refresh_county_data(db, property_id)
    total = result.assessments_fetched + result.permits_fetched + result.deeds_fetched
    if result.errors:
        return {"status": "error", "error": "; ".join(result.errors)}
    return {"status": "refreshed", "fields_updated": total}


async def _refresh_hazard(
    db: AsyncSession,
    property_id: str,
) -> dict[str, Any]:
    """Refresh hazard profile from static data."""
    from pipa.services.hazard_service import HazardService

    profile = await HazardService.enrich_hazard_profile(db, property_id)
    # Count non-None risk fields
    risk_fields = [
        profile.flood_risk_score,
        profile.wildfire_risk,
        profile.earthquake_risk,
        profile.hurricane_risk,
        profile.tornado_risk,
        profile.radon_risk,
    ]
    fields = sum(1 for f in risk_fields if f is not None)
    return {"status": "refreshed", "fields_updated": fields}


async def _refresh_listing(
    db: AsyncSession,
    property_id: str,
    source: str,
) -> dict[str, Any]:
    """Refresh listing data from Zillow or Redfin.

    This is a placeholder — in production it would re-scrape
    the listing URL stored in the most recent ListingPageSnapshot.
    """
    now = datetime.now(timezone.utc)
    record = SourceRecord(
        property_id=property_id,
        source_name=f"{source}_listing",
        source_url=f"scheduled_refresh:{source}",
        fetched_at=now,
        raw_payload={"status": "refresh_scheduled"},
    )
    db.add(record)
    await db.flush()
    return {"status": "scheduled", "fields_updated": 0}


async def _refresh_stub(
    db: AsyncSession,
    property_id: str,
    source: str,
) -> dict[str, Any]:
    """Stub refresh for sources not yet implemented."""
    return {"status": "not_implemented", "source": source, "fields_updated": 0}


# ======================================================================
# Cross-reference helpers
# ======================================================================


async def _cross_ref_price_vs_assessment(
    db: AsyncSession,
    property_id: str,
) -> Optional[dict[str, Any]]:
    """Compare listing price against county assessed value."""
    # Get listing price
    price_result = await db.execute(
        select(EvidenceItem).where(
            EvidenceItem.property_id == property_id,
            EvidenceItem.field_name == "list_price",
        ).order_by(EvidenceItem.observed_at.desc()).limit(1)
    )
    price_item = price_result.scalar_one_or_none()

    # Get assessed value
    assessed_result = await db.execute(
        select(EvidenceItem).where(
            EvidenceItem.property_id == property_id,
            EvidenceItem.field_name.in_(["assessed_total", "tax_assessed_value"]),
        ).order_by(EvidenceItem.observed_at.desc()).limit(1)
    )
    assessed_item = assessed_result.scalar_one_or_none()

    if not price_item or not assessed_item:
        return None

    try:
        price = float(price_item.field_value.replace(",", "").replace("$", ""))
        assessed = float(assessed_item.field_value.replace(",", "").replace("$", ""))
    except (ValueError, AttributeError):
        return None

    if assessed <= 0:
        return None

    ratio = price / assessed
    if ratio > 1.3 or ratio < 0.7:
        return {
            "field": "price_vs_assessment",
            "source_a": "listing",
            "value_a": f"${price:,.0f}",
            "source_b": "county_assessment",
            "value_b": f"${assessed:,.0f}",
            "severity": "medium" if (ratio > 1.5 or ratio < 0.5) else "low",
            "note": f"Listing price is {ratio:.0%} of assessed value",
        }

    return None


async def _cross_ref_field(
    db: AsyncSession,
    property_id: str,
    field_name: str,
    source_a_pattern: str,
    source_b_pattern: str,
    severity: str = "low",
    tolerance_pct: float = 0.0,
) -> Optional[dict[str, Any]]:
    """Generic field cross-reference between two source patterns."""
    # Find latest evidence from source A
    a_result = await db.execute(
        select(EvidenceItem)
        .join(SourceRecord, EvidenceItem.source_record_id == SourceRecord.id)
        .where(
            EvidenceItem.property_id == property_id,
            EvidenceItem.field_name == field_name,
            SourceRecord.source_name.like(source_a_pattern),
        )
        .order_by(EvidenceItem.observed_at.desc())
        .limit(1)
    )
    item_a = a_result.scalar_one_or_none()

    # Find latest evidence from source B
    b_result = await db.execute(
        select(EvidenceItem)
        .join(SourceRecord, EvidenceItem.source_record_id == SourceRecord.id)
        .where(
            EvidenceItem.property_id == property_id,
            EvidenceItem.field_name == field_name,
            SourceRecord.source_name.like(source_b_pattern),
        )
        .order_by(EvidenceItem.observed_at.desc())
        .limit(1)
    )
    item_b = b_result.scalar_one_or_none()

    if not item_a or not item_b:
        return None

    val_a = item_a.field_value.strip()
    val_b = item_b.field_value.strip()

    # Try numeric comparison with tolerance
    if tolerance_pct > 0:
        try:
            num_a = float(val_a.replace(",", "").replace("$", ""))
            num_b = float(val_b.replace(",", "").replace("$", ""))
            if num_b > 0:
                diff_pct = abs(num_a - num_b) / num_b * 100
                if diff_pct <= tolerance_pct:
                    return None
        except (ValueError, ZeroDivisionError):
            pass

    # String comparison
    if val_a.upper() == val_b.upper():
        return None

    return {
        "field": field_name,
        "source_a": source_a_pattern.replace("%", ""),
        "value_a": val_a,
        "source_b": source_b_pattern.replace("%", ""),
        "value_b": val_b,
        "severity": severity,
        "note": f"{field_name} differs between sources",
    }
