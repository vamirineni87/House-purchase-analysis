"""Core property identity models.

Supports parcel splits/merges/renumbers and historical addresses.
Parcel ID is the canonical anchor, not listing-site address text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class Property(Base, UUIDMixin, TimestampMixin):
    """Central entity. Everything hangs off this."""

    __tablename__ = "property"

    property_type: Mapped[str] = mapped_column(
        String(50), default="single_family",
        comment="single_family, condo, townhouse, multi_family",
    )

    # Relationships
    parcels: Mapped[list[Parcel]] = relationship(back_populates="property", cascade="all, delete-orphan")
    parcel_identifiers: Mapped[list[ParcelIdentifier]] = relationship(back_populates="property", cascade="all, delete-orphan")
    parcel_events: Mapped[list[ParcelEvent]] = relationship(back_populates="property", cascade="all, delete-orphan")
    addresses: Mapped[list[AddressHistory]] = relationship(back_populates="property", cascade="all, delete-orphan")

    @property
    def current_address(self) -> Optional[AddressHistory]:
        """Get the current situs address."""
        for addr in self.addresses:
            if addr.is_current and addr.address_type == "situs":
                return addr
        return None

    @property
    def current_parcel_number(self) -> Optional[str]:
        """Get the current parcel number identifier."""
        for pid in self.parcel_identifiers:
            if pid.is_current and pid.identifier_type == "parcel_number":
                return pid.identifier_value
        return None


class Parcel(Base, UUIDMixin, TimestampMixin):
    """Physical parcel record from county GIS."""

    __tablename__ = "parcel"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    county: Mapped[str] = mapped_column(String(50), comment="fairfax, loudoun")
    legal_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    land_use_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    acreage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lot_sqft: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    property: Mapped[Property] = relationship(back_populates="parcels")


class ParcelIdentifier(Base, UUIDMixin, TimestampMixin):
    """Typed parcel identifier with temporal validity.

    Supports multiple identifier types and handles renumbers/changes over time.
    """

    __tablename__ = "parcel_identifier"
    __table_args__ = (
        Index("ix_parcel_id_current", "county", "identifier_type", "identifier_value", "is_current"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    county: Mapped[str] = mapped_column(String(50))
    identifier_type: Mapped[str] = mapped_column(
        String(30),
        comment="parcel_number, tax_map_number, account_number, GIS_PIN, source_specific_key",
    )
    identifier_value: Mapped[str] = mapped_column(String(100))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("source_record.id"), nullable=True)

    # Relationships
    property: Mapped[Property] = relationship(back_populates="parcel_identifiers")


class ParcelEvent(Base, UUIDMixin, TimestampMixin):
    """Events that change parcel identity: splits, merges, renumbers, boundary adjustments."""

    __tablename__ = "parcel_event"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    event_type: Mapped[str] = mapped_column(
        String(30),
        comment="split, merge, renumber, address_change, boundary_adjustment",
    )
    event_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("source_record.id"), nullable=True)

    # Relationships
    property: Mapped[Property] = relationship(back_populates="parcel_events")


class AddressHistory(Base, UUIDMixin, TimestampMixin):
    """Address records with type and temporal validity."""

    __tablename__ = "address_history"
    __table_args__ = (
        Index("ix_address_current", "property_id", "address_type", "is_current"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    address_type: Mapped[str] = mapped_column(
        String(20),
        comment="situs, mailing, historical, listing_display",
    )
    normalized_address: Mapped[str] = mapped_column(String(500))
    raw_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("source_record.id"), nullable=True)

    # Relationships
    property: Mapped[Property] = relationship(back_populates="addresses")
