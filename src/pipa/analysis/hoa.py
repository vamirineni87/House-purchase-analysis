"""HOA / community association analysis — pure functions, no I/O.

Analyzes HOA fee trends, reserve health, risk scoring, and
resale friction from association rules.
"""

from __future__ import annotations

import math


def analyze_fee_trend(
    fee_history: list[dict],
) -> dict:
    """Analyze the historical trend of HOA fees.

    Parameters
    ----------
    fee_history:
        List of dicts with ``"year"`` (int) and ``"monthly_fee"`` (float),
        sorted oldest-first.

    Returns
    -------
    dict with:
    - ``annual_increase_rate``: average annual % increase
    - ``projected_5yr_fee``: projected monthly fee in 5 years
    - ``total_increase_pct``: total % increase over the history
    - ``years_of_data``: span of years covered
    """
    if len(fee_history) < 2:
        current = fee_history[0]["monthly_fee"] if fee_history else 0.0
        return {
            "annual_increase_rate": 0.0,
            "projected_5yr_fee": current,
            "total_increase_pct": 0.0,
            "years_of_data": len(fee_history),
        }

    first = fee_history[0]
    last = fee_history[-1]
    years_span = last["year"] - first["year"]

    if years_span <= 0 or first["monthly_fee"] <= 0:
        return {
            "annual_increase_rate": 0.0,
            "projected_5yr_fee": last["monthly_fee"],
            "total_increase_pct": 0.0,
            "years_of_data": 0,
        }

    total_increase_pct = (last["monthly_fee"] - first["monthly_fee"]) / first["monthly_fee"]

    # Compound annual growth rate
    cagr = (last["monthly_fee"] / first["monthly_fee"]) ** (1.0 / years_span) - 1.0

    projected_5yr = round(last["monthly_fee"] * (1 + cagr) ** 5, 2)

    return {
        "annual_increase_rate": round(cagr, 4),
        "projected_5yr_fee": projected_5yr,
        "total_increase_pct": round(total_increase_pct, 4),
        "years_of_data": years_span,
    }


def score_reserve_health(
    reserve_balance: float,
    annual_expenses: float,
) -> float:
    """Score HOA reserve fund health from 0 (critical) to 100 (excellent).

    The industry benchmark is reserves covering 25-50 % of replacement
    cost, but a simpler proxy is the reserves-to-annual-expenses ratio.

    - >= 100 % of annual expenses -> 100
    - 50-99 %  -> 50-99
    - 25-49 %  -> 25-49
    - < 25 %   -> pro-rated below 25
    """
    if annual_expenses <= 0:
        return 100.0 if reserve_balance > 0 else 0.0

    ratio = reserve_balance / annual_expenses
    score = min(100.0, ratio * 100.0)
    return round(max(0.0, score), 1)


def score_hoa_risk(
    fee_trend: dict,
    reserve_health: float,
    special_assessments: list[dict] | None = None,
    litigation_flags: list[str] | None = None,
) -> int:
    """Score overall HOA risk from 1 (lowest risk) to 10 (highest risk).

    Parameters
    ----------
    fee_trend:
        Output of :func:`analyze_fee_trend`.
    reserve_health:
        Output of :func:`score_reserve_health` (0-100).
    special_assessments:
        List of dicts with ``"year"`` and ``"amount"``, if any.
    litigation_flags:
        List of active or recent litigation descriptions.

    Returns
    -------
    int from 1 (safe) to 10 (avoid).
    """
    if special_assessments is None:
        special_assessments = []
    if litigation_flags is None:
        litigation_flags = []

    risk = 1.0  # start at lowest risk

    # Fee trend contribution (0-3 points)
    annual_rate = fee_trend.get("annual_increase_rate", 0.0)
    if annual_rate > 0.10:
        risk += 3.0
    elif annual_rate > 0.06:
        risk += 2.0
    elif annual_rate > 0.03:
        risk += 1.0

    # Reserve health contribution (0-3 points)
    if reserve_health < 25:
        risk += 3.0
    elif reserve_health < 50:
        risk += 2.0
    elif reserve_health < 75:
        risk += 1.0

    # Special assessments (0-2 points)
    recent = [sa for sa in special_assessments if sa.get("amount", 0) > 0]
    if len(recent) >= 2:
        risk += 2.0
    elif len(recent) == 1:
        risk += 1.0

    # Litigation (0-2 points)
    if len(litigation_flags) >= 2:
        risk += 2.0
    elif len(litigation_flags) == 1:
        risk += 1.0

    return min(10, max(1, int(round(risk))))


def analyze_resale_friction(
    rules: dict,
) -> dict:
    """Analyze HOA rules that may impede future resale.

    Parameters
    ----------
    rules:
        Dict with boolean or descriptive keys such as:
        - ``"rental_restriction"`` (bool): prohibits or limits rentals
        - ``"rental_cap_pct"`` (float | None): max % of units rented
        - ``"pet_restriction"`` (bool): breed/weight/count limits
        - ``"age_restriction"`` (bool): 55+ community
        - ``"exterior_modification_approval"`` (bool): board approval needed
        - ``"lease_term_minimum_months"`` (int | None): minimum lease term

    Returns
    -------
    dict with:
    - ``rental_restriction``: bool
    - ``pet_restriction``: bool
    - ``age_restriction``: bool
    - ``friction_score``: float 0-100 (higher = harder to resell)
    """
    rental = bool(rules.get("rental_restriction", False))
    pet = bool(rules.get("pet_restriction", False))
    age = bool(rules.get("age_restriction", False))
    exterior = bool(rules.get("exterior_modification_approval", False))

    friction = 0.0

    # Rental restrictions are the biggest resale friction — they reduce
    # the buyer pool by excluding investors.
    if rental:
        friction += 35.0
        rental_cap = rules.get("rental_cap_pct")
        if rental_cap is not None and rental_cap < 0.10:
            friction += 10.0  # very tight cap

    if pet:
        friction += 15.0

    if age:
        friction += 25.0

    if exterior:
        friction += 5.0

    lease_min = rules.get("lease_term_minimum_months")
    if lease_min is not None and lease_min > 6:
        friction += 10.0

    friction = min(100.0, friction)

    return {
        "rental_restriction": rental,
        "pet_restriction": pet,
        "age_restriction": age,
        "friction_score": round(friction, 1),
    }
