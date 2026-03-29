"""Alert endpoints — events and subscriptions."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.alert import AlertEvent
from pipa.schemas.alert import AlertResponse, AlertSubscriptionCreate, AlertSubscriptionResponse
from pipa.services.alert_service import AlertService

router = APIRouter(tags=["alerts"])

# Single-user desktop app default
DEFAULT_USER_ID = "default-user"


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    property_id: Optional[str] = None,
    is_read: Optional[bool] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List alerts, optionally filtered by property and/or read status."""
    return await AlertService.get_alerts(
        db,
        property_id=property_id,
        is_read=is_read,
        limit=limit,
    )


@router.patch("/alerts/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as read."""
    alert = await AlertService.mark_read(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/mark-all-read", status_code=204)
async def mark_all_alerts_read(db: AsyncSession = Depends(get_db)):
    """Mark all unread alerts as read."""
    result = await db.execute(
        select(AlertEvent).where(AlertEvent.is_read == False)  # noqa: E712
    )
    alerts = result.scalars().all()
    for alert in alerts:
        alert.is_read = True


@router.get("/alerts/subscriptions", response_model=list[AlertSubscriptionResponse])
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
):
    """List all alert subscriptions for the current user."""
    return await AlertService.get_subscriptions(db, DEFAULT_USER_ID)


@router.post(
    "/alerts/subscriptions",
    response_model=AlertSubscriptionResponse,
    status_code=201,
)
async def create_subscription(
    body: AlertSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert subscription."""
    return await AlertService.create_subscription(
        db,
        user_id=DEFAULT_USER_ID,
        alert_type=body.alert_type,
        filter_criteria=body.filter_criteria,
    )
