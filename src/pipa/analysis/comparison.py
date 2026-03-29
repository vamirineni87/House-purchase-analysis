"""Property comparison — pure functions, no I/O.

Ported from archive/cli-v1 with BaseAnalyzer/AppConfig/FinancialAnalyzer
dependencies removed.  All scores are computed from pre-calculated data
passed as dicts.

EXPANDED beyond the original (financial, value, size) with four new
scoring dimensions:
  - condition_score   (from capex forecast)
  - hoa_risk_score    (from HOA risk analysis)
  - hazard_score      (from insurance disaster risk)
  - surrounding_stability_score (from surrounding-property analysis)

Default weights:
  financial=0.20, value=0.15, size=0.10, condition=0.20,
  hoa=0.10, hazard=0.10, surrounding=0.15
"""

from __future__ import annotations

from typing import Any, Optional

# ------------------------------------------------------------------
# Default scoring weights
# ------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "financial": 0.20,
    "value": 0.15,
    "size": 0.10,
    "condition": 0.20,
    "hoa": 0.10,
    "hazard": 0.10,
    "surrounding": 0.15,
}


def _normalize_score(
    value: float,
    all_values: list[float],
    *,
    lower_is_better: bool = False,
) -> float:
    """Normalize *value* to 0-100 relative to the group in *all_values*.

    When *lower_is_better* is True (e.g. monthly payment, price/sqft),
    the lowest value gets 100 and the highest gets 0.
    """
    lo = min(all_values)
    hi = max(all_values)

    if hi == lo:
        return 100.0  # all identical -> perfect score for everyone

    if lower_is_better:
        return round(100.0 * (1.0 - (value - lo) / (hi - lo)), 2)
    else:
        return round(100.0 * ((value - lo) / (hi - lo)), 2)


