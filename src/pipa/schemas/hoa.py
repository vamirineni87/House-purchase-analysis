"""Pydantic v2 schemas for HOA endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HOASummary(BaseModel):
    """Summary HOA info for a property."""

    community_id: Optional[str] = None
    community_name: Optional[str] = None
    community_type: Optional[str] = None
    management_company: Optional[str] = None
    current_monthly_fee: Optional[float] = None
    is_member: bool = False


class HOAUpdate(BaseModel):
    """Update HOA community link for a property."""

    community_name: str
    community_type: str = "HOA"
    management_company: Optional[str] = None


class HOAFeeCreate(BaseModel):
    """Add an HOA fee history entry."""

    effective_date: datetime
    monthly_amount: float
    special_assessment: Optional[float] = None


class HOAFeeResponse(BaseModel):
    """HOA fee history entry returned by the API."""

    id: str
    community_id: str
    effective_date: datetime
    monthly_amount: float
    special_assessment: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}
