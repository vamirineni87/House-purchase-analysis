"""Geocoding helpers, FIPS code utilities, and address parsing.

Provides state-to-FIPS mappings, county FIPS codes for target counties,
and basic address parsing without external API calls.
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

# Virginia county FIPS codes (3-digit) for target counties.
# Full FIPS = state (51) + county code.
VA_COUNTY_FIPS: dict[str, str] = {
    "fairfax": "059",       # Fairfax County
    "fairfax_city": "600",  # Fairfax City (independent city)
    "loudoun": "107",       # Loudoun County
    "arlington": "013",
    "prince_william": "153",
    "fauquier": "061",
    "clarke": "043",
}


def get_state_fips(state_abbr: str) -> Optional[str]:
    """Return the two-digit FIPS code for a US state abbreviation."""
    return STATE_FIPS.get(state_abbr.strip().upper())


def fips_to_state(fips_code: str) -> Optional[str]:
    """Return the state abbreviation for a two-digit FIPS code."""
    return FIPS_STATE.get(fips_code.strip().zfill(2))


def get_county_fips(county_name: str) -> Optional[str]:
    """Return the 3-digit county FIPS code for a Virginia county name."""
    return VA_COUNTY_FIPS.get(county_name.strip().lower())


def get_full_fips(county_name: str) -> Optional[str]:
    """Return the full 5-digit FIPS code (state + county) for a Virginia county."""
    county_fips = get_county_fips(county_name)
    if county_fips:
        return f"51{county_fips}"
    return None


def parse_address(address_str: str) -> dict[str, str]:
    """Parse a comma-separated address string.

    Expects: "123 Main St, City, ST 12345"
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
    """Return True if state_abbr is a recognized US state/DC code."""
    return state_abbr.strip().upper() in STATE_FIPS


def normalize_address(address_str: str) -> str:
    """Normalize an address for deduplication: uppercase, trim, collapse whitespace."""
    return " ".join(address_str.upper().strip().split())


def detect_county(city: str, state: str, zip_code: str = "") -> Optional[str]:
    """Detect county from city/zip for Virginia addresses.

    ZIP code takes priority over city name because some cities
    straddle county lines (e.g., Chantilly spans Fairfax and Loudoun).
    """
    if state.upper() != "VA":
        return None

    # ZIP code is the most reliable indicator for border cities
    zip_clean = zip_code.strip()[:5]
    loudoun_zips = {
        "20105", "20117", "20118", "20129", "20132", "20134", "20135",
        "20141", "20142", "20143", "20144", "20146", "20147", "20148",
        "20149", "20151", "20152", "20158", "20159", "20160", "20163",
        "20164", "20165", "20166", "20167", "20175", "20176", "20177",
        "20178", "20180", "20189", "20197",
    }
    fairfax_zips = {
        "22003", "22009", "22015", "22027", "22030", "22031", "22032",
        "22033", "22034", "22035", "22036", "22037", "22038", "22039",
        "22041", "22042", "22043", "22044", "22046", "22060", "22066",
        "22079", "22101", "22102", "22103", "22121", "22122", "22124",
        "22150", "22151", "22152", "22153", "22180", "22181", "22182",
        "22183", "22185", "22199",
    }

    if zip_clean in loudoun_zips:
        return "loudoun"
    if zip_clean in fairfax_zips:
        return "fairfax"

    # Fall back to city name for cities that don't straddle
    city_lower = city.strip().lower()

    fairfax_only_cities = {
        "fairfax", "falls church", "vienna", "annandale", "burke",
        "clifton", "dunn loring", "great falls",
        "lorton", "mclean", "merrifield", "mount vernon",
        "oakton", "springfield", "tysons", "tysons corner",
    }
    loudoun_only_cities = {
        "leesburg", "ashburn", "purcellville", "lovettsville",
        "middleburg", "round hill", "hamilton", "hillsboro", "aldie",
        "brambleton", "broadlands", "south riding", "stone ridge",
        "lansdowne",
    }
    # Cities that straddle — need ZIP to resolve
    # "chantilly": 20151/20152 = Loudoun, 20151 can be either
    # "centreville": 20120/20121 = Fairfax, 20124 = Fairfax
    # "herndon": 20170/20171 = Fairfax, but some parts near Loudoun
    # "reston": 20190/20191/20194 = Fairfax
    # "sterling": 20164/20165/20166 = Loudoun
    # "dulles": 20166 = Loudoun

    if city_lower in fairfax_only_cities:
        return "fairfax"
    if city_lower in loudoun_only_cities:
        return "loudoun"

    # Border cities without ZIP — best guess
    border_defaults = {
        "chantilly": "loudoun",  # More Chantilly addresses are Loudoun-side
        "centreville": "fairfax",
        "herndon": "fairfax",
        "reston": "fairfax",
        "sterling": "loudoun",
        "dulles": "loudoun",
    }
    if city_lower in border_defaults:
        return border_defaults[city_lower]

    return None
