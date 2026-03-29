"""Comparable sales endpoints — find, enrich, and analyze comps."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_db
from pipa.models.property import Property
from pipa.schemas.comp import (
    CompAnalysisRequest,
    CompAnalysisResult,
    CompCandidate,
    EnrichedComp,
)
from pipa.services.comp_service import CompService

router = APIRouter(tags=["comps"])


async def _verify_property(db: AsyncSession, property_id: str) -> Property:
    """Load and return the property or raise 404."""
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses))
        .where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


# ------------------------------------------------------------------
# Find comp candidates (fast, no county scraping)
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/comps/find",
    response_model=list[CompCandidate],
    summary="Find comp candidates from listing sites",
)
async def find_comp_candidates(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Find comparable sale candidates from stored listing data.

    Returns raw candidates from Zillow/Redfin/Realtor nearby sold data
    and county neighborhood sales. Fast -- no live scraping involved.
    """
    await _verify_property(db, property_id)
    candidates = await CompService.find_comp_candidates(db, property_id)
    return candidates


# ------------------------------------------------------------------
# Full pipeline: find + enrich + analyze (slow, ~2 min)
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/comps/analyze",
    response_model=CompAnalysisResult,
    summary="Full comp analysis: find, enrich from county, run appraisal",
)
async def run_comp_analysis(
    property_id: str,
    body: CompAnalysisRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Run end-to-end comparable sales analysis.

    1. Finds comp candidates from stored listing data
    2. Enriches each comp with county-verified details (~15-20s each)
    3. Runs appraisal adjustments using county-verified sqft (above grade)
    4. Detects conflicts between listing site and county data

    **This endpoint takes ~2 minutes** for 4-6 comps due to county
    scraping. Consider using the background task version for production.
    """
    await _verify_property(db, property_id)

    subject_data = None
    max_comps = 6
    if body:
        max_comps = body.max_comps
        # Build subject_data from request if any overrides provided
        if any([body.list_price, body.sqft, body.beds, body.baths, body.year_built]):
            subject_data = {}
            if body.list_price is not None:
                subject_data["list_price"] = body.list_price
            if body.sqft is not None:
                subject_data["sqft"] = body.sqft
            if body.beds is not None:
                subject_data["beds"] = body.beds
            if body.baths is not None:
                subject_data["baths"] = body.baths
            if body.year_built is not None:
                subject_data["year_built"] = body.year_built

    result = await CompService.run_comp_analysis(
        db, property_id, subject_data=subject_data, max_comps=max_comps
    )
    return CompAnalysisResult(**result)


# ------------------------------------------------------------------
# Get stored comp analysis results
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/comps",
    summary="Get stored comp analysis results",
)
async def get_comp_results(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the most recent comp analysis results for a property.

    Returns the stored analysis from the last ``/comps/analyze`` run,
    including enriched comps, appraisal result, data quality metrics,
    and any listing-vs-county conflicts detected.

    Returns 404 if no comp analysis has been run yet.
    """
    await _verify_property(db, property_id)
    result = await CompService.get_stored_results(db, property_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No comp analysis found. Run POST /comps/analyze first.",
        )
    return result
