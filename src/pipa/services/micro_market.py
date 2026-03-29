"""Micro-market analysis service — neighborhood investment signals."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.analysis.surrounding import (
    analyze_surrounding,
    calculate_investor_share,
    calculate_turnover_rate,
    score_neighborhood_stability,
)
from pipa.models.deed import DeedRecord
from pipa.models.listing import SaleEvent
from pipa.models.nearby import NearbyRelationship
from pipa.models.property import AddressHistory

logger = logging.getLogger(__name__)


class MicroMarketService:
    """Computes micro-market metrics using nearby relationships and events."""

    @staticmethod
    async def analyze_micro_market(
        db: AsyncSession,
        property_id: str,
    ) -> dict:
        """Compute turnover rate, investor share, and stability score.

        Uses nearby relationships (from ``NearbyDiscoveryService``) and
        their associated sale/listing events to feed the pure-function
        analysis in ``pipa.analysis.surrounding``.

        Returns a dict with:
        - ``investor_share``: fraction of nearby properties that are investor-owned
        - ``turnover_rate``: annual turnover rate
        - ``flip_count``: properties that sold twice within 18 months
        - ``stability_score``: 0-100 composite score
        - ``total_nearby``: number of nearby properties analyzed
        - ``total_sales``: number of sales events found
        """
        # Load nearby relationships for the subject property
        rel_result = await db.execute(
            select(NearbyRelationship).where(
                NearbyRelationship.subject_property_id == property_id,
                NearbyRelationship.is_current.is_(True),
            )
        )
        relationships = list(rel_result.scalars().all())

        if not relationships:
            logger.info("No nearby relationships for property %s", property_id)
            return {
                "investor_share": 0.0,
                "turnover_rate": 0.0,
                "flip_count": 0,
                "stability_score": 100.0,
                "total_nearby": 0,
                "total_sales": 0,
            }

        related_ids = [r.related_property_id for r in relationships]

        # Build nearby_properties list for investor share analysis
        nearby_properties = await MicroMarketService._build_nearby_properties(
            db, related_ids
        )

        # Build nearby_sales list for turnover / flip analysis
        nearby_sales = await MicroMarketService._build_nearby_sales(
            db, related_ids
        )

        # Delegate to pure-function analysis
        result = analyze_surrounding(
            nearby_properties=nearby_properties,
            nearby_sales=nearby_sales,
            total_properties=len(related_ids),
        )

        result["total_sales"] = len(nearby_sales)

        logger.info(
            "Micro-market for %s: stability=%.1f, investor=%.2f, turnover=%.4f",
            property_id,
            result["stability_score"],
            result["investor_share"],
            result["turnover_rate"],
        )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _build_nearby_properties(
        db: AsyncSession,
        property_ids: list[str],
    ) -> list[dict]:
        """Build the nearby_properties dicts for surrounding analysis.

        Uses a heuristic: if a property has a mailing address different
        from its situs address, it is likely investor-owned. Without
        mailing data, defaults to owner-occupied.
        """
        if not property_ids:
            return []

        result = await db.execute(
            select(AddressHistory).where(
                AddressHistory.property_id.in_(property_ids),
                AddressHistory.is_current.is_(True),
            )
        )
        addresses = list(result.scalars().all())

        # Group by property
        by_prop: dict[str, list[AddressHistory]] = {}
        for addr in addresses:
            by_prop.setdefault(addr.property_id, []).append(addr)

        nearby: list[dict] = []
        for prop_id, addrs in by_prop.items():
            situs = None
            mailing = None
            for a in addrs:
                if a.address_type == "situs":
                    situs = a
                elif a.address_type == "mailing":
                    mailing = a

            # Heuristic: different mailing address suggests investor
            owner_occupied = True
            if situs and mailing:
                if situs.normalized_address != mailing.normalized_address:
                    owner_occupied = False

            nearby.append({
                "property_id": prop_id,
                "owner_occupied": owner_occupied,
                "address": situs.normalized_address if situs else "",
            })

        return nearby

    @staticmethod
    async def _build_nearby_sales(
        db: AsyncSession,
        property_ids: list[str],
    ) -> list[dict]:
        """Build the nearby_sales dicts for surrounding analysis.

        Combines SaleEvent and DeedRecord data.
        """
        if not property_ids:
            return []

        sales: list[dict] = []

        # SaleEvent records
        sale_result = await db.execute(
            select(SaleEvent).where(
                SaleEvent.property_id.in_(property_ids),
            )
        )
        for se in sale_result.scalars().all():
            sales.append({
                "property_id": se.property_id,
                "sale_date": se.sale_date.isoformat() if se.sale_date else None,
                "address": se.property_id,  # fallback key for flip detection
            })

        # DeedRecord records (may overlap with SaleEvent)
        deed_result = await db.execute(
            select(DeedRecord).where(
                DeedRecord.property_id.in_(property_ids),
            )
        )
        for dr in deed_result.scalars().all():
            if dr.sale_date:
                sales.append({
                    "property_id": dr.property_id,
                    "sale_date": dr.sale_date.isoformat(),
                    "address": dr.property_id,
                })

        return sales
