"""Permit, zoning, and plat record models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class PermitRecord(Base, UUIDMixin, TimestampMixin):
    """Building / development permit record."""

    __tablename__ = "permit_record"
    __table_args__ = (
        Index("ix_permit_property_type", "property_id", "type"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    permit_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    issue_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    final_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    contractor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(100))


class ZoningRecord(Base, UUIDMixin, TimestampMixin):
    """Current zoning designation for a property."""

    __tablename__ = "zoning_record"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    zone_code: Mapped[str] = mapped_column(String(30))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    overlay_districts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class PlatRecord(Base, UUIDMixin, TimestampMixin):
    """Recorded plat / subdivision map record."""

    __tablename__ = "plat_record"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    plat_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subdivision_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    book_page: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    easement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )
