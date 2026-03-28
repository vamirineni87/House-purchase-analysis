"""Property-related Pydantic v2 models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Address(BaseModel):
    """Physical address of a property."""

    street: str
    city: str
    state: str
    zip_code: str
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PropertyDetails(BaseModel):
    """Detailed information about a property listing."""

    address: Address
    list_price: float
    bedrooms: int
    bathrooms: float
    square_feet: int
    lot_size_sqft: Optional[int] = None
    year_built: Optional[int] = None
    property_type: str = "single_family"
    hoa_monthly: float = 0.0
    garage_spaces: int = 0
    stories: int = 1
    description: Optional[str] = None
    mls_number: Optional[str] = None
    days_on_market: Optional[int] = None
