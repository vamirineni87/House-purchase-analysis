"""Virginia county/city property tax rates.

Rates are expressed as dollars per $100 of assessed value, which is
the standard format used by Virginia localities. To compute annual tax:

    annual_tax = (assessed_value / 100) * rate

Sources:
- Individual county/city Treasurer websites
- Virginia JLARC local tax rates report
- Updated annually (rates shown are for the most recent available tax year)

Note: Some localities have different rates for different property types
(residential vs. commercial). The rates below are for residential real
property unless noted.
"""

from __future__ import annotations

# Property tax rates per $100 of assessed value
# Format: "Locality Name" -> rate
VA_TAX_RATES: dict[str, float] = {
    # Northern Virginia counties
    "Fairfax County": 1.11,
    "Fairfax": 1.11,
    "Loudoun County": 0.87,
    "Loudoun": 0.87,
    "Arlington County": 1.013,
    "Arlington": 1.013,
    "Prince William County": 0.978,
    "Prince William": 0.978,
    "Fauquier County": 0.992,
    "Fauquier": 0.992,
    "Stafford County": 1.02,
    "Stafford": 1.02,
    "Spotsylvania County": 0.86,
    "Spotsylvania": 0.86,
    "Clarke County": 0.56,
    "Clarke": 0.56,
    "Warren County": 0.67,
    "Warren": 0.67,
    "Frederick County": 0.585,
    "Frederick": 0.585,
    "Culpeper County": 0.71,
    "Culpeper": 0.71,
    # Northern Virginia independent cities
    "City of Alexandria": 1.11,
    "Alexandria": 1.11,
    "City of Falls Church": 1.355,
    "Falls Church": 1.355,
    "City of Fairfax": 1.075,
    "City of Manassas": 1.204,
    "Manassas": 1.204,
    "City of Manassas Park": 1.325,
    "Manassas Park": 1.325,
    "City of Winchester": 0.86,
    "Winchester": 0.86,
    # Richmond area
    "Henrico County": 0.87,
    "Henrico": 0.87,
    "Chesterfield County": 0.96,
    "Chesterfield": 0.96,
    "City of Richmond": 1.20,
    "Richmond": 1.20,
    "Hanover County": 0.81,
    "Hanover": 0.81,
    "Goochland County": 0.53,
    "Goochland": 0.53,
    "Powhatan County": 0.83,
    "Powhatan": 0.83,
    # Hampton Roads / Tidewater
    "City of Virginia Beach": 0.99,
    "Virginia Beach": 0.99,
    "City of Norfolk": 1.25,
    "Norfolk": 1.25,
    "City of Chesapeake": 1.05,
    "Chesapeake": 1.05,
    "City of Newport News": 1.22,
    "Newport News": 1.22,
    "City of Hampton": 1.24,
    "Hampton": 1.24,
    "City of Suffolk": 1.09,
    "Suffolk": 1.09,
    "James City County": 0.84,
    "James City": 0.84,
    "York County": 0.74,
    "York": 0.74,
    "City of Williamsburg": 0.55,
    "Williamsburg": 0.55,
    "Isle of Wight County": 0.83,
    "Isle of Wight": 0.83,
    # Central Virginia
    "Albemarle County": 0.854,
    "Albemarle": 0.854,
    "City of Charlottesville": 0.96,
    "Charlottesville": 0.96,
    "Orange County": 0.70,
    "Orange": 0.70,
}


def get_tax_rate(locality: str) -> float | None:
    """Look up the property tax rate for a Virginia locality.

    Args:
        locality: Locality name (county, city, or town).

    Returns:
        Tax rate per $100 of assessed value, or ``None`` if not found.
    """
    # Try exact match first
    rate = VA_TAX_RATES.get(locality)
    if rate is not None:
        return rate

    # Try common variations
    for suffix in [" County", ""]:
        candidate = locality.replace(" County", "").replace("City of ", "") + suffix
        rate = VA_TAX_RATES.get(candidate)
        if rate is not None:
            return rate

    # Case-insensitive fallback
    locality_lower = locality.lower()
    for key, rate in VA_TAX_RATES.items():
        if key.lower() == locality_lower:
            return rate

    return None


def compute_annual_tax(assessed_value: float, locality: str) -> float | None:
    """Compute the annual property tax for a given assessed value and locality.

    Args:
        assessed_value: Total assessed value of the property in dollars.
        locality: Virginia locality name.

    Returns:
        Annual property tax in dollars, or ``None`` if the rate is unknown.
    """
    rate = get_tax_rate(locality)
    if rate is None:
        return None
    return (assessed_value / 100.0) * rate
