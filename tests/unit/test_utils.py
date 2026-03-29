"""Tests for utility functions."""

from pipa.utils.formatters import format_currency, format_number, format_percentage
from pipa.utils.geo import (
    detect_county,
    get_county_fips,
    get_full_fips,
    get_state_fips,
    normalize_address,
    parse_address,
    validate_state,
)


def test_format_currency():
    assert format_currency(1234.56) == "$1,234.56"
    assert format_currency(-500) == "-$500.00"
    assert format_currency(0) == "$0.00"


def test_format_percentage():
    assert format_percentage(0.1234) == "12.34%"
    assert format_percentage(0.5, decimals=0) == "50%"


def test_format_number():
    assert format_number(1234) == "1,234"
    assert format_number(1234.5, decimals=2) == "1,234.50"


def test_parse_address():
    result = parse_address("123 Main St, Fairfax, VA 22030")
    assert result["street"] == "123 Main St"
    assert result["city"] == "Fairfax"
    assert result["state"] == "VA"
    assert result["zip_code"] == "22030"


def test_parse_address_missing_parts():
    result = parse_address("123 Main St")
    assert result["street"] == "123 Main St"
    assert result["city"] == ""


def test_validate_state():
    assert validate_state("VA") is True
    assert validate_state("va") is True
    assert validate_state("XX") is False


def test_get_state_fips():
    assert get_state_fips("VA") == "51"
    assert get_state_fips("XX") is None


def test_get_county_fips():
    assert get_county_fips("fairfax") == "059"
    assert get_county_fips("loudoun") == "107"
    assert get_county_fips("unknown") is None


def test_get_full_fips():
    assert get_full_fips("fairfax") == "51059"
    assert get_full_fips("loudoun") == "51107"


def test_normalize_address():
    assert normalize_address("  123  Main  St  ") == "123 MAIN ST"


def test_detect_county():
    assert detect_county("Fairfax", "VA") == "fairfax"
    assert detect_county("Ashburn", "VA") == "loudoun"
    assert detect_county("Reston", "VA") == "fairfax"
    assert detect_county("Leesburg", "VA") == "loudoun"
    assert detect_county("Richmond", "VA") is None
    assert detect_county("Fairfax", "MD") is None
