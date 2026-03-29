"""Pydantic v2 schemas for property API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AddressCreate(BaseModel):
    """Schema for creating an address."""

    street: str
    city: str
    state: str = "VA"
    zip_code: str = ""
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AddressResponse(BaseModel):
    """Schema for address in API responses."""

    id: str
    address_type: str
    normalized_address: str
    raw_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_current: bool = True

    model_config = {"from_attributes": True}


class ParcelIdentifierResponse(BaseModel):
    """Schema for parcel identifier in API responses."""

    id: str
    county: str
    identifier_type: str
    identifier_value: str
    is_current: bool

    model_config = {"from_attributes": True}


class PropertyCreate(BaseModel):
    """Schema for creating a property."""

    address: AddressCreate
    property_type: str = "single_family"


class PropertyResponse(BaseModel):
    """Schema for property in API responses."""

    id: str
    property_type: str
    created_at: datetime
    updated_at: datetime
    addresses: list[AddressResponse] = []
    parcel_identifiers: list[ParcelIdentifierResponse] = []

    model_config = {"from_attributes": True}


class PropertySummary(BaseModel):
    """Compact property listing for watchlist/list views."""

    id: str
    property_type: str
    address: Optional[str] = None
    county: Optional[str] = None
    created_at: datetime


class WatchlistEntryCreate(BaseModel):
    """Schema for adding a property to watchlist."""

    property_id: str
    stage: str = "researching"
    priority: int = 0


class WatchlistEntryResponse(BaseModel):
    """Schema for watchlist entry in API responses."""

    id: str
    property_id: str
    stage: str
    priority: int
    added_at: datetime
    stage_changed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WatchlistStageUpdate(BaseModel):
    """Schema for updating watchlist stage."""

    stage: str
