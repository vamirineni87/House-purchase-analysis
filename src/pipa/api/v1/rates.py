"""Rate lookup endpoints — mortgage rates and county tax rates."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pipa.schemas.rates import CountyTaxRate, MortgageRates

router = APIRouter(tags=["rates"])

# Static default rates (would be replaced by FRED API / live feed)
_DEFAULT_RATES = MortgageRates(
    rate_30yr=0.065,
    rate_15yr=0.059,
    source="default",
    as_of="2024-01-01",
)

# Virginia county tax rates (per $100 of assessed value, converted to decimal)
_COUNTY_TAX_RATES: dict[str, CountyTaxRate] = {
    "fairfax": CountyTaxRate(
        county="fairfax",
        property_tax_rate=0.0111,
        vehicle_tax_rate=0.0457,
        stormwater_fee=0.0325,
        source="fairfax_county_fy2025",
    ),
    "loudoun": CountyTaxRate(
        county="loudoun",
        property_tax_rate=0.00875,
        vehicle_tax_rate=0.04,
        stormwater_fee=0.0,
        source="loudoun_county_fy2025",
    ),
    "arlington": CountyTaxRate(
        county="arlington",
        property_tax_rate=0.01013,
        vehicle_tax_rate=0.05,
        stormwater_fee=0.0,
        source="arlington_county_fy2025",
    ),
    "prince_william": CountyTaxRate(
        county="prince_william",
        property_tax_rate=0.0092,
        vehicle_tax_rate=0.036,
        stormwater_fee=0.0,
        source="prince_william_county_fy2025",
    ),
}


@router.get("/rates/mortgage", response_model=MortgageRates)
async def get_mortgage_rates():
    """Get current default mortgage rates.

    In production, these would come from the FRED API or a
    rate aggregation service.
    """
    return _DEFAULT_RATES


@router.get("/rates/tax/{county}", response_model=CountyTaxRate)
async def get_county_tax_rate(county: str):
    """Get tax rate information for a Virginia county."""
    key = county.strip().lower().replace(" ", "_")
    rate = _COUNTY_TAX_RATES.get(key)
    if rate is None:
        available = ", ".join(sorted(_COUNTY_TAX_RATES.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"County '{county}' not found. Available: {available}",
        )
    return rate