def score_property(
    property_data: dict[str, Any],
    all_properties: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score a single property relative to the full comparison set.

    Parameters
    ----------
    property_data:
        Dict for the subject property with keys:

        - ``"monthly_payment"`` (float): best-scenario total monthly payment
        - ``"price_per_sqft"`` (float): list_price / sqft
        - ``"sqft"`` (int): living area square footage
        - ``"condition_score"`` (float, 0-100): from ``score_property_condition``
        - ``"hoa_risk"`` (int, 1-10): from ``score_hoa_risk``
        - ``"hazard_score"`` (int, 1-10): from ``assess_disaster_risk().overall_risk_score``
        - ``"stability_score"`` (float, 0-100): from ``score_neighborhood_stability``
        - ``"address"`` (str): display address

    all_properties:
        The full list (including *property_data*) for group-relative
        normalisation.

    Returns
    -------
    dict with per-dimension scores (0-100), a weighted total, and
    ``"pros"`` / ``"cons"`` lists.
    """
    # Collect group-wide raw values for each dimension.
    payments = [p["monthly_payment"] for p in all_properties]
    ppsfs = [p["price_per_sqft"] for p in all_properties]
    sqfts = [p["sqft"] for p in all_properties]
    conditions = [p.get("condition_score", 50.0) for p in all_properties]
    hoa_risks = [p.get("hoa_risk", 5) for p in all_properties]
    hazards = [p.get("hazard_score", 5) for p in all_properties]
    stabilities = [p.get("stability_score", 50.0) for p in all_properties]

    # --- Dimension scores (all 0-100, higher is better) ---

    financial_score = _normalize_score(
        property_data["monthly_payment"], payments, lower_is_better=True,
    )
    value_score = _normalize_score(
        property_data["price_per_sqft"], ppsfs, lower_is_better=True,
    )
    size_score = _normalize_score(
        property_data["sqft"], sqfts, lower_is_better=False,
    )

    # Condition is already 0-100 (higher=better) — normalize within group.
    condition_score = _normalize_score(
        property_data.get("condition_score", 50.0), conditions, lower_is_better=False,
    )

    # HOA risk is 1-10 (lower=better) — normalize.
    hoa_risk_score = _normalize_score(
        float(property_data.get("hoa_risk", 5)), [float(x) for x in hoa_risks],
        lower_is_better=True,
    )

    # Hazard is 1-10 (lower=better) — normalize.
    hazard_score = _normalize_score(
        float(property_data.get("hazard_score", 5)), [float(x) for x in hazards],
        lower_is_better=True,
    )

    # Stability is 0-100 (higher=better) — normalize within group.
    surrounding_stability_score = _normalize_score(
        property_data.get("stability_score", 50.0), stabilities, lower_is_better=False,
    )

    scores = {
        "financial": financial_score,
        "value": value_score,
        "size": size_score,
        "condition": condition_score,
        "hoa": hoa_risk_score,
        "hazard": hazard_score,
        "surrounding": surrounding_stability_score,
    }

    return {
        "address": property_data.get("address", ""),
        "scores": scores,
        "monthly_payment": property_data["monthly_payment"],
        "price_per_sqft": property_data["price_per_sqft"],
    }


def _generate_pros_cons(
    scored: dict[str, Any],
    all_scored: list[dict[str, Any]],
    raw: dict[str, Any],
    all_raw: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Generate human-readable pros/cons for a property."""
    pros: list[str] = []
    cons: list[str] = []

    payments = [s["monthly_payment"] for s in all_scored]
    ppsfs = [s["price_per_sqft"] for s in all_scored]
    sqfts = [r["sqft"] for r in all_raw]

    if scored["monthly_payment"] == min(payments):
        pros.append("Lowest monthly payment")
    if scored["monthly_payment"] == max(payments):
        cons.append("Highest monthly payment")

    if scored["price_per_sqft"] == min(ppsfs):
        pros.append("Lowest price per sqft")
    if scored["price_per_sqft"] == max(ppsfs):
        cons.append("Highest price per sqft")

    if raw["sqft"] == max(sqfts):
        pros.append("Largest living area")
    if raw["sqft"] == min(sqfts):
        cons.append("Smallest living area")

    conditions = [r.get("condition_score", 50.0) for r in all_raw]
    if raw.get("condition_score", 50.0) == max(conditions) and max(conditions) != min(conditions):
        pros.append("Best property condition")
    if raw.get("condition_score", 50.0) == min(conditions) and max(conditions) != min(conditions):
        cons.append("Most deferred maintenance")

    hoa_risks = [r.get("hoa_risk", 5) for r in all_raw]
    if raw.get("hoa_risk", 5) == min(hoa_risks) and max(hoa_risks) != min(hoa_risks):
        pros.append("Lowest HOA risk")
    if raw.get("hoa_risk", 5) == max(hoa_risks) and max(hoa_risks) != min(hoa_risks):
        cons.append("Highest HOA risk")

    hazards = [r.get("hazard_score", 5) for r in all_raw]
    if raw.get("hazard_score", 5) == min(hazards) and max(hazards) != min(hazards):
        pros.append("Lowest natural hazard risk")
    if raw.get("hazard_score", 5) == max(hazards) and max(hazards) != min(hazards):
        cons.append("Highest natural hazard risk")

    stabilities = [r.get("stability_score", 50.0) for r in all_raw]
    if raw.get("stability_score", 50.0) == max(stabilities) and max(stabilities) != min(stabilities):
        pros.append("Most stable surrounding neighborhood")
    if raw.get("stability_score", 50.0) == min(stabilities) and max(stabilities) != min(stabilities):
        cons.append("Least stable surrounding neighborhood")

    hoa_monthly = raw.get("hoa_monthly", 0.0)
    if hoa_monthly == 0.0:
        pros.append("No HOA fees")
    else:
        all_hoas = [r.get("hoa_monthly", 0.0) for r in all_raw]
        if hoa_monthly == max(all_hoas) and max(all_hoas) != min(all_hoas):
            cons.append("Highest HOA fees")

    return pros, cons


def compare_properties(
    properties: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Score and rank properties relative to one another.

    Parameters
    ----------
    properties:
        List of property dicts, each with the keys described in
        :func:`score_property`.
    weights:
        Optional weight overrides.  Keys should be a subset of
        ``"financial"``, ``"value"``, ``"size"``, ``"condition"``,
        ``"hoa"``, ``"hazard"``, ``"surrounding"``.  Values should
        sum to 1.0.  Missing keys fall back to ``DEFAULT_WEIGHTS``.

    Returns
    -------
    List of scored-property dicts, sorted best-to-worst by total_score.
    Each dict contains:
    - ``"address"`` (str)
    - ``"scores"`` (dict[str, float]): per-dimension 0-100 scores
    - ``"total_score"`` (float): weighted average
    - ``"rank"`` (int): 1-based rank
    - ``"monthly_payment"`` (float)
    - ``"price_per_sqft"`` (float)
    - ``"pros"`` (list[str])
    - ``"cons"`` (list[str])
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Merge with defaults so callers can pass a partial dict.
    effective_weights = {**DEFAULT_WEIGHTS, **weights}

    # Normalise weights to sum to 1.0.
    w_sum = sum(effective_weights.values())
    if w_sum > 0:
        effective_weights = {k: v / w_sum for k, v in effective_weights.items()}

    # --- Step 1: Score each property against the group ---
    scored_properties: list[dict[str, Any]] = []
    for prop in properties:
        scored = score_property(prop, properties)

        # Weighted total
        total = sum(
            effective_weights.get(dim, 0.0) * score
            for dim, score in scored["scores"].items()
        )
        scored["total_score"] = round(total, 2)
        scored_properties.append(scored)

    # --- Step 2: Generate pros/cons ---
    for scored, raw in zip(scored_properties, properties):
        pros, cons = _generate_pros_cons(scored, scored_properties, raw, properties)
        scored["pros"] = pros
        scored["cons"] = cons

    # --- Step 3: Rank ---
    scored_properties.sort(key=lambda s: s["total_score"], reverse=True)
    for i, sp in enumerate(scored_properties, start=1):
        sp["rank"] = i

    return scored_properties
