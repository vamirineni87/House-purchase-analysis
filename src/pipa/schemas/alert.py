"""Pydantic v2 schemas for alert endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AlertResponse(BaseModel):
    """Alert event returned by the API."""

    id: str
    property_id: Optional[str] = None
    alert_type: str
    title: str
    description: Optional[str] = None
    severity: str
    is_read: bool
    data: Optional[dict] = None
    triggered_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertSubscriptionCreate(BaseModel):
    """Create an alert subscription."""

    alert_type: str
    filter_criteria: Optional[dict] = None


class AlertSubscriptionResponse(BaseModel):
    """Alert subscription returned by the API."""

    id: str
    user_id: str
    alert_type: str
    filter_criteria: Optional[dict] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
