"""Insurance cost estimation and natural disaster risk — pure functions, no I/O.

Ported from archive/cli-v1 with BaseAnalyzer/AppConfig dependency removed.
All config values are passed as explicit parameters.

Estimates homeowners insurance, flood insurance, and evaluates regional
natural disaster exposure based on state-level lookup tables.
"""

from __future__ import annotations

from typing import Optional

from pipa.schemas.insurance import (
    FloodInsuranceEstimate,
    HomeownersInsuranceEstimate,
    InsuranceAnalysisResult,
    NaturalDisasterRisk,
)

# ---------------------------------------------------------------------------
# State-level natural disaster risk lookup tables
# ---------------------------------------------------------------------------
_HURRICANE_HIGH_STATES: set[str] = {
    "FL", "LA", "TX", "NC", "SC", "AL", "MS", "GA",
}
_EARTHQUAKE_HIGH_STATES: set[str] = {
    "CA", "AK", "HI", "WA", "OR",
}
_WILDFIRE_HIGH_STATES: set[str] = {
    "CA", "CO", "OR", "WA", "MT", "AZ",
}
_TORNADO_HIGH_STATES: set[str] = {
    "TX", "OK", "KS", "NE", "SD", "IA", "IL", "IN", "MO", "AR",
}

# Flood insurance premium estimates by inferred zone
_FLOOD_PREMIUM_MODERATE = 500.0
_FLOOD_PREMIUM_HIGH = 1_200.0


def estimate_homeowners_insurance(
    home_value: float,
    rate: float = 0.0035,
) -> HomeownersInsuranceEstimate:
    """Estimate standard homeowners insurance (HO-3 equivalent).

    Parameters
    ----------
    home_value:
        Property value / dwelling replacement value.
    rate:
        Annual premium as a fraction of home value (default 0.35%).
    """
    annual = round(home_value * rate, 2)
    monthly = round(annual / 12.0, 2)
    coverage = home_value

    return HomeownersInsuranceEstimate(
        annual_premium=annual,
        monthly_premium=monthly,
        coverage_amount=coverage,
    )


def estimate_flood_insurance(
    flood_zone: Optional[str],
    flood_declarations: int = 0,
) -> Optional[FloodInsuranceEstimate]:
    """Estimate flood insurance based on zone and disaster history.

    Parameters
    ----------
    flood_zone:
        FEMA flood zone designation (e.g. "X", "AE", "VE").
        When ``None`` the zone is inferred from *flood_declarations*.
    flood_declarations:
        Number of historical flood disaster declarations in the area.

    Returns ``None`` when risk is low (no zone, no declarations).
    """
    # Determine effective zone and premium from explicit zone or declaration count.
    high_risk_zones = {"A", "AE", "AH", "AO", "AR", "V", "VE"}
    moderate_risk_zones = {"B", "X500"}

    if flood_zone is not None:
        zone_upper = flood_zone.upper()
        if zone_upper in high_risk_zones:
            return FloodInsuranceEstimate(
                flood_zone=flood_zone,
                annual_premium=_FLOOD_PREMIUM_HIGH,
                required=True,
                coverage_amount=250_000.0,
            )
        if zone_upper in moderate_risk_zones:
            return FloodInsuranceEstimate(
                flood_zone=flood_zone,
                annual_premium=_FLOOD_PREMIUM_MODERATE,
                required=False,
                coverage_amount=250_000.0,
            )

    # Infer from historical declarations when no explicit zone is given.
    if flood_declarations >= 3:
        return FloodInsuranceEstimate(
            flood_zone=flood_zone or "AE",
            annual_premium=_FLOOD_PREMIUM_HIGH,
            required=True,
            coverage_amount=250_000.0,
        )
    if flood_declarations > 0:
        return FloodInsuranceEstimate(
            flood_zone=flood_zone or "X500",
            annual_premium=_FLOOD_PREMIUM_MODERATE,
            required=False,
            coverage_amount=250_000.0,
        )

    # No zone, no declarations — low risk, no flood insurance needed.
    return None


def assess_disaster_risk(state: str) -> NaturalDisasterRisk:
    """Assess natural disaster risk based on the property's state.

    Uses hard-coded state-level risk tables for hurricane, earthquake,
    wildfire, and tornado exposure.  Overall risk score is 1-10 based
    on the number of high-risk categories.

    Parameters
    ----------
    state:
        Two-letter state abbreviation (e.g. "VA", "CA").
    """
    state = state.upper().strip()

    hurricane = "high" if state in _HURRICANE_HIGH_STATES else "low"
    earthquake = "high" if state in _EARTHQUAKE_HIGH_STATES else "low"
    wildfire = "high" if state in _WILDFIRE_HIGH_STATES else "low"
    tornado = "high" if state in _TORNADO_HIGH_STATES else "low"

    high_count = sum(
        1
        for risk in (hurricane, earthquake, wildfire, tornado)
        if risk == "high"
    )

    # Map 0-4 high categories to a 1-10 score.
    # 0 high -> 1, 1 high -> 3, 2 high -> 5, 3 high -> 7, 4 high -> 9
    score_map = {0: 1, 1: 3, 2: 5, 3: 7, 4: 9}
    overall_score = score_map.get(high_count, 10)

    return NaturalDisasterRisk(
        earthquake_risk=earthquake,
        hurricane_risk=hurricane,
        wildfire_risk=wildfire,
        tornado_risk=tornado,
        overall_risk_score=overall_score,
    )


def run_insurance_analysis(
    home_value: float,
    state: str,
    flood_zone: Optional[str] = None,
    flood_declarations: int = 0,
    homeowners_rate: float = 0.0035,
) -> InsuranceAnalysisResult:
    """Run end-to-end insurance analysis. Single entry point.

    Parameters
    ----------
    home_value:
        Property value / list price.
    state:
        Two-letter state abbreviation.
    flood_zone:
        FEMA flood zone (optional; inferred from declarations if absent).
    flood_declarations:
        Number of historical flood disaster declarations.
    homeowners_rate:
        Annual homeowners insurance premium as fraction of home value.
    """
    homeowners = estimate_homeowners_insurance(home_value, homeowners_rate)
    flood_estimate = estimate_flood_insurance(flood_zone, flood_declarations)
    disaster_risk = assess_disaster_risk(state)

    # --- Totals ---
    total_annual = homeowners.annual_premium
    if flood_estimate is not None:
        total_annual += flood_estimate.annual_premium

    total_annual = round(total_annual, 2)
    total_monthly = round(total_annual / 12.0, 2)

    # Risk-adjusted monthly cost adds a buffer for high-risk areas.
    risk_multiplier = 1.0 + (disaster_risk.overall_risk_score - 1) * 0.01
    risk_adjusted = round(total_monthly * risk_multiplier, 2)

    return InsuranceAnalysisResult(
        homeowners=homeowners,
        flood=flood_estimate,
        disaster_risk=disaster_risk,
        total_annual_insurance=total_annual,
        total_monthly_insurance=total_monthly,
        risk_adjusted_monthly_cost=risk_adjusted,
    )
