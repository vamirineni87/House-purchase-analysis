"""Community / HOA association and membership models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class Community(Base, UUIDMixin, TimestampMixin):
    """An HOA, condo association, co-op, or civic association."""

    __tablename__ = "community"

    name: Mapped[str] = mapped_column(String(200))
    community_type: Mapped[str] = mapped_column(
        String(30),
        comment="HOA, condo, coop, civic_association",
    )
    management_company: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )


class PropertyCommunityMembership(Base, UUIDMixin, TimestampMixin):
    """Links a property to a community with temporal membership data."""

    __tablename__ = "property_community_membership"
    __table_args__ = (
        Index("ix_pcm_property_community", "property_id", "community_id"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    community_id: Mapped[str] = mapped_column(String(36), ForeignKey("community.id"), index=True)
    membership_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_record.id"), nullable=True,
    )


class CommunityAmenity(Base, UUIDMixin, TimestampMixin):
    """Amenity provided by a community (pool, gym, etc.)."""

    __tablename__ = "community_amenity"

    community_id: Mapped[str] = mapped_column(String(36), ForeignKey("community.id"), index=True)
    amenity_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
