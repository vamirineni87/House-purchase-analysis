"""Appraisal analysis — pure functions, no I/O.

Ported from archive/cli-v1 with BaseAnalyzer/AppConfig dependency removed.
All config values are passed as explicit parameters.

Evaluates whether a property is priced fairly by analyzing comparable sales.
Comps are passed in as data — no API calls.
"""

from __future__ import annotations

from datetime import date
from statistics import mean
from typing import Optional

from pipa.schemas.appraisal import AppraisalResult, ComparableSale, PriceBenchmarks


def adjust_comparable(
    comp: ComparableSale,
    subject_sqft: int,
    subject_beds: int,
    subject_baths: float,
    subject_year_built: Optional[int] = None,
    appreciation_rate: float = 0.03,
) -> ComparableSale:
    """Apply standard appraisal adjustments to a comparable sale.

    Adjustments move the comp's price toward what it *would have sold for*
    if it were identical to the subject property.

    - Square footage: $100 per sqft difference.
    - Bedrooms: $10,000 per bedroom difference.
    - Bathrooms: $7,500 per bathroom difference.
    - Year built: $2,000 per year difference.
    - Time: appreciation_rate applied to months since sale.
    """
    adjustments: dict[str, float] = {}

    # --- Square footage ---
    sqft_diff = subject_sqft - comp.square_feet
    adjustments["sqft"] = sqft_diff * 100.0

    # --- Bedrooms ---
    bed_diff = subject_beds - comp.bedrooms
    adjustments["bedrooms"] = bed_diff * 10_000.0

    # --- Bathrooms ---
    bath_diff = subject_baths - comp.bathrooms
    adjustments["bathrooms"] = bath_diff * 7_500.0

    # --- Year built / age ---
    if comp.year_built and subject_year_built:
        year_diff = subject_year_built - comp.year_built
        adjustments["year_built"] = year_diff * 2_000.0
    else:
        adjustments["year_built"] = 0.0

    # --- Time adjustment (market appreciation since sale) ---
    today = date.today()
    months_since_sale = (
        (today.year - comp.sale_date.year) * 12
        + (today.month - comp.sale_date.month)
    )
    monthly_appreciation = appreciation_rate / 12.0
    time_adjustment = comp.sale_price * monthly_appreciation * max(months_since_sale, 0)
    adjustments["time"] = round(time_adjustment, 2)

    total_adjustment = sum(adjustments.values())
    adjusted_price = comp.sale_price + total_adjustment

    return comp.model_copy(
        update={
            "adjustments": adjustments,
            "adjusted_price": round(adjusted_price, 2),
        }
    )


def assess_value(
    comps: list[ComparableSale],
    list_price: float,
    sqft: int = 0,
) -> tuple[float, float, float, str]:
    """Derive low/mid/high value estimates and a market assessment.

    Uses price-per-sqft from adjusted comps applied to the subject's sqft.
    If *sqft* is 0 the raw adjusted prices are used directly.

    Returns:
        (low, mid, high, assessment) where assessment is one of
        ``"below_market"``, ``"at_market"``, or ``"above_market"``.
    """
    sqft = max(sqft, 1)

    adjusted_ppsf_values = [
        (c.adjusted_price or c.sale_price) / max(c.square_feet, 1)
        for c in comps
    ]

    low = min(adjusted_ppsf_values) * sqft
    mid = mean(adjusted_ppsf_values) * sqft
    high = max(adjusted_ppsf_values) * sqft

    if list_price < mid * 0.95:
        assessment = "below_market"
    elif list_price > mid * 1.05:
        assessment = "above_market"
    else:
        assessment = "at_market"

    return low, mid, high, assessment


def determine_confidence(comps: list[ComparableSale]) -> str:
    """Return a confidence label based on the number of comparables.

    - 0 comps  -> ``"low"``
    - 1-3 comps -> ``"medium"``
    - 4+ comps -> ``"high"``
    """
    count = len(comps)
    if count == 0:
        return "low"
    if count <= 3:
        return "medium"
    return "high"


