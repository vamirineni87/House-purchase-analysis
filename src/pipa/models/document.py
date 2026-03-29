"""Document storage, fact extraction, photos, and notes models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class Document(Base, UUIDMixin, TimestampMixin):
    """Uploaded or fetched document (inspection report, disclosure, etc.)."""

    __tablename__ = "document"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    document_type: Mapped[str] = mapped_column(
        String(30),
        comment="inspection, disclosure, appraisal, contract, hoa_ccr, other",
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtractedFact(Base, UUIDMixin, TimestampMixin):
    """A structured fact extracted from a document (e.g., roof age from inspection)."""

    __tablename__ = "extracted_fact"
    __table_args__ = (
        Index("ix_fact_property_type", "property_id", "fact_type"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("document.id"), index=True)
    fact_type: Mapped[str] = mapped_column(String(100))
    fact_value_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    fact_value_number: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fact_value_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), comment="confirmed, estimated, inferred, unknown")
    page_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class PhotoAsset(Base, UUIDMixin, TimestampMixin):
    """Photo associated with a property."""

    __tablename__ = "photo_asset"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    storage_path: Mapped[str] = mapped_column(String(1000))
    caption: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PropertyNote(Base, UUIDMixin, TimestampMixin):
    """User-authored note or observation about a property."""

    __tablename__ = "property_note"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    note_type: Mapped[str] = mapped_column(
        String(20),
        comment="general, showing, concern, positive",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
