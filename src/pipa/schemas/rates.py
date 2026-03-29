"""Pydantic v2 schemas for rate lookup endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class MortgageRates(BaseModel):
    """Current / default mortgage rates."""

    rate_30yr: float
    rate_15yr: float
    source: str = "default"
    as_of: str = ""


class CountyTaxRate(BaseModel):
    """Tax rate information for a county."""

    county: str
    property_tax_rate: float
    vehicle_tax_rate: float = 0.0
    stormwater_fee: float = 0.0
    source: str = "static"
