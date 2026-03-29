"""Neighborhood quality analysis — pure functions, no I/O.

Ported from archive/cli-v1 with BaseAnalyzer/AppConfig dependency removed.
All data is passed as explicit parameters — no API fetching.

Combines school, crime, walkability, flood risk, and demographic data
into a weighted composite neighborhood score.
"""

from __future__ import annotations

from typing import Optional

from pipa.schemas.neighborhood import (
    CrimeStats,
    Demographics,
    FloodRisk,
    NeighborhoodAnalysisResult,
    SchoolRating,
    WalkabilityScores,
)

# National median household income used as a baseline for demographics scoring.
_NATIONAL_MEDIAN_INCOME = 75_000.0

# Composite score weights keyed by data category.
_WEIGHTS: dict[str, float] = {
    "schools": 0.30,
    "crime": 0.20,
    "walkability": 0.20,
    "flood": 0.15,
    "demographics": 0.15,
}


def crime_rate_to_safety(
    violent_rate: Optional[float],
    property_rate: Optional[float] = None,
) -> Optional[float]:
    """Convert crime rates (per 100k) to a 1-10 safety score.

    National average violent crime rate is roughly 380 per 100k.
    Lower rate -> higher score.

    When *property_rate* is provided it nudges the score by up to +/-1
    point (low property crime boosts safety, high penalises it), but the
    primary driver remains the violent-crime rate.
    """
    if violent_rate is None:
        return None

    # Scale: 0 violent crimes = 10, 800+ = 1
    base = max(1.0, min(10.0, 10.0 - (violent_rate / 100.0)))

    if property_rate is not None:
        # National average property crime ~2000 per 100k
        prop_nudge = max(-1.0, min(1.0, 1.0 - (property_rate / 2000.0)))
        base = max(1.0, min(10.0, base + prop_nudge))

    return round(base, 1)


def compute_composite_score(
    schools: list[SchoolRating],
    crime: Optional[CrimeStats],
    walkability: Optional[WalkabilityScores],
    flood: Optional[FloodRisk],
    demographics: Optional[Demographics],
) -> tuple[Optional[float], float]:
    """Compute a weighted composite neighborhood score (0-100).

    Only factors with available data are included; weights are
    re-normalized proportionally.

    Weights: schools 30%, crime 20%, walkability 20%, flood 15%,
    demographics 15%.

    Returns:
        (composite_score, data_completeness) where data_completeness
        is the fraction of the 5 data categories that returned data.
    """
    total_sources = 5
    available_count = 0
    weighted_scores: dict[str, float] = {}

    # --- Schools ---
    rated_schools = [s for s in schools if s.rating is not None]
    if rated_schools:
        avg_rating = sum(s.rating for s in rated_schools) / len(rated_schools)  # type: ignore[arg-type]
        weighted_scores["schools"] = (avg_rating / 10.0) * 100.0
        available_count += 1

    # --- Crime ---
    if crime and crime.overall_safety_score is not None:
        weighted_scores["crime"] = (crime.overall_safety_score / 10.0) * 100.0
        available_count += 1

    # --- Walkability ---
    if walkability and walkability.walk_score is not None:
        weighted_scores["walkability"] = float(walkability.walk_score)
        available_count += 1

    # --- Flood risk ---
    if flood and flood.risk_level != "unknown":
        flood_score_map = {"low": 100.0, "moderate": 50.0, "high": 20.0}
        weighted_scores["flood"] = flood_score_map.get(flood.risk_level, 50.0)
        available_count += 1

    # --- Demographics ---
    if demographics and demographics.median_household_income is not None:
        income_ratio = demographics.median_household_income / _NATIONAL_MEDIAN_INCOME
        # Cap the score at 100 to keep it on the 0-100 scale.
        demo_score = min(income_ratio * 100.0, 100.0)
        weighted_scores["demographics"] = demo_score
        available_count += 1

    data_completeness = available_count / total_sources

    if not weighted_scores:
        return None, data_completeness

    # Re-normalize weights to sum to 1.0 for the available categories.
    active_weights = {k: _WEIGHTS[k] for k in weighted_scores}
    weight_sum = sum(active_weights.values())

    composite = sum(
        (active_weights[k] / weight_sum) * weighted_scores[k]
        for k in weighted_scores
    )

    return composite, data_completeness


def run_neighborhood_analysis(
    schools: list[SchoolRating] | None = None,
    crime_stats: Optional[CrimeStats] = None,
    walk_scores: Optional[WalkabilityScores] = None,
    flood_risk: Optional[FloodRisk] = None,
    demographics: Optional[Demographics] = None,
) -> NeighborhoodAnalysisResult:
    """Run end-to-end neighborhood analysis. Single entry point.

    All data sources are passed in directly — no API calls.

    Parameters
    ----------
    schools:
        List of nearby school ratings.
    crime_stats:
        Crime statistics with rates per 100k population.
    walk_scores:
        Walk Score / Transit Score / Bike Score.
    flood_risk:
        Flood zone and disaster history.
    demographics:
        Demographic data (population, income, home values).
    """
    if schools is None:
        schools = []

    # Auto-compute safety score if crime rates are provided but score is missing
    if crime_stats and crime_stats.overall_safety_score is None:
        safety = crime_rate_to_safety(
            crime_stats.violent_crime_rate,
            crime_stats.property_crime_rate,
        )
        if safety is not None:
            crime_stats = crime_stats.model_copy(
                update={"overall_safety_score": safety}
            )

    composite_score, data_completeness = compute_composite_score(
        schools=schools,
        crime=crime_stats,
        walkability=walk_scores,
        flood=flood_risk,
        demographics=demographics,
    )

    return NeighborhoodAnalysisResult(
        schools=schools,
        crime=crime_stats,
        walkability=walk_scores,
        flood_risk=flood_risk,
        demographics=demographics,
        composite_score=round(composite_score, 1) if composite_score is not None else None,
        data_completeness=round(data_completeness, 2),
    )
