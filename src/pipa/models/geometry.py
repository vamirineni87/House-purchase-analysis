"""Geometry and spatial overlay models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class GeometrySnapshot(Base, UUIDMixin, TimestampMixin):
    """Captured geometry (parcel boundary, building footprint, etc.)."""

    __tablename__ = "geometry_snapshot"
    __table_args__ = (
        Index("ix_geometry_property_type", "property_id", "geometry_type"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    geometry_type: Mapped[str] = mapped_column(
        String(30),
        comment="parcel_boundary, building_footprint, address_point, lot_outline",
    )
    geometry_format: Mapped[str] = mapped_column(
        String(10),
        comment="geojson, wkt",
    )
    geometry_data: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )


class OverlayIntersection(Base, UUIDMixin, TimestampMixin):
    """Records whether a property intersects with a spatial overlay layer."""

    __tablename__ = "overlay_intersection"
    __table_args__ = (
        Index("ix_overlay_property_type", "property_id", "overlay_type"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    overlay_type: Mapped[str] = mapped_column(
        String(30),
        comment="floodplain, watershed, easement, utility_corridor, airport_noise, soil_class, slope_band, zoning_overlay",
    )
    intersects: Mapped[bool] = mapped_column(Boolean)
    overlap_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overlay_value_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )
