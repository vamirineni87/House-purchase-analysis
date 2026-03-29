"""Assessment / tax snapshot models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class AssessmentSnapshot(Base, UUIDMixin, TimestampMixin):
    """Annual assessment / tax valuation snapshot from county records."""

    __tablename__ = "assessment_snapshot"
    __table_args__ = (
        Index("ix_assessment_property_year", "property_id", "tax_year"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    tax_year: Mapped[int] = mapped_column(Integer)
    land_value: Mapped[float] = mapped_column(Float)
    improvement_value: Mapped[float] = mapped_column(Float)
    total_value: Mapped[float] = mapped_column(Float)
    tax_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    annual_tax: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )
