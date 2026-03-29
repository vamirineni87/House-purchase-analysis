"""Static reference data for property analysis."""

from .epa_radon_zones import VA_RADON_ZONES, get_radon_zone
from .fema_nri import load_nri_for_county
from .va_tax_rates import VA_TAX_RATES, compute_annual_tax, get_tax_rate

__all__ = [
    "VA_RADON_ZONES",
    "VA_TAX_RATES",
    "compute_annual_tax",
    "get_radon_zone",
    "get_tax_rate",
    "load_nri_for_county",
]
