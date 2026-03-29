"""Pydantic v2 schemas for comparable sales sourcing and enrichment."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CompCandidate(BaseModel):
    """Raw comp candidate before county enrichment."""

    address: str
    price: Optional[float] = None  # sale price (sold) or list price (active/pending)
    date: Optional[str] = None  # sale date or list date
    status: str = "sold"  # "sold", "active", "pending", "contingent"
    source: str  # "zillow_nearby", "county_neighborhood", "rentcast"
    distance_mi: Optional[float] = None
    sqft: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    days_on_market: Optional[int] = None  # for active/pending


class EnrichedComp(BaseModel):
    """Comp with county-verified details."""

    address: str
    # Sale info (county-verified)
    sale_price: float
    sale_date: str
    # Dwelling (county Residential tab)
    sqft_above_grade: Optional[int] = None
    total_sqft: Optional[int] = None  # above + finished basement
    year_built: Optional[int] = None
    full_baths: Optional[int] = None
    half_baths: Optional[int] = None
    stories: Optional[int] = None
    style: Optional[str] = None
    condition: Optional[str] = None
    grade: Optional[str] = None
    roof_material: Optional[str] = None
    exterior_wall: Optional[str] = None
    basement_total_sqft: Optional[int] = None
    basement_finished_sqft: Optional[int] = None
    foundation: Optional[str] = None
    lot_acres: Optional[float] = None
    # Assessment
    assessed_total: Optional[float] = None
    # Source tracking
    zillow_sqft: Optional[int] = None  # what listing site said (for conflict detection)
    county_sqft: Optional[int] = None  # what county says (above grade)
    sqft_conflict: bool = False  # True if they disagree by >10%


class CompAnalysisResult(BaseModel):
    """Full comp analysis result."""

    sold_comps: list[EnrichedComp]  # county-verified sold properties
    active_listings: list[CompCandidate] = []  # competing active listings
    pending_listings: list[CompCandidate] = []  # recently went under contract
    appraisal: dict  # AppraisalResult from sold comps
    data_quality: dict
    conflicts: list[dict]
    market_context: Optional[dict] = None  # summary of active/pending vs sold


class CompAnalysisRequest(BaseModel):
    """Optional overrides for comp analysis."""

    max_comps: int = 6
    list_price: Optional[float] = None
    sqft: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    year_built: Optional[int] = None
