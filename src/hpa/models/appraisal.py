"""Appraisal and comparable-sale Pydantic v2 models."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

from hpa.models.property import Address


class ComparableSale(BaseModel):
    """A comparable property sale used in appraisal analysis."""

    address: Address
    sale_price: float
    sale_date: date
    square_feet: int
    bedrooms: int
    bathrooms: float
    year_built: Optional[int] = None
    price_per_sqft: float
    distance_miles: float
    adjustments: dict[str, float] = {}  # e.g., {"bedrooms": -5000, "condition": +10000}
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
