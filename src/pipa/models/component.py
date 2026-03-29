"""Home component system and evidence models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class ComponentSystem(Base, UUIDMixin, TimestampMixin):
    """A major building component (roof, HVAC, etc.) with lifecycle metadata."""

    __tablename__ = "component_system"
    __table_args__ = (
        Index("ix_component_property_type", "property_id", "component_type"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    component_type: Mapped[str] = mapped_column(
        String(30),
        comment="roof, hvac, water_heater, electrical_panel, plumbing, windows, siding, foundation, deck, appliances, drainage",
    )
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_install_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expected_lifespan: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_replacement_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(20), default="unknown",
        comment="confirmed, estimated, unknown",
    )


class ComponentEvidence(Base, UUIDMixin, TimestampMixin):
    """Evidence supporting a component system's metadata."""

    __tablename__ = "component_evidence"

    component_system_id: Mapped[str] = mapped_column(String(36), ForeignKey("component_system.id"), index=True)
    source: Mapped[str] = mapped_column(
        String(30),
        comment="permit, inspection, disclosure, listing, user",
    )
    source_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=True,
    )
