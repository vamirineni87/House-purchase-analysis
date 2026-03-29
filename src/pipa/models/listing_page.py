"""Listing page snapshot model — captures a scrape of a listing site page."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class ListingPageSnapshot(Base, UUIDMixin, TimestampMixin):
    """Point-in-time scrape of a listing page (Zillow, Redfin, Realtor.com).

    Stores the fully parsed fields as structured JSON alongside paths to
    the raw HTML and screenshot for debugging and change detection.
    """

    __tablename__ = "listing_page_snapshot"
    __table_args__ = (
        Index("ix_listing_page_property", "property_id", "source_site"),
        Index("ix_listing_page_url", "listing_url"),
    )

    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("property.id"), index=True,
    )
    source_site: Mapped[str] = mapped_column(
        String(30),
        comment="zillow, redfin, realtor",
    )
    listing_url: Mapped[str] = mapped_column(String(1000))
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    parsed_fields: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_html_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    parser_version: Mapped[str] = mapped_column(
        String(30), default="1.0.0",
        comment="Version of the parser that extracted parsed_fields",
    )
    canonical_listing_key: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Cross-site canonical key, e.g. zillow:251682872",
    )
    site_listing_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Site-specific listing ID, e.g. 251682872_zpid",
    )
    scrape_success: Mapped[bool] = mapped_column(Boolean, default=True)
    parser_strategy_used: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
        comment="graphql, jsonld, dom, mixed",
    )
    parse_warnings: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        comment="List of warning strings from the parser",
    )
    html_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="Hash of saved HTML for change detection",
    )
    extracted_at_version: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
        comment="Parser version at extraction time",
    )
