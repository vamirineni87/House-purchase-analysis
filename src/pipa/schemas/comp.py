"""Pydantic v2 schemas for comparable sales sourcing and enrichment.

Two-stage comp system:
- QuickCompResult: auto-runs on every new listing, no county scraping
- DeepCompResult: user-triggered, county-verified, adjustment-grade
"""

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
    similarity_score: Optional[float] = None  # 0-100, set by filter_comps
    year_built: Optional[int] = None
    property_type: Optional[str] = None


class EnrichedComp(BaseModel):
    """Comp with county-verified details."""

    address: str
    # Sale info (county-verified)
    sale_price: float
    sale_date: str
    # Dwelling (county Residential tab)
    # Dwelling — above grade
    sqft_above_grade: Optional[int] = None
    total_livable_sqft: Optional[int] = None  # above grade + finished basement
    year_built: Optional[int] = None
    full_baths: Optional[int] = None
    half_baths: Optional[int] = None
    stories: Optional[int] = None
    style: Optional[str] = None
    model: Optional[str] = None  # builder model name (e.g., LONGWOOD, COLORADO II)
    condition: Optional[str] = None  # AVERAGE, GOOD, etc.
    grade: Optional[str] = None  # construction quality
    roof_type: Optional[str] = None  # GABLE, HIP, etc.
    roof_material: Optional[str] = None  # ASPHALT/FBGL SHINGLE, etc.
    exterior_wall: Optional[str] = None  # MASONRY FRONT AV, VINYL, etc.
    heating_ac: Optional[str] = None  # CENTRAL HEAT AND AC, etc.
    fireplaces: Optional[int] = None
    cathedral_ceiling_sqft: Optional[int] = None
    # Basement
    basement_total_sqft: Optional[int] = None
    basement_finished_sqft: Optional[int] = None
    basement_unfinished_sqft: Optional[int] = None  # computed: total - finished
    basement_entrance: Optional[str] = None  # WALK OUT, WALK UP, etc.
    # Attic
    attic_type: Optional[str] = None  # NONE, FINISHED, UNFINISHED
    attic_sqft: Optional[int] = None
    # Garage / attached structures
    garage_sqft: Optional[int] = None
    garage_cars: Optional[int] = None
    deck_sqft: Optional[int] = None
    porch_sqft: Optional[int] = None
    area_over_garage_sqft: Optional[int] = None
    attached_structures: Optional[list[dict]] = None  # raw list from county
    # Foundation / lot
    foundation: Optional[str] = None
    lot_acres: Optional[float] = None
    lot_sqft: Optional[int] = None
    # Assessment
    assessed_land: Optional[float] = None
    assessed_building: Optional[float] = None
    assessed_total: Optional[float] = None
    # Parcel / subdivision
    parcel_id: Optional[str] = None
    subdivision: Optional[str] = None
    builder: Optional[str] = None  # from seller in county sale records
    # Source tracking
    zillow_sqft: Optional[int] = None  # what listing site said (for conflict detection)
    county_sqft: Optional[int] = None  # what county says (above grade)
    sqft_conflict: bool = False  # True if they disagree by >10%


# ======================================================================
# Quick Comp — runs automatically on every new listing, no county scraping
# ======================================================================


class QuickCompResult(BaseModel):
    """Result from quick comp — rough value band, no county scraping."""

    candidates: list[CompCandidate]  # all discovered candidates
    filtered_comps: list[CompCandidate]  # filtered to likely matches (5-8)
    sold_count: int
    active_count: int
    pending_count: int
    rough_value_band: dict  # {low, mid, high} from portal data only
    quick_confidence: str  # "strong", "moderate", "weak", "insufficient"
    warnings: list[str]  # e.g., "few comps in area", "old sales only"
    assessment_context: dict | None = None  # county assessment if available
    asking_vs_comps: str  # "below", "at", "above" market


# ======================================================================
# Deep Comp — runs only when user clicks "Run Deep Comp"
# ======================================================================


class DeepCompResult(BaseModel):
    """Result from deep comp — county-verified, adjustment-grade."""

    sold_comps: list[EnrichedComp]  # county-verified sold (3-6 best)
    active_listings: list[CompCandidate]  # competing
    pending_listings: list[CompCandidate]  # under contract
    appraisal: dict  # AppraisalResult
    adjustments_summary: dict  # per-comp adjustment explanation
    value_range: dict  # {low, mid, high} from adjusted comps
    confidence: str  # high, medium, low
    data_quality: dict
    conflicts: list[dict]  # Zillow vs county discrepancies
    market_context: dict
    unresolved_unknowns: list[str]  # things we couldn't verify


# ======================================================================
# Legacy schemas — kept for backward compatibility
# ======================================================================


class CompAnalysisResult(BaseModel):
    """Full comp analysis result (legacy — use DeepCompResult for new code)."""

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
