"""School boundary lookup and cross-reference service.

Orchestrates the LCPS School Locator scraper, stores results as
EvidenceItem records, and cross-references against Zillow-scraped
school data to surface mismatches and boundary changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.property import AddressHistory, Property
from pipa.models.source import EvidenceItem, SourceRecord

logger = logging.getLogger(__name__)

# Evidence field names for school data
_SCHOOL_FIELDS = {
    "elementary": "school_elementary",
    "middle": "school_middle",
    "high": "school_high",
    "future_elementary": "school_future_elementary",
    "future_middle": "school_future_middle",
    "future_high": "school_future_high",
    "school_board_member": "school_board_member",
    "boundary_change": "school_boundary_change",
}


class SchoolService:
    """Fetches, stores, and cross-references LCPS school boundary data."""

    # ------------------------------------------------------------------
    # Lookup and store
    # ------------------------------------------------------------------

    @staticmethod
    async def lookup_and_store(
        db: AsyncSession,
        property_id: str,
        address: str,
        *,
        headless: bool = True,
        screenshot_dir: Path | None = None,
    ) -> dict:
        """Look up schools from LCPS and store as evidence items.

        Args:
            db: Database session.
            property_id: Property to attach evidence to.
            address: Street address to search in the LCPS dashboard.
            headless: Run browser in headless mode.
            screenshot_dir: Where to save screenshots.

        Returns:
            Raw school data dict from the scraper.
        """
        from pipa.clients.scrapers.lcps_schools import LCPSSchoolScraper

        scraper = LCPSSchoolScraper(headless=headless)
        try:
            data = await scraper.lookup_schools(
                address,
                save_screenshot=True,
                screenshot_dir=screenshot_dir,
            )
        finally:
            await scraper.close()

        if data.get("_error"):
            logger.warning(
                "LCPS lookup failed for property %s: %s",
                property_id,
                data["_error"],
            )
            return data

        now = datetime.now(timezone.utc)

        # Create SourceRecord for audit trail
        source_record = SourceRecord(
            property_id=property_id,
            source_name="lcps_official",
            source_url=data.get("_url", ""),
            raw_payload=data,
            fetched_at=now,
        )
        db.add(source_record)
        await db.flush()

        # Store each school level as an EvidenceItem
        evidence_items = []
        for level_key, field_name in _SCHOOL_FIELDS.items():
            value = data.get(level_key)
            if value is None:
                continue

            # For school dicts, store the name as the field value
            if isinstance(value, dict):
                str_value = value.get("name", "")
            elif isinstance(value, bool):
                str_value = str(value)
            else:
                str_value = str(value)

            if not str_value:
                continue

            evidence = EvidenceItem(
                property_id=property_id,
                field_name=field_name,
                field_value=str_value,
                source_record_id=source_record.id,
                observed_at=now,
                confidence="confirmed",  # LCPS is the authoritative source
            )
            db.add(evidence)
            evidence_items.append(evidence)

        # Store detailed school info (address, phone, etc.) as separate fields
        for level in ("elementary", "middle", "high"):
            school = data.get(level, {})
            if not isinstance(school, dict):
                continue
            for detail_key in ("principal", "phone", "address", "website"):
                detail_value = school.get(detail_key)
                if detail_value:
                    evidence = EvidenceItem(
                        property_id=property_id,
                        field_name=f"school_{level}_{detail_key}",
                        field_value=str(detail_value),
                        source_record_id=source_record.id,
                        observed_at=now,
                        confidence="confirmed",
                    )
                    db.add(evidence)

        # Store school year info
        for year_key in ("current_year", "future_year"):
            year_value = data.get(year_key)
            if year_value:
                evidence = EvidenceItem(
                    property_id=property_id,
                    field_name=f"school_{year_key}",
                    field_value=str(year_value),
                    source_record_id=source_record.id,
                    observed_at=now,
                    confidence="confirmed",
                )
                db.add(evidence)

        await db.flush()
        logger.info(
            "Stored %d LCPS evidence items for property %s",
            len(evidence_items),
            property_id,
        )

        return data

    # ------------------------------------------------------------------
    # Cross-reference against Zillow
    # ------------------------------------------------------------------

    @staticmethod
    async def cross_reference_zillow(
        db: AsyncSession,
        property_id: str,
    ) -> dict:
        """Compare LCPS official schools against Zillow-scraped schools.

        Returns dict with:
        - matches: list of matching schools by level
        - mismatches: list of {level, zillow_says, lcps_says}
        - boundary_change_warning: bool
        """
        result = {
            "matches": [],
            "mismatches": [],
            "boundary_change_warning": False,
        }

        # Load LCPS evidence items
        lcps_schools = {}
        lcps_result = await db.execute(
            select(EvidenceItem).where(
                EvidenceItem.property_id == property_id,
                EvidenceItem.field_name.in_([
                    "school_elementary",
                    "school_middle",
                    "school_high",
                ]),
            ).order_by(EvidenceItem.observed_at.desc())
        )
        for item in lcps_result.scalars().all():
            # Source check: verify this came from LCPS
            sr = await db.execute(
                select(SourceRecord).where(
                    SourceRecord.id == item.source_record_id,
                    SourceRecord.source_name == "lcps_official",
                )
            )
            if sr.scalar_one_or_none() is not None:
                level = item.field_name.replace("school_", "")
                if level not in lcps_schools:
                    lcps_schools[level] = item.field_value

        # Load Zillow school evidence — Zillow stores schools as a list
        # in a single evidence item with field_name "schools"
        zillow_schools: dict[str, str] = {}
        zillow_result = await db.execute(
            select(EvidenceItem).where(
                EvidenceItem.property_id == property_id,
                EvidenceItem.field_name.like("school%"),
            ).order_by(EvidenceItem.observed_at.desc())
        )
        for item in zillow_result.scalars().all():
            sr = await db.execute(
                select(SourceRecord).where(
                    SourceRecord.id == item.source_record_id,
                    SourceRecord.source_name.like("%zillow%"),
                )
            )
            if sr.scalar_one_or_none() is not None:
                field = item.field_name
                # Normalize Zillow school field names
                for level in ("elementary", "middle", "high"):
                    if level in field.lower() and level not in zillow_schools:
                        zillow_schools[level] = item.field_value

        # Compare LCPS vs Zillow by level
        for level in ("elementary", "middle", "high"):
            lcps_name = lcps_schools.get(level, "").strip().upper()
            zillow_name = zillow_schools.get(level, "").strip().upper()

            if not lcps_name or not zillow_name:
                continue

            if _fuzzy_school_match(lcps_name, zillow_name):
                result["matches"].append({
                    "level": level,
                    "school": lcps_name,
                })
            else:
                result["mismatches"].append({
                    "level": level,
                    "lcps_says": lcps_name,
                    "zillow_says": zillow_name,
                })

        # Check for boundary change warning
        boundary_items = await db.execute(
            select(EvidenceItem).where(
                EvidenceItem.property_id == property_id,
                EvidenceItem.field_name == "school_boundary_change",
            ).order_by(EvidenceItem.observed_at.desc()).limit(1)
        )
        boundary_item = boundary_items.scalar_one_or_none()
        if boundary_item and boundary_item.field_value.lower() == "true":
            result["boundary_change_warning"] = True

        return result

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    @staticmethod
    async def refresh(
        db: AsyncSession,
        property_id: str,
        *,
        headless: bool = True,
    ) -> dict:
        """Re-scrape LCPS for latest school assignments.

        Same as lookup_and_store but resolves the address from the property
        and marks old LCPS evidence as superseded by creating newer entries.
        """
        # Resolve address from property
        address = await SchoolService._resolve_address(db, property_id)
        if not address:
            return {"_error": "no_address", "property_id": property_id}

        return await SchoolService.lookup_and_store(
            db,
            property_id,
            address,
            headless=headless,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_address(
        db: AsyncSession,
        property_id: str,
    ) -> Optional[str]:
        """Resolve the street address for LCPS lookup from the property."""
        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.property_id == property_id,
                AddressHistory.is_current.is_(True),
                AddressHistory.address_type == "situs",
            )
        )
        addr = result.scalar_one_or_none()
        if addr is not None:
            return addr.normalized_address
        return None


def _fuzzy_school_match(name_a: str, name_b: str) -> bool:
    """Check if two school names likely refer to the same school.

    Handles variations like "Buffalo Trail ES" vs "Buffalo Trail Elementary School".
    """
    # Normalize
    a = _normalize_school_name(name_a)
    b = _normalize_school_name(name_b)

    # Exact match after normalization
    if a == b:
        return True

    # Check if one contains the other (handles abbreviation differences)
    if a in b or b in a:
        return True

    # Check if the core name matches (strip ES/MS/HS/Elementary/etc.)
    core_a = _strip_level_suffix(a)
    core_b = _strip_level_suffix(b)
    if core_a and core_b and core_a == core_b:
        return True

    return False


def _normalize_school_name(name: str) -> str:
    """Normalize a school name for comparison."""
    import re
    name = name.upper().strip()
    # Remove punctuation
    name = re.sub(r"[^\w\s]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)
    return name


def _strip_level_suffix(name: str) -> str:
    """Strip school level suffixes for core name comparison."""
    import re
    name = re.sub(
        r"\s*(ELEMENTARY\s*SCHOOL|MIDDLE\s*SCHOOL|HIGH\s*SCHOOL|ES|MS|HS)\s*$",
        "", name,
    )
    return name.strip()
