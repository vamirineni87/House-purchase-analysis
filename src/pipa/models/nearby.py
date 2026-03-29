"""Nearby property relationship model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class NearbyRelationship(Base, UUIDMixin, TimestampMixin):
    """Spatial or logical relationship between two properties."""

    __tablename__ = "nearby_relationship"
    __table_args__ = (
        Index("ix_nearby_subject_type", "subject_property_id", "relationship_type"),
    )

    subject_property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    related_property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(
        String(30),
        comment="adjacent, same_street, same_subdivision, same_HOA, within_250ft, within_500ft, same_school_zone, same_builder_cluster",
    )
    distance_feet: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
