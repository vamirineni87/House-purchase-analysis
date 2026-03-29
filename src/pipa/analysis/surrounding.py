"""Surrounding-properties / neighborhood stability analysis — pure functions.

Analyzes investor concentration, turnover rates, and neighborhood
stability signals from nearby property records and sales data.
"""

from __future__ import annotations

from datetime import datetime


def calculate_investor_share(
    nearby_properties: list[dict],
) -> float:
    """Calculate the percentage of nearby properties owned by investors.

    Parameters
    ----------
    nearby_properties:
        List of dicts, each with at least an ``"owner_occupied"`` (bool)
        key.  Properties where ``owner_occupied`` is *False* are counted
        as investor-owned.

    Returns
    -------
    Investor share as a float between 0.0 and 1.0.
    """
    if not nearby_properties:
        return 0.0

    investor_count = sum(
        1 for p in nearby_properties if not p.get("owner_occupied", True)
    )
    return round(investor_count / len(nearby_properties), 4)


def calculate_turnover_rate(
    nearby_sales: list[dict],
    total_properties: int | None = None,
    years: int = 5,
) -> float:
    """Calculate the annual property turnover rate for the area.

    Parameters
    ----------
    nearby_sales:
        List of dicts with at least ``"sale_date"`` (str ISO date or
        ``datetime``) key.  All sales within the lookback period are
        counted.
    total_properties:
        Total number of properties in the comparison set.  If not
        provided, the number of unique addresses in *nearby_sales* is
        used as a rough proxy.
    years:
        Lookback window in years.

    Returns
    -------
    Annual turnover rate as a float (e.g. 0.08 means 8 % per year).
    """
    if not nearby_sales:
        return 0.0

    now = datetime.now()
    cutoff = datetime(now.year - years, now.month, now.day)

    count = 0
    for sale in nearby_sales:
        sd = sale.get("sale_date")
        if sd is None:
            continue
        if isinstance(sd, str):
            try:
                sd = datetime.fromisoformat(sd)
            except ValueError:
                continue
        if sd >= cutoff:
            count += 1

    if total_properties is None:
        addresses = {
            s.get("address", s.get("parcel_id", id(s)))
            for s in nearby_sales
        }
        total_properties = max(len(addresses), 1)

    if total_properties <= 0 or years <= 0:
        return 0.0

    annual_rate = count / (total_properties * years)
    return round(annual_rate, 4)


def _count_flips(
    nearby_sales: list[dict],
    flip_window_months: int = 18,
) -> int:
    """Count properties that sold twice within *flip_window_months*.

    A "flip" is defined as the same address selling again within the
    window, which often signals speculative activity.
    """
    from collections import defaultdict

    by_address: dict[str, list[datetime]] = defaultdict(list)

    for sale in nearby_sales:
        addr = sale.get("address", sale.get("parcel_id"))
        if addr is None:
            continue
        sd = sale.get("sale_date")
        if sd is None:
            continue
        if isinstance(sd, str):
            try:
                sd = datetime.fromisoformat(sd)
            except ValueError:
                continue
        by_address[str(addr)].append(sd)

    flip_count = 0
    for addr, dates in by_address.items():
        if len(dates) < 2:
            continue
        dates.sort()
        for i in range(1, len(dates)):
            delta_months = (dates[i] - dates[i - 1]).days / 30.44
            if delta_months <= flip_window_months:
                flip_count += 1

    return flip_count


def score_neighborhood_stability(
    investor_share: float,
    turnover_rate: float,
    flip_count: int,
) -> float:
    """Score neighborhood stability from 0 (unstable) to 100 (very stable).

    Three equally-weighted components (each 0-33.3):
    1. Low investor share is good (< 10 % ideal, > 40 % worst)
    2. Low turnover is good (< 6 % ideal, > 15 % worst)
    3. Low flip activity is good (0 ideal, 5+ worst)
    """
    # Investor share component (33.3 points max)
    if investor_share <= 0.10:
        inv_score = 33.3
    elif investor_share >= 0.40:
        inv_score = 0.0
    else:
        inv_score = 33.3 * (1 - (investor_share - 0.10) / 0.30)

    # Turnover component (33.3 points max)
    if turnover_rate <= 0.06:
        turn_score = 33.3
    elif turnover_rate >= 0.15:
        turn_score = 0.0
    else:
        turn_score = 33.3 * (1 - (turnover_rate - 0.06) / 0.09)

    # Flip component (33.4 points max)
    if flip_count <= 0:
        flip_score = 33.4
    elif flip_count >= 5:
        flip_score = 0.0
    else:
        flip_score = 33.4 * (1 - flip_count / 5)

    total = inv_score + turn_score + flip_score
    return round(max(0.0, min(100.0, total)), 1)


def analyze_surrounding(
    nearby_properties: list[dict],
    nearby_sales: list[dict],
    total_properties: int | None = None,
    turnover_years: int = 5,
    flip_window_months: int = 18,
) -> dict:
    """Run full surrounding-property analysis.

    Parameters
    ----------
    nearby_properties:
        List of dicts with ``"owner_occupied"`` bool key.
    nearby_sales:
        List of dicts with ``"sale_date"`` and ``"address"``/``"parcel_id"``.
    total_properties:
        Total properties in the comparison set.
    turnover_years:
        Lookback for turnover calculation.
    flip_window_months:
        Window to detect flips.

    Returns
    -------
    dict with ``investor_share``, ``turnover_rate``, ``flip_count``,
    ``stability_score``, and ``total_nearby``.
    """
    investor_share = calculate_investor_share(nearby_properties)
    turnover_rate = calculate_turnover_rate(
        nearby_sales,
        total_properties=total_properties or len(nearby_properties) or None,
        years=turnover_years,
    )
    flip_count = _count_flips(nearby_sales, flip_window_months)
    stability = score_neighborhood_stability(investor_share, turnover_rate, flip_count)

    return {
        "investor_share": investor_share,
        "turnover_rate": turnover_rate,
        "flip_count": flip_count,
        "stability_score": stability,
        "total_nearby": len(nearby_properties),
    }
