"""Source provenance, health tracking, and licensing models.

Every external data fetch is archived as a SourceRecord with raw payload.
Evidence items link specific facts to their source with confidence.
Source health tracks scraper reliability over time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class SourceRegistry(Base, TimestampMixin):
    """Registry of all known data sources with licensing and confidence metadata."""

    __tablename__ = "source_registry"

    source_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_type: Mapped[str] = mapped_column(
        String(30),
        comment="official_api, public_arcgis, public_site_scrape, licensed_feed, manual_upload",
    )
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False)
    tos_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_use: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    refresh_policy: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    confidence_rank: Mapped[int] = mapped_column(
        Integer, default=50,
        comment="Higher = more trusted. county=90, deed=80, licensed_api=60, listing=40, heuristic=10",
    )


class SourceRecord(Base, UUIDMixin, TimestampMixin):
    """Raw payload archive for every external data fetch.

    Immutable audit trail. Every API response and scrape result is stored here.
    """

    __tablename__ = "source_record"
    __table_args__ = (
        Index("ix_source_record_property", "property_id", "source_name"),
    )

    property_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("property.id"), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class EvidenceItem(Base, UUIDMixin, TimestampMixin):
    """Links a specific fact about a property to its source with confidence.

    Each row says: "field X has value Y, according to source Z, observed at time T,
    with confidence level C."
    """

    __tablename__ = "evidence_item"
    __table_args__ = (
        Index("ix_evidence_property_field", "property_id", "field_name"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100), comment="e.g., year_built, sqft, roof_age")
    field_value: Mapped[str] = mapped_column(String(500))
    source_record_id: Mapped[str] = mapped_column(String(36), ForeignKey("source_record.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[str] = mapped_column(
        String(20), default="estimated",
        comment="confirmed, estimated, inferred, unknown",
    )


class SourceHealth(Base, UUIDMixin):
    """Tracks health of each data source over time.

    Used to detect when scrapers break due to site changes.
    """

    __tablename__ = "source_health"
    __table_args__ = (
        Index("ix_source_health_latest", "source_name", "checked_at"),
    )

    source_name: Mapped[str] = mapped_column(String(100), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20),
        comment="healthy, degraded, broken, auth_required, structure_changed",
    )
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="DOM structure fingerprint for change detection",
    )


class ScrapeRun(Base, UUIDMixin):
    """Individual scrape execution log.

    Stores HTML snapshots and screenshots for debugging scraper failures.
    """

    __tablename__ = "scrape_run"

    source_name: Mapped[str] = mapped_column(String(100), index=True)
    target_key: Mapped[str] = mapped_column(String(200), comment="e.g., parcel number or address")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    page_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    html_snapshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
