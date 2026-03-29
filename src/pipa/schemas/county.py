"""Pydantic v2 schemas for county data endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# --- Assessment ---


class AssessmentResponse(BaseModel):
    """Single assessment snapshot returned by the API."""

    id: str
    property_id: str
    tax_year: int
    land_value: float
    improvement_value: float
    total_value: float
    tax_rate: Optional[float] = None
    annual_tax: Optional[float] = None
    snapshot_date: datetime

    model_config = {"from_attributes": True}


# --- Permit ---


class PermitResponse(BaseModel):
    """Single permit record returned by the API."""

    id: str
    property_id: str
    permit_number: Optional[str] = None
    type: str
    description: Optional[str] = None
    estimated_cost: Optional[float] = None
    issue_date: Optional[datetime] = None
    final_date: Optional[datetime] = None
    status: Optional[str] = None
    contractor: Optional[str] = None
    source: str

    model_config = {"from_attributes": True}


# --- Deed ---


class DeedResponse(BaseModel):
    """Single deed record returned by the API."""

    id: str
    property_id: str
    grantor: Optional[str] = None
    grantee: Optional[str] = None
    sale_price: Optional[float] = None
    sale_date: Optional[datetime] = None
    deed_type: Optional[str] = None
    instrument_number: Optional[str] = None
    recorded_date: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Refresh result ---


class CountyRefreshResult(BaseModel):
    """Result of a county data refresh operation."""

    property_id: str
    assessments_fetched: int = 0
    permits_fetched: int = 0
    deeds_fetched: int = 0
    errors: list[str] = []
