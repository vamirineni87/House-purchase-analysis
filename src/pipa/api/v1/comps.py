"""Comparable sales endpoints — 2-stage comp system.

Quick comp: fast, runs automatically on every new listing.
Deep comp: slow (~2 min), user-triggered for shortlisted homes.
Legacy endpoints kept for backward compatibility.
"""

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
    DeepCompResult,
    EnrichedComp,
    QuickCompResult,
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
# Quick comp — fast, runs automatically on every new listing
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/comps/quick",
    response_model=QuickCompResult,
    summary="Quick comp analysis — fast, no county scraping",
)
async def quick_comp(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run a quick comp analysis using only already-scraped data.

    This is fast (<2 seconds) and runs automatically when a listing is
    ingested. It produces a rough value band from portal prices and
    identifies 5-8 likely comparable sales.

    No county scraping is performed — use ``/comps/deep`` for verified data.
    """
    await _verify_property(db, property_id)
    result = await CompService.quick_comp(db, property_id)
    return QuickCompResult(**result)


# ------------------------------------------------------------------
# Deep comp — slow (~2 min), user-triggered for shortlisted homes
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/comps/deep",
    response_model=DeepCompResult,
    summary="Deep comp analysis — county-verified, adjustment-grade",
)
async def deep_comp(
    property_id: str,
    body: CompAnalysisRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Run a deep comp analysis with county-verified data.

    This endpoint takes ~2 minutes due to county scraping (15-20s per comp).
    Use only for shortlisted homes where you need verified data.

    1. Finds and ranks comp candidates by similarity
    2. County-enriches top 4-6 candidates with verified details
    3. Runs full appraisal adjustment engine
    4. Detects listing-site vs county discrepancies
    """
    await _verify_property(db, property_id)

    subject_data = None
    max_comps = 6
    if body:
        max_comps = body.max_comps
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

    result = await CompService.deep_comp(
        db, property_id, subject_data=subject_data, max_comps=max_comps
    )
    return DeepCompResult(**result)


# ------------------------------------------------------------------
# Get stored results (quick + deep if available)
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/comps",
    summary="Get stored comp analysis results (quick + deep)",
)
async def get_comp_results(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the most recent comp analysis results for a property.

    Returns stored quick_comp and/or deep_comp results.
    Returns 404 if no comp analysis has been run yet.
    """
    await _verify_property(db, property_id)
    result = await CompService.get_stored_results(db, property_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No comp analysis found. Run POST /comps/quick or /comps/deep first.",
        )
    return result


# ------------------------------------------------------------------
# Legacy endpoints — backward compatibility aliases
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


@router.post(
    "/properties/{property_id}/comps/analyze",
    response_model=CompAnalysisResult,
    summary="Full comp analysis (legacy — use /comps/deep instead)",
)
async def run_comp_analysis(
    property_id: str,
    body: CompAnalysisRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Legacy endpoint — delegates to deep_comp internally.

    Use POST /comps/deep for new integrations.
    """
    await _verify_property(db, property_id)

    subject_data = None
    max_comps = 6
    if body:
        max_comps = body.max_comps
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
