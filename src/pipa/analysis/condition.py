"""Property condition and capital expenditure analysis — pure functions.

Estimates remaining useful life of major home components, forecasts
replacement costs, and scores overall property condition.
"""

from __future__ import annotations

from datetime import datetime

# ------------------------------------------------------------------
# Default lifespans (years) for major home components
# ------------------------------------------------------------------

DEFAULT_LIFESPANS: dict[str, int] = {
    "roof_asphalt_shingle": 25,
    "roof_metal": 50,
    "roof_tile": 50,
    "hvac_furnace": 20,
    "hvac_ac": 15,
    "hvac_heat_pump": 15,
    "water_heater_tank": 12,
    "water_heater_tankless": 20,
    "windows": 25,
    "siding_vinyl": 30,
    "siding_wood": 20,
    "siding_fiber_cement": 30,
    "deck_wood": 15,
    "deck_composite": 25,
    "driveway_asphalt": 20,
    "driveway_concrete": 30,
    "garage_door": 20,
    "exterior_paint": 10,
    "carpet": 10,
    "hardwood_refinish": 15,
    "kitchen_remodel": 20,
    "bathroom_remodel": 20,
    "septic_system": 30,
    "well_pump": 15,
    "electrical_panel": 30,
    "plumbing_supply": 50,
    "plumbing_drain": 50,
    "foundation": 75,
    "appliances": 12,
}

# ------------------------------------------------------------------
# Default replacement / repair costs (USD)
# ------------------------------------------------------------------

DEFAULT_REPLACEMENT_COSTS: dict[str, float] = {
    "roof_asphalt_shingle": 12_000.0,
    "roof_metal": 25_000.0,
    "roof_tile": 30_000.0,
    "hvac_furnace": 6_000.0,
    "hvac_ac": 6_500.0,
    "hvac_heat_pump": 8_000.0,
    "water_heater_tank": 2_000.0,
    "water_heater_tankless": 3_500.0,
    "windows": 15_000.0,
    "siding_vinyl": 12_000.0,
    "siding_wood": 15_000.0,
    "siding_fiber_cement": 18_000.0,
    "deck_wood": 8_000.0,
    "deck_composite": 12_000.0,
    "driveway_asphalt": 5_000.0,
    "driveway_concrete": 8_000.0,
    "garage_door": 2_500.0,
    "exterior_paint": 5_000.0,
    "carpet": 4_000.0,
    "hardwood_refinish": 5_000.0,
    "kitchen_remodel": 30_000.0,
    "bathroom_remodel": 15_000.0,
    "septic_system": 20_000.0,
    "well_pump": 3_000.0,
    "electrical_panel": 3_000.0,
    "plumbing_supply": 15_000.0,
    "plumbing_drain": 15_000.0,
    "foundation": 25_000.0,
    "appliances": 8_000.0,
}

# ------------------------------------------------------------------
# Evidence hierarchy — confidence levels for component age sources
# ------------------------------------------------------------------

EVIDENCE_CONFIDENCE: dict[str, float] = {
    "permit": 0.95,
    "inspection": 0.85,
    "disclosure": 0.70,
    "listing": 0.50,
    "user": 0.60,
    "age_estimate": 0.30,
}


# ------------------------------------------------------------------
# Core functions
# ------------------------------------------------------------------


def estimate_remaining_life(
    component_type: str,
    install_year: int,
    current_year: int | None = None,
    lifespans: dict[str, int] | None = None,
) -> int:
    """Estimate years of remaining useful life for a component.

    Returns 0 when the component has exceeded its expected lifespan.
    """
    if current_year is None:
        current_year = datetime.now().year
    if lifespans is None:
        lifespans = DEFAULT_LIFESPANS

    lifespan = lifespans.get(component_type)
    if lifespan is None:
        raise ValueError(
            f"Unknown component type: {component_type!r}. "
            f"Known types: {sorted(lifespans.keys())}"
        )

    age = current_year - install_year
    remaining = lifespan - age
    return max(remaining, 0)


def calculate_capex_forecast(
    components: list[dict],
    current_year: int | None = None,
    horizons: list[int] | None = None,
    lifespans: dict[str, int] | None = None,
    replacement_costs: dict[str, float] | None = None,
) -> dict[int, float]:
    """Forecast capital expenditure over multiple time horizons.

    Parameters
    ----------
    components:
        List of dicts, each with keys ``"type"`` (str) and
        ``"install_year"`` (int).  An optional ``"cost_override"``
        (float) allows per-component cost overrides.
    current_year:
        Defaults to the current calendar year.
    horizons:
        List of horizon lengths in years (e.g. ``[1, 3, 5, 10]``).
    lifespans:
        Override default lifespans.
    replacement_costs:
        Override default replacement costs.

    Returns
    -------
    dict mapping each horizon (years) to the total projected CapEx
    within that window.
    """
    if current_year is None:
        current_year = datetime.now().year
    if horizons is None:
        horizons = [1, 3, 5, 10]
    if lifespans is None:
        lifespans = DEFAULT_LIFESPANS
    if replacement_costs is None:
        replacement_costs = DEFAULT_REPLACEMENT_COSTS

    forecast: dict[int, float] = {h: 0.0 for h in horizons}

    for comp in components:
        ctype = comp.get("type") or comp.get("component_type", "unknown")
        install_year = comp.get("install_year") or comp.get("estimated_install_year", current_year)
        cost = comp.get("cost_override") or replacement_costs.get(ctype, 0.0)

        remaining = estimate_remaining_life(
            ctype, install_year, current_year, lifespans
        )

        for horizon in horizons:
            if remaining <= horizon:
                forecast[horizon] = round(forecast[horizon] + cost, 2)

    return forecast


def score_property_condition(
    components: list[dict],
    current_year: int | None = None,
    lifespans: dict[str, int] | None = None,
) -> float:
    """Score overall property condition from 0 (worst) to 100 (best).

    The score is the weighted-average percentage of remaining life
    across all components, weighted by their replacement cost.
    A brand-new home scores ~100; one where everything is past due
    scores 0.
    """
    if current_year is None:
        current_year = datetime.now().year
    if lifespans is None:
        lifespans = DEFAULT_LIFESPANS

    total_weight = 0.0
    weighted_life_pct = 0.0

    for comp in components:
        ctype = comp.get("type") or comp.get("component_type", "unknown")
        install_year = comp.get("install_year") or comp.get("estimated_install_year", current_year)
        cost = comp.get("cost_override") or DEFAULT_REPLACEMENT_COSTS.get(ctype, 1.0)
        lifespan = lifespans.get(ctype)
        if lifespan is None or lifespan == 0:
            continue

        age = current_year - install_year
        life_pct = max(0.0, min(1.0, 1.0 - (age / lifespan)))

        total_weight += cost
        weighted_life_pct += life_pct * cost

    if total_weight == 0:
        return 100.0

    score = (weighted_life_pct / total_weight) * 100.0
    return round(score, 1)
