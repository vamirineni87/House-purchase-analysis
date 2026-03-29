"""Background job model with SQLite-safe worker guardrails.

Rules:
- One writer process for scheduled ingestion jobs
- Idempotency keys prevent duplicate work
- Job leasing with heartbeat (lease_expires_at)
- Retry with backoff, no overlapping refresh for same property + job_type
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class RefreshJob(Base, UUIDMixin, TimestampMixin):
    """Background refresh/ingestion job with idempotency and leasing."""

    __tablename__ = "refresh_job"
    __table_args__ = (
        Index("ix_refresh_job_idempotency", "idempotency_key", unique=True),
        Index("ix_refresh_job_status", "status", "scheduled_at"),
        Index("ix_refresh_job_property", "property_id", "job_type"),
    )

    property_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("property.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(
        String(50),
        comment="county_refresh, listing_monitor, alert_evaluation, source_health_check",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending, leased, running, completed, failed, cancelled",
    )

    # Idempotency: prevent duplicate jobs for same work
    idempotency_key: Mapped[str] = mapped_column(String(200))

    # Leasing: only one worker can hold this job at a time
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Scheduling
    priority: Mapped[int] = mapped_column(Integer, default=50, comment="Higher = process first")
    triggered_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="scheduler, user, alert")
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Lifecycle timestamps
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
