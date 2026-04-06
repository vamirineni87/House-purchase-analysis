"""Market data endpoints — ZIP-level market metrics and trends."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.property import AddressHistory

router = APIRouter(tags=["market"])


@router.get(
    "/properties/{property_id}/market",
    summary="Get market metrics for the property's ZIP code",
)
async def get_market_data(
    property_id: str,
    months: int = Query(12, ge=1, le=36),
    db: AsyncSession = Depends(get_db),
):
    """Return housing market metrics for the property's ZIP code.

    Uses Redfin Data Center (free CSV) for historical monthly data
    and computes buyer/seller market indicators.
    """
    # Get property ZIP code
    result = await db.execute(
        select(AddressHistory)
        .where(AddressHistory.property_id == property_id)
        .order_by(AddressHistory.created_at.desc())
        .limit(1)
    )
    addr = result.scalar_one_or_none()
    if not addr or not addr.zip_code:
        raise HTTPException(404, "Property address or ZIP code not found")

    zip_code = addr.zip_code[:5]  # Normalize to 5-digit

    from pipa.clients.redfin_data import RedfinDataClient

    client = RedfinDataClient()
    metrics = await client.get_zip_metrics(zip_code, months=months)

    if not metrics:
        # Try county-level fallback
        county = addr.county or ""
        if county:
            metrics = await client.get_county_metrics(county, "Virginia", months)

    indicators = client.compute_market_indicators(metrics) if metrics else {}

    return {
        "zip_code": zip_code,
        "county": addr.county,
        "monthly_metrics": metrics,
        "indicators": indicators,
    }


@router.get(
    "/market/{zip_code}",
    summary="Get market metrics for a ZIP code directly",
)
async def get_market_by_zip(
    zip_code: str,
    months: int = Query(12, ge=1, le=36),
):
    """Return housing market metrics for any ZIP code."""
    from pipa.clients.redfin_data import RedfinDataClient

    client = RedfinDataClient()
    metrics = await client.get_zip_metrics(zip_code, months=months)
    indicators = client.compute_market_indicators(metrics) if metrics else {}

    return {
        "zip_code": zip_code,
        "monthly_metrics": metrics,
        "indicators": indicators,
    }
