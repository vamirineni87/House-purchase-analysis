"""Natural hazard and risk profile model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class HazardProfile(Base, UUIDMixin, TimestampMixin):
    """Aggregated natural hazard risk profile for a property."""

    __tablename__ = "hazard_profile"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), unique=True, index=True)
    flood_zone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    flood_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    radon_zone: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    radon_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wildfire_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    earthquake_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hurricane_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tornado_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overall_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nri_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
