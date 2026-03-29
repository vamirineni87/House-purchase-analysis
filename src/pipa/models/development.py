"""Development and zoning case models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class DevelopmentCase(Base, UUIDMixin, TimestampMixin):
    """Active or recent development / land-use case near a property."""

    __tablename__ = "development_case"

    property_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("property.id"), nullable=True, index=True)
    case_number: Mapped[str] = mapped_column(String(100))
    case_type: Mapped[str] = mapped_column(String(50))
    applicant: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    distance_feet: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    hearing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(100))


class ZoningCase(Base, UUIDMixin, TimestampMixin):
    """Zoning amendment or variance case."""

    __tablename__ = "zoning_case"

    property_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("property.id"), nullable=True, index=True)
    case_number: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(50))
    applicant: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    hearing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
