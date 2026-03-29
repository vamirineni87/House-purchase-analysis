"""Alert event and subscription models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class AlertEvent(Base, UUIDMixin, TimestampMixin):
    """A triggered alert (price drop, new listing, status change, etc.)."""

    __tablename__ = "alert_event"

    property_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("property.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20), default="info",
        comment="info, warning, critical",
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertSubscription(Base, UUIDMixin, TimestampMixin):
    """User subscription to a specific type of alert."""

    __tablename__ = "alert_subscription"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), index=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    filter_criteria: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
