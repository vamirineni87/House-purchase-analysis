"""Deed / ownership-transfer models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class DeedRecord(Base, UUIDMixin, TimestampMixin):
    """Recorded deed or ownership-transfer event."""

    __tablename__ = "deed_record"
    __table_args__ = (
        Index("ix_deed_property_date", "property_id", "sale_date"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    grantor: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    grantee: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sale_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sale_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deed_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    instrument_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    recorded_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )
