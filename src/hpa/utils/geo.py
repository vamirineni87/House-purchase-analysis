"""Geocoding helpers and FIPS code utilities.

Provides state-to-FIPS mappings and basic address parsing without
requiring any external API calls.
"""

from __future__ import annotations

from typing import Optional

# State abbreviation to two-digit FIPS code mapping (50 states + DC).
STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}

# Reverse mapping: FIPS code -> state abbreviation.
FIPS_STATE: dict[str, str] = {v: k for k, v in STATE_FIPS.items()}


def get_state_fips(state_abbr: str) -> Optional[str]:
    """Return the two-digit FIPS code for a US state abbreviation.

    Parameters
    ----------
    state_abbr:
        Two-letter state abbreviation (case-insensitive).

    Returns
    -------
    str or None
        The FIPS code string, or ``None`` if the abbreviation is unknown.
    """
    return STATE_FIPS.get(state_abbr.strip().upper())


def fips_to_state(fips_code: str) -> Optional[str]:
    """Return the state abbreviation for a two-digit FIPS code.

    Parameters
    ----------
    fips_code:
        Two-digit FIPS code (e.g. ``"48"`` for Texas).

    Returns
    -------
    str or None
        The state abbreviation, or ``None`` if the code is unknown.
    """
    return FIPS_STATE.get(fips_code.strip().zfill(2))


def parse_address(address_str: str) -> dict[str, str]:
    """Parse a simple comma-separated address string.

    Expects a format like ``"123 Main St, Austin, TX 78701"``.

    Parameters
    ----------
    address_str:
        Raw address string with comma-separated components.

    Returns
    -------
    dict
        Dictionary with keys ``street``, ``city``, ``state``, and
        ``zip_code``.  Missing components are returned as empty strings.
    """
    parts = [p.strip() for p in address_str.split(",")]
    result: dict[str, str] = {
        "street": "",
        "city": "",
        "state": "",
        "zip_code": "",
    }

    if len(parts) >= 1:
        result["street"] = parts[0]
    if len(parts) >= 2:
        result["city"] = parts[1]
    if len(parts) >= 3:
        state_zip = parts[2].strip().split()
        if len(state_zip) >= 1:
            result["state"] = state_zip[0].upper()
        if len(state_zip) >= 2:
            result["zip_code"] = state_zip[1]

    return result


def validate_state(state_abbr: str) -> bool:
    """Return ``True`` if *state_abbr* is a recognized US state/DC code."""
    return state_abbr.strip().upper() in STATE_FIPS
