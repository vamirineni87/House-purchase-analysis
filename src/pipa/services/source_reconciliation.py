"""Source reconciliation service — multi-source field conflict resolution."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.source import EvidenceItem, SourceRegistry

logger = logging.getLogger(__name__)

# Default confidence ranks when a source is not in the registry.
_DEFAULT_CONFIDENCE_RANK = 10


class SourceReconciliationService:
    """Reconciles field values across multiple data sources."""

    # ------------------------------------------------------------------
    # Reconcile a single field
    # ------------------------------------------------------------------

    @staticmethod
    async def reconcile_field(
        db: AsyncSession,
        property_id: str,
        field_name: str,
    ) -> dict:
        """Get all evidence for a field, rank by source confidence, return best.

        Returns a dict with:
        - ``field_name``: the queried field
        - ``best_value``: the value from the most-trusted source
        - ``best_source``: name of that source
        - ``best_confidence_rank``: numeric rank of that source
        - ``all_evidence``: list of dicts for every evidence item
        - ``has_conflict``: True if sources disagree on the value
        """
        evidence_rows = await db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.property_id == property_id,
                EvidenceItem.field_name == field_name,
            )
            .order_by(EvidenceItem.observed_at.desc())
        )
        items = list(evidence_rows.scalars().all())

        if not items:
            return {
                "field_name": field_name,
                "best_value": None,
                "best_source": None,
                "best_confidence_rank": 0,
                "all_evidence": [],
                "has_conflict": False,
            }

        # Load source registry for confidence ranking
        source_names = {item.source_record_id for item in items}
        source_rank_cache: dict[str, int] = {}

        # Build ranked evidence list
        ranked: list[dict] = []
        for item in items:
            source_name = await SourceReconciliationService._resolve_source_name(
                db, item.source_record_id
            )
            rank = await SourceReconciliationService._get_cached_rank(
                db, source_name, source_rank_cache
            )
            ranked.append({
                "evidence_id": item.id,
                "field_value": item.field_value,
                "source_name": source_name,
                "confidence_rank": rank,
                "confidence": item.confidence,
                "observed_at": item.observed_at.isoformat() if item.observed_at else None,
            })

        # Sort by confidence rank descending (highest = most trusted)
        ranked.sort(key=lambda e: e["confidence_rank"], reverse=True)

        # Detect conflicts — do distinct values appear?
        distinct_values = {e["field_value"] for e in ranked}
        has_conflict = len(distinct_values) > 1

        best = ranked[0]

        return {
            "field_name": field_name,
            "best_value": best["field_value"],
            "best_source": best["source_name"],
            "best_confidence_rank": best["confidence_rank"],
            "all_evidence": ranked,
            "has_conflict": has_conflict,
        }

    # ------------------------------------------------------------------
    # Find all conflicts for a property
    # ------------------------------------------------------------------

    @staticmethod
    async def find_conflicts(
        db: AsyncSession,
        property_id: str,
    ) -> list[dict]:
        """Find fields where multiple sources disagree on the value.

        Returns a list of dicts, one per conflicted field, each containing
        ``field_name``, ``distinct_values``, and ``evidence_count``.
        """
        evidence_rows = await db.execute(
            select(EvidenceItem)
            .where(EvidenceItem.property_id == property_id)
            .order_by(EvidenceItem.field_name, EvidenceItem.observed_at.desc())
        )
        items = list(evidence_rows.scalars().all())

        # Group by field name
        by_field: dict[str, list[EvidenceItem]] = {}
        for item in items:
            by_field.setdefault(item.field_name, []).append(item)

        conflicts: list[dict] = []
        for field_name, field_items in by_field.items():
            distinct_values = {fi.field_value for fi in field_items}
            if len(distinct_values) > 1:
                conflicts.append({
                    "field_name": field_name,
                    "distinct_values": list(distinct_values),
                    "evidence_count": len(field_items),
                })

        return conflicts

    # ------------------------------------------------------------------
    # Confidence rank lookup
    # ------------------------------------------------------------------

    @staticmethod
    def get_confidence_rank(source_name: str) -> int:
        """Synchronous confidence rank heuristic for known source names.

        For a database-backed lookup use the async ``reconcile_field``
        method, which queries ``SourceRegistry``.
        """
        known_ranks: dict[str, int] = {
            "county_gis": 90,
            "fairfax_gis": 90,
            "loudoun_gis": 90,
            "deed_record": 80,
            "assessment": 80,
            "rentcast": 60,
            "listing_mls": 40,
            "zillow": 35,
            "redfin": 35,
            "user": 30,
            "heuristic": 10,
        }
        return known_ranks.get(source_name.lower(), _DEFAULT_CONFIDENCE_RANK)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_source_name(
        db: AsyncSession,
        source_record_id: str,
    ) -> str:
        """Resolve a source_record_id to its source_name."""
        from pipa.models.source import SourceRecord

        result = await db.execute(
            select(SourceRecord.source_name).where(
                SourceRecord.id == source_record_id
            )
        )
        name = result.scalar_one_or_none()
        return name or "unknown"

    @staticmethod
    async def _get_cached_rank(
        db: AsyncSession,
        source_name: str,
        cache: dict[str, int],
    ) -> int:
        """Get confidence rank, using cache to avoid repeated queries."""
        if source_name in cache:
            return cache[source_name]

        result = await db.execute(
            select(SourceRegistry.confidence_rank).where(
                SourceRegistry.source_name == source_name
            )
        )
        rank = result.scalar_one_or_none()
        if rank is None:
            rank = SourceReconciliationService.get_confidence_rank(source_name)

        cache[source_name] = rank
        return rank
