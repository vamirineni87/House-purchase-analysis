"""FEMA National Risk Index (NRI) data stubs for Virginia counties.

The NRI provides county-level composite risk scores for 18 natural hazards.
Full dataset: https://hazards.fema.gov/nri/data-resources

This module provides reasonable default values for Virginia counties until
we integrate the full NRI dataset download. Scores are 0-100 (relative risk
within the state; higher = more risk).

Risk ratings: Very Low, Relatively Low, Relatively Moderate, Relatively High, Very High
"""

from __future__ import annotations

from typing import Any

# Default risk profile for a typical Northern Virginia county
_NOVA_DEFAULT_RISKS: dict[str, Any] = {
    "composite_risk_rating": "Relatively Moderate",
    "composite_risk_score": 42.0,
    "expected_annual_loss": 1_500_000,  # dollars (county-level)
    "social_vulnerability": "Relatively Low",
    "community_resilience": "Relatively High",
    "hazards": {
        "earthquake": {"rating": "Relatively Low", "score": 15.0},
        "flooding": {"rating": "Relatively Moderate", "score": 45.0},
        "hurricane": {"rating": "Relatively Moderate", "score": 40.0},
        "ice_storm": {"rating": "Relatively Moderate", "score": 35.0},
        "lightning": {"rating": "Relatively Moderate", "score": 38.0},
        "strong_wind": {"rating": "Relatively Moderate", "score": 42.0},
        "tornado": {"rating": "Relatively Low", "score": 22.0},
        "winter_weather": {"rating": "Relatively Moderate", "score": 40.0},
        "hail": {"rating": "Relatively Low", "score": 20.0},
        "heat_wave": {"rating": "Relatively Moderate", "score": 35.0},
        "drought": {"rating": "Relatively Low", "score": 18.0},
        "wildfire": {"rating": "Very Low", "score": 8.0},
        "landslide": {"rating": "Very Low", "score": 5.0},
        "coastal_flooding": {"rating": "Very Low", "score": 3.0},
        "cold_wave": {"rating": "Relatively Low", "score": 25.0},
        "avalanche": {"rating": "Very Low", "score": 0.0},
        "tsunami": {"rating": "Very Low", "score": 0.0},
        "volcanic_activity": {"rating": "Very Low", "score": 0.0},
    },
}

# County-specific overrides (only deltas from NOVA default)
_COUNTY_OVERRIDES: dict[str, dict[str, Any]] = {
    "Fairfax": {
        "composite_risk_score": 44.0,
        "expected_annual_loss": 2_200_000,
        "hazards_overrides": {
            "flooding": {"rating": "Relatively Moderate", "score": 48.0},
            "hurricane": {"rating": "Relatively Moderate", "score": 42.0},
        },
    },
    "Loudoun": {
        "composite_risk_score": 38.0,
        "expected_annual_loss": 1_100_000,
        "hazards_overrides": {
            "flooding": {"rating": "Relatively Moderate", "score": 40.0},
            "tornado": {"rating": "Relatively Low", "score": 25.0},
        },
    },
    "Arlington": {
        "composite_risk_score": 46.0,
        "expected_annual_loss": 1_800_000,
        "social_vulnerability": "Relatively Moderate",
        "hazards_overrides": {
            "flooding": {"rating": "Relatively High", "score": 55.0},
        },
    },
    "Prince William": {
        "composite_risk_score": 40.0,
        "expected_annual_loss": 1_400_000,
        "hazards_overrides": {
            "flooding": {"rating": "Relatively Moderate", "score": 43.0},
        },
    },
    "Alexandria": {
        "composite_risk_score": 48.0,
        "expected_annual_loss": 2_000_000,
        "hazards_overrides": {
            "flooding": {"rating": "Relatively High", "score": 58.0},
            "coastal_flooding": {"rating": "Relatively Low", "score": 20.0},
        },
    },
    "Fauquier": {
        "composite_risk_score": 30.0,
        "expected_annual_loss": 600_000,
        "community_resilience": "Relatively Moderate",
        "hazards_overrides": {
            "flooding": {"rating": "Relatively Low", "score": 30.0},
        },
    },
    "Stafford": {
        "composite_risk_score": 36.0,
        "expected_annual_loss": 800_000,
        "hazards_overrides": {
            "flooding": {"rating": "Relatively Moderate", "score": 38.0},
        },
    },
}


def load_nri_for_county(county: str, state: str = "VA") -> dict:
    """Load FEMA NRI risk data for a given county.

    Currently returns reasonable defaults/stubs for Virginia counties.
    Will be replaced with actual NRI dataset integration.

    Args:
        county: County name (e.g. ``"Fairfax"``, ``"Loudoun County"``).
        state: State abbreviation.

    Returns:
        Dict with risk ratings, scores, and per-hazard breakdown.
        Always returns data (defaults for unknown counties).
    """
    import copy

    if state.upper() != "VA":
        # Return generic defaults for non-VA (stub)
        result = copy.deepcopy(_NOVA_DEFAULT_RISKS)
        result["county"] = county
        result["state"] = state
        result["_stub"] = True
        return result

    # Normalize county name
    clean = county.replace(" County", "").replace("City of ", "").strip()

    result = copy.deepcopy(_NOVA_DEFAULT_RISKS)
    result["county"] = county
    result["state"] = state

    overrides = _COUNTY_OVERRIDES.get(clean, {})
    if overrides:
        # Apply top-level overrides
        for key in ["composite_risk_score", "composite_risk_rating",
                     "expected_annual_loss", "social_vulnerability",
                     "community_resilience"]:
            if key in overrides:
                result[key] = overrides[key]

        # Apply hazard-specific overrides
        hazard_overrides = overrides.get("hazards_overrides", {})
        for hazard, vals in hazard_overrides.items():
            if hazard in result["hazards"]:
                result["hazards"][hazard].update(vals)

    result["_stub"] = True  # flag that this is estimated, not real NRI data
    return result