def compute_price_benchmarks(
    asking_price: float,
    county_assessed: float | None = None,
    county_assessed_year: int | None = None,
    zestimate: float | None = None,
    assessment_markup_pct: float = 7.0,
) -> PriceBenchmarks:
    """Compute price benchmarks comparing ask against multiple sources.

    Args:
        asking_price: the listing ask price.
        county_assessed: official county assessed value.
        county_assessed_year: tax year of the assessment.
        zestimate: Zillow's automated valuation.
        assessment_markup_pct: % above assessment for market estimate.
            Default 7% — adjustable per area. Loudoun County assessments
            typically trail market by 5-10%.
    """
    benchmarks = PriceBenchmarks(
        asking_price=asking_price,
        assessment_markup_pct=assessment_markup_pct,
    )

    if zestimate:
        benchmarks.zestimate = zestimate
        benchmarks.ask_vs_zestimate = round(asking_price - zestimate, 2)
        benchmarks.ask_vs_zestimate_pct = round((asking_price / zestimate - 1) * 100, 1)

    if county_assessed:
        benchmarks.county_assessed = county_assessed
        benchmarks.county_assessed_year = county_assessed_year
        benchmarks.ask_vs_assessed = round(asking_price - county_assessed, 2)
        benchmarks.ask_vs_assessed_pct = round((asking_price / county_assessed - 1) * 100, 1)

        derived = county_assessed * (1 + assessment_markup_pct / 100)
        benchmarks.county_derived_market_value = round(derived, 2)
        benchmarks.ask_vs_county_derived = round(asking_price - derived, 2)
        benchmarks.ask_vs_county_derived_pct = round((asking_price / derived - 1) * 100, 1)

    return benchmarks


def run_appraisal_analysis(
    list_price: float,
    sqft: int,
    beds: int,
    baths: float,
    year_built: Optional[int] = None,
    comps: list[ComparableSale] | None = None,
    appreciation_rate: float = 0.03,
    county_assessed: float | None = None,
    county_assessed_year: int | None = None,
    zestimate: float | None = None,
    assessment_markup_pct: float = 7.0,
) -> AppraisalResult:
    """Run end-to-end appraisal analysis. Single entry point.

    Parameters
    ----------
    list_price:
        The subject property's asking price.
    sqft:
        Subject square footage.
    beds:
        Subject bedroom count.
    baths:
        Subject bathroom count.
    year_built:
        Subject year built (optional).
    comps:
        Comparable sales data. When empty/None a heuristic fallback is used.
    appreciation_rate:
        Annual market appreciation rate for time-adjusting comps.
    """
    if comps is None:
        comps = []

    # --- Adjust comparables ---
    adjusted_comps = [
        adjust_comparable(comp, sqft, beds, baths, year_built, appreciation_rate)
        for comp in comps
    ]

    # --- Assess value ---
    if adjusted_comps:
        low, mid, high, assessment = assess_value(adjusted_comps, list_price, sqft)
    else:
        # Heuristic fallback: assume subject price is the only data point
        mid = list_price
        low = mid * 0.90
        high = mid * 1.10
        assessment = "at_market"

    confidence = determine_confidence(adjusted_comps)

    subject_ppsf = list_price / max(sqft, 1)
    market_ppsf = mid / max(sqft, 1) if mid else subject_ppsf

    # Compute price benchmarks if assessment/zestimate data available
    benchmarks = None
    if county_assessed or zestimate:
        benchmarks = compute_price_benchmarks(
            asking_price=list_price,
            county_assessed=county_assessed,
            county_assessed_year=county_assessed_year,
            zestimate=zestimate,
            assessment_markup_pct=assessment_markup_pct,
        )

    return AppraisalResult(
        comparables=adjusted_comps,
        estimated_value_low=round(low, 2),
        estimated_value_mid=round(mid, 2),
        estimated_value_high=round(high, 2),
        price_per_sqft_market=round(market_ppsf, 2),
        subject_price_per_sqft=round(subject_ppsf, 2),
        value_assessment=assessment,
        confidence=confidence,
        price_benchmarks=benchmarks,
    )
