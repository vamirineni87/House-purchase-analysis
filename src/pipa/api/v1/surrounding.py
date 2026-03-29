"""Surrounding properties analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.analysis.surrounding import analyze_surrounding
from pipa.core.dependencies import get_db
from pipa.models.deed import DeedRecord
from pipa.models.nearby import NearbyRelationship
from pipa.models.property import Property
from pipa.schemas.surrounding import SurroundingStats

router = APIRouter(tags=["surrounding"])


@router.get(
    "/properties/{property_id}/surrounding/stats",
    response_model=SurroundingStats,
)
async def get_surrounding_stats(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get surrounding property statistics (investor share, turnover, stability).

    Uses the nearby_relationship table to identify related properties
    and their sales history.
    """
    # Verify property exists
    prop_result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    if prop_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Property not found")

    # Find nearby properties
    nearby_result = await db.execute(
        select(NearbyRelationship).where(
            NearbyRelationship.subject_property_id == property_id,
            NearbyRelationship.is_current == True,  # noqa: E712
        )
    )
    nearby_rels = list(nearby_result.scalars().all())

    if not nearby_rels:
        return SurroundingStats(
            property_id=property_id,
            total_nearby=0,
            stability_score=100.0,
        )

    related_ids = [r.related_property_id for r in nearby_rels]

    # Build nearby_properties list (we don't have owner_occupied data yet,
    # so we treat all as owner-occupied for now)
    nearby_properties = [{"owner_occupied": True} for _ in related_ids]

    # Get sales data for nearby properties
    sales_result = await db.execute(
        select(DeedRecord).where(DeedRecord.property_id.in_(related_ids))
    )
    nearby_sales = [
        {
            "sale_date": d.sale_date,
            "address": d.property_id,
            "sale_price": d.sale_price,
        }
        for d in sales_result.scalars().all()
        if d.sale_date is not None
    ]

    # Run surrounding analysis
    analysis = analyze_surrounding(
        nearby_properties=nearby_properties,
        nearby_sales=nearby_sales,
    )

    # Compute median sale price if we have sales
    median_price = None
    prices = sorted(
        [s["sale_price"] for s in nearby_sales if s.get("sale_price")],
    )
    if prices:
        mid = len(prices) // 2
        if len(prices) % 2 == 0:
            median_price = round((prices[mid - 1] + prices[mid]) / 2, 2)
        else:
            median_price = prices[mid]

    return SurroundingStats(
        property_id=property_id,
        investor_share=analysis["investor_share"],
        turnover_rate=analysis["turnover_rate"],
        flip_count=analysis["flip_count"],
        stability_score=analysis["stability_score"],
        total_nearby=analysis["total_nearby"],
        median_sale_price=median_price,
    )
