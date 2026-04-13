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
    watchlist_stage: Optional[str] = None
    decision_status: Optional[str] = None
    decision_stage: Optional[str] = None


class PropertyIngestRequest(BaseModel):
    """Schema for ingesting a property from a listing URL or manual address.

    At least one of ``url`` or ``address`` must be provided.
    """

    url: Optional[str] = Field(None, description="Listing URL from Zillow, Redfin, or Realtor.com")
    address: Optional[AddressCreate] = Field(None, description="Manual address entry (when no URL)")
    property_type: str = "single_family"

    def model_post_init(self, __context):
        if not self.url and not self.address:
            raise ValueError("At least one of 'url' or 'address' must be provided")


class ListingPageSnapshotResponse(BaseModel):
    """Schema for listing page snapshot in API responses."""

    id: str
    property_id: str
    source_site: str
    listing_url: str
    scraped_at: datetime
    parsed_fields: Optional[dict] = None
    raw_html_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    parser_version: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PropertyIngestResponse(BaseModel):
    """Response from the ingest endpoint — property plus optional snapshot."""

    property: PropertyResponse
    snapshot: Optional[ListingPageSnapshotResponse] = None


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
