"""Analysis endpoints — run financial, tax, investment, condition, offer, stress analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_db
from pipa.models.property import Property
from pipa.schemas.analysis import (
    ConditionAnalysisResult,
    FullAnalysisRequest,
    FullAnalysisResult,
    OfferAnalysisRequest,
    OfferAnalysisResult,
    StressTestRequest,
    StressTestResult,
)
from pipa.schemas.financial import FinancialAnalysisRequest, FinancialAnalysisResult
from pipa.schemas.investment import InvestmentAnalysisRequest, InvestmentAnalysisResult
from pipa.schemas.tax import TaxAnalysisRequest, TaxAnalysisResult
from pipa.services.analysis_service import AnalysisService

router = APIRouter(tags=["analysis"])


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
# Financial
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/financial",
    response_model=FinancialAnalysisResult,
)
async def run_financial(
    property_id: str,
    body: FinancialAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run financial analysis on a property."""
    await _verify_property(db, property_id)
    return await AnalysisService.run_financial(db, property_id, body)


# ------------------------------------------------------------------
# Tax
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/tax",
    response_model=TaxAnalysisResult,
)
async def run_tax(
    property_id: str,
    body: TaxAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run tax analysis on a property.

    Includes mortgage interest deduction, property tax deduction (SALT cap),
    and optionally the sell-vs-rent strategy for a current home.
    """
    await _verify_property(db, property_id)
    return await AnalysisService.run_tax(db, property_id, body)


# ------------------------------------------------------------------
# Investment
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/investment",
    response_model=InvestmentAnalysisResult,
)
async def run_investment(
    property_id: str,
    body: InvestmentAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run investment analysis on a property.

    Includes equity projections, IRR, and rent-vs-buy comparison.
    """
    await _verify_property(db, property_id)
    return await AnalysisService.run_investment(db, property_id, body)


# ------------------------------------------------------------------
# Condition
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/condition",
    response_model=ConditionAnalysisResult,
)
async def run_condition(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run condition analysis on a property.

    Uses stored component data (roof, HVAC, etc.) to estimate
    remaining life and forecast capital expenditure.
    """
    await _verify_property(db, property_id)
    result = await AnalysisService.run_condition(db, property_id)
    return ConditionAnalysisResult(**result)


# ------------------------------------------------------------------
# Offer strategy
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/offer",
    response_model=OfferAnalysisResult,
)
async def run_offer(
    property_id: str,
    body: OfferAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run offer strategy analysis.

    Determines max bid, walk-away price, escalation modelling,
    and appraisal gap risk assessment.
    """
    await _verify_property(db, property_id)
    result = await AnalysisService.run_offer(db, property_id, body.model_dump())
    return OfferAnalysisResult(**result)


# ------------------------------------------------------------------
# Stress testing
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/stress",
    response_model=StressTestResult,
)
async def run_stress(
    property_id: str,
    body: StressTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run stress test scenarios.

    Models rate shock, insurance inflation, and downside sale outcomes.
    """
    await _verify_property(db, property_id)
    result = await AnalysisService.run_stress(db, property_id, body.model_dump())
    return StressTestResult(**result)


# ------------------------------------------------------------------
# Full analysis (all-in-one)
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/analysis/full",
    response_model=FullAnalysisResult,
)
async def run_full(
    property_id: str,
    body: FullAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run all analyses (financial, tax, investment, condition) at once."""
    await _verify_property(db, property_id)
    result = await AnalysisService.run_all(db, property_id, body.model_dump())
    return FullAnalysisResult(**result)
