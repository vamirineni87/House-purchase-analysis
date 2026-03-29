"""Data freshness and TTL policy model."""

from __future__ import annotations

from sqlalchemy import Integer, String

from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin


class DataFreshnessPolicy(Base, TimestampMixin):
    """Defines how fresh data must be for each source/entity combination.

    Examples:
        county parcel fundamentals: ttl_hours=720 (30 days), stale=warn_only
        listing status/price: ttl_hours=4, stale=refresh_before_use
        HOA docs: ttl_hours=8760 (1 year), stale=use_cached
        mortgage quotes: ttl_hours=24, stale=refresh_before_use
    """

    __tablename__ = "data_freshness_policy"

    source_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100), primary_key=True)
    ttl_hours: Mapped[int] = mapped_column(Integer, default=24)
    refresh_priority: Mapped[int] = mapped_column(Integer, default=50, comment="Higher = refresh first")
    stale_behavior: Mapped[str] = mapped_column(
        String(30), default="warn_only",
        comment="warn_only, refresh_before_use, use_cached, require_manual_review",
    )
