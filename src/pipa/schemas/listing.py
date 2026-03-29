"""Pydantic v2 schemas for listing endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ListingEpisodeCreate(BaseModel):
    """Create a new listing episode."""

    source: str = "manual"
    original_list_price: Optional[float] = None
    original_list_date: Optional[datetime] = None
    status: str = "active"
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[float] = None
    year_built: Optional[int] = None
    mls_number: Optional[str] = None


class ListingEpisodeResponse(BaseModel):
    """Listing episode returned by the API."""

    id: str
    property_id: str
    source: str
    original_list_price: Optional[float] = None
    original_list_date: Optional[datetime] = None
    status: str
    final_price: Optional[float] = None
    close_date: Optional[datetime] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[float] = None
    year_built: Optional[int] = None
    mls_number: Optional[str] = None
    days_on_market: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingSnapshotCreate(BaseModel):
    """Add a price/status snapshot to an episode."""

    price: float
    status: str


class ListingSnapshotResponse(BaseModel):
    """Listing snapshot returned by the API."""

    id: str
    listing_episode_id: str
    captured_at: datetime
    price: float
    status: str
    delta_price: Optional[float] = None

    model_config = {"from_attributes": True}


class TimelineEvent(BaseModel):
    """A generic event in a property's timeline."""

    event_type: str  # "listing", "price_change", "status_change", "sale"
    date: datetime
    description: str
    data: Optional[dict] = None
