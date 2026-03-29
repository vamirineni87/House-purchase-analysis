"""Pydantic v2 schemas for appraisal analysis."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class ComparableSale(BaseModel):
    """A comparable property sale used in appraisal analysis."""

    address: str
    sale_price: float
    sale_date: date
    square_feet: int
    bedrooms: int
    bathrooms: float
    year_built: Optional[int] = None
    price_per_sqft: float = 0.0
    distance_miles: float = 0.0
    adjustments: dict[str, float] = {}
    adjusted_price: Optional[float] = None


class AppraisalResult(BaseModel):
    """Aggregated appraisal results based on comparable sales."""

    comparables: list[ComparableSale]
    estimated_value_low: float
    estimated_value_mid: float
    estimated_value_high: float
    price_per_sqft_market: float
    subject_price_per_sqft: float
    value_assessment: str  # "below_market", "at_market", "above_market"
    confidence: str  # "low", "medium", "high"


class AppraisalRequest(BaseModel):
    """Request body for the appraisal analysis endpoint."""

    list_price: float
    square_feet: int
    bedrooms: int
    bathrooms: float
    year_built: Optional[int] = None
    comps: list[ComparableSale] = []
    appreciation_rate: float = 0.03  # annual, for time-adjusting comps
