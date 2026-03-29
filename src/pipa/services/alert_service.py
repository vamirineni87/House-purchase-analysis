"""Alert management service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.alert import AlertEvent, AlertSubscription


class AlertService:
    """Creates, queries, and manages alert events and subscriptions."""

    # ------------------------------------------------------------------
    # Alert events
    # ------------------------------------------------------------------

    @staticmethod
    async def create_alert(
        db: AsyncSession,
        *,
        property_id: Optional[str] = None,
        alert_type: str,
        title: str,
        description: Optional[str] = None,
        severity: str = "info",
        data: Optional[dict] = None,
    ) -> AlertEvent:
        """Create a new alert event."""
        alert = AlertEvent(
            property_id=property_id,
            alert_type=alert_type,
            title=title,
            description=description,
            severity=severity,
            data=data,
            triggered_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        await db.flush()
        return alert

    @staticmethod
    async def get_alerts(
        db: AsyncSession,
        *,
        property_id: Optional[str] = None,
        is_read: Optional[bool] = None,
        limit: int = 50,
    ) -> list[AlertEvent]:
        """Query alerts with optional filters."""
        query = select(AlertEvent).order_by(AlertEvent.triggered_at.desc())

        if property_id is not None:
            query = query.where(AlertEvent.property_id == property_id)
        if is_read is not None:
            query = query.where(AlertEvent.is_read == is_read)

        query = query.limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def mark_read(
        db: AsyncSession,
        alert_id: str,
    ) -> Optional[AlertEvent]:
        """Mark an alert as read. Returns None if not found."""
        result = await db.execute(
            select(AlertEvent).where(AlertEvent.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if alert is None:
            return None
        alert.is_read = True
        return alert

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    @staticmethod
    async def get_subscriptions(
        db: AsyncSession,
        user_id: str,
    ) -> list[AlertSubscription]:
        """Get all alert subscriptions for a user."""
        result = await db.execute(
            select(AlertSubscription)
            .where(AlertSubscription.user_id == user_id)
            .order_by(AlertSubscription.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_subscription(
        db: AsyncSession,
        user_id: str,
        alert_type: str,
        filter_criteria: Optional[dict] = None,
    ) -> AlertSubscription:
        """Create a new alert subscription."""
        sub = AlertSubscription(
            user_id=user_id,
            alert_type=alert_type,
            filter_criteria=filter_criteria,
        )
        db.add(sub)
        await db.flush()
        return sub
