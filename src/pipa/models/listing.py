"""Listing lifecycle models: episodes, snapshots, and events."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class ListingEpisode(Base, UUIDMixin, TimestampMixin):
    """A single listing episode (list-to-close or list-to-withdraw)."""

    __tablename__ = "listing_episode"
    __table_args__ = (
        Index("ix_listing_episode_property", "property_id", "status"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    source: Mapped[str] = mapped_column(String(100))
    original_list_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    original_list_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), comment="active, pending, sold, withdrawn, expired")
    final_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bedrooms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sqft: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    year_built: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mls_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    days_on_market: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    snapshots: Mapped[list[ListingSnapshot]] = relationship(back_populates="listing_episode", cascade="all, delete-orphan")
    status_events: Mapped[list[StatusEvent]] = relationship(back_populates="listing_episode", cascade="all, delete-orphan")
    price_events: Mapped[list[PriceEvent]] = relationship(back_populates="listing_episode", cascade="all, delete-orphan")


class ListingSnapshot(Base, UUIDMixin, TimestampMixin):
    """Point-in-time capture of a listing's state."""

    __tablename__ = "listing_snapshot"

    listing_episode_id: Mapped[str] = mapped_column(String(36), ForeignKey("listing_episode.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30))
    delta_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    listing_episode: Mapped[ListingEpisode] = relationship(back_populates="snapshots")


class StatusEvent(Base, UUIDMixin, TimestampMixin):
    """Status transition event within a listing episode."""

    __tablename__ = "status_event"

    listing_episode_id: Mapped[str] = mapped_column(String(36), ForeignKey("listing_episode.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Relationships
    listing_episode: Mapped[ListingEpisode] = relationship(back_populates="status_events")


class PriceEvent(Base, UUIDMixin, TimestampMixin):
    """Price change event within a listing episode."""

    __tablename__ = "price_event"

    listing_episode_id: Mapped[str] = mapped_column(String(36), ForeignKey("listing_episode.id"), index=True)
    old_price: Mapped[float] = mapped_column(Float)
    new_price: Mapped[float] = mapped_column(Float)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Relationships
    listing_episode: Mapped[ListingEpisode] = relationship(back_populates="price_events")


class SaleEvent(Base, UUIDMixin, TimestampMixin):
    """Confirmed sale event (may come from deed, MLS, or other source)."""

    __tablename__ = "sale_event"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    sale_price: Mapped[float] = mapped_column(Float)
    sale_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(100))
