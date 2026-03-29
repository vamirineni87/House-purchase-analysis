"""EPA radon zone data for Virginia counties.

Zone definitions (EPA Map of Radon Zones):
- Zone 1: Highest potential (predicted avg indoor screening level >= 4 pCi/L)
- Zone 2: Moderate potential (predicted avg 2-4 pCi/L)
- Zone 3: Low potential (predicted avg < 2 pCi/L)

Source: https://www.epa.gov/radon/epa-map-radon-zones
Virginia data: https://www.epa.gov/radon/epa-map-radon-zones-virginia

This is static reference data that rarely changes.
"""

from __future__ import annotations

# Virginia county radon zones
# Zone 1 = high, Zone 2 = moderate, Zone 3 = low
VA_RADON_ZONES: dict[str, int] = {
    # Northern Virginia counties (primary focus)
    "Fairfax": 2,
    "Fairfax County": 2,
    "Fairfax City": 2,
    "Loudoun": 2,
    "Loudoun County": 2,
    "Arlington": 2,
    "Arlington County": 2,
    "Prince William": 2,
    "Prince William County": 2,
    "Fauquier": 1,
    "Fauquier County": 1,
    "Stafford": 2,
    "Stafford County": 2,
    "Spotsylvania": 2,
    "Spotsylvania County": 2,
    "Clarke": 1,
    "Clarke County": 1,
    "Warren": 1,
    "Warren County": 1,
    "Frederick": 1,
    "Frederick County": 1,
    # Independent cities in NoVA
    "Alexandria": 2,
    "City of Alexandria": 2,
    "Falls Church": 2,
    "City of Falls Church": 2,
    "Manassas": 2,
    "City of Manassas": 2,
    "Manassas Park": 2,
    "City of Manassas Park": 2,
    "Winchester": 1,
    "City of Winchester": 1,
    "Leesburg": 2,
    # Central Virginia
    "Albemarle": 1,
    "Albemarle County": 1,
    "Charlottesville": 1,
    "City of Charlottesville": 1,
    "Orange": 1,
    "Orange County": 1,
    "Culpeper": 1,
    "Culpeper County": 1,
    "Madison": 1,
    "Madison County": 1,
    "Rappahannock": 1,
    "Rappahannock County": 1,
    # Hampton Roads / Tidewater
    "Virginia Beach": 3,
    "City of Virginia Beach": 3,
    "Norfolk": 3,
    "City of Norfolk": 3,
    "Chesapeake": 3,
    "City of Chesapeake": 3,
    "Newport News": 3,
    "City of Newport News": 3,
    "Hampton": 3,
    "City of Hampton": 3,
    "Suffolk": 3,
    "City of Suffolk": 3,
    "James City": 3,
    "James City County": 3,
    "York": 3,
    "York County": 3,
    # Richmond area
    "Henrico": 2,
    "Henrico County": 2,
    "Chesterfield": 2,
    "Chesterfield County": 2,
    "Richmond": 2,
    "City of Richmond": 2,
    "Hanover": 2,
    "Hanover County": 2,
}


def get_radon_zone(county: str, state: str = "VA") -> int | None:
    """Look up the EPA radon zone for a county.

    Args:
        county: County name (with or without 'County' suffix).
        state: State abbreviation (only ``"VA"`` supported currently).

    Returns:
        Zone number (1, 2, or 3), or ``None`` if not found.
    """
    if state.upper() != "VA":
        return None

    # Try exact match first, then common variations
    for candidate in [county, f"{county} County", county.replace(" County", "")]:
        zone = VA_RADON_ZONES.get(candidate)
        if zone is not None:
            return zone

    # Case-insensitive fallback
    county_lower = county.lower()
    for key, zone in VA_RADON_ZONES.items():
        if key.lower() == county_lower:
            return zone

    return None
