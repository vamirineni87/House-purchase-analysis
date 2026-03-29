"""User, watchlist, buyer profile, and scoring models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipa.models.base import Base, TimestampMixin, UUIDMixin


# Many-to-many: property <-> tag
property_tag = Table(
    "property_tag",
    Base.metadata,
    Column("property_id", String(36), ForeignKey("property.id"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tag.id"), primary_key=True),
)


class User(Base, UUIDMixin, TimestampMixin):
    """Application user."""

    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    watchlist_entries: Mapped[list[WatchlistEntry]] = relationship(back_populates="user", cascade="all, delete-orphan")
    buyer_profiles: Mapped[list[BuyerProfile]] = relationship(back_populates="user", cascade="all, delete-orphan")
    scoring_profiles: Mapped[list[ScoringProfile]] = relationship(back_populates="user", cascade="all, delete-orphan")


class WatchlistEntry(Base, UUIDMixin, TimestampMixin):
    """Property on user's watchlist with kanban stage tracking."""

    __tablename__ = "watchlist_entry"
    __table_args__ = (
        Index("ix_watchlist_user_property", "user_id", "property_id", unique=True),
        Index("ix_watchlist_stage", "user_id", "stage"),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"))
    stage: Mapped[str] = mapped_column(
        String(20), default="researching",
        comment="researching, touring, offer, contract, closed, rejected",
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    stage_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="watchlist_entries")


class Tag(Base, UUIDMixin, TimestampMixin):
    """User-defined tag for categorizing properties."""

    __tablename__ = "tag"

    name: Mapped[str] = mapped_column(String(100), unique=True)


class BuyerProfile(Base, UUIDMixin, TimestampMixin):
    """Buyer's preferences and constraints for personalized scoring."""

    __tablename__ = "buyer_profile"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="Default")
    budget_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    payment_comfort: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Max comfortable monthly payment")
    renovation_tolerance: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="none, cosmetic, moderate, major")
    hoa_tolerance: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="none, low, moderate, high")
    school_priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="1-10")
    commute_priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="1-10")
    risk_tolerance: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="conservative, moderate, aggressive")
    hold_period_years: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    investment_optionality_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="0.0-1.0")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="buyer_profiles")


class ScoringProfile(Base, UUIDMixin, TimestampMixin):
    """Custom scoring weights for property comparison."""

    __tablename__ = "scoring_profile"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="Default")
    weights_json: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "financial": 0.25,
            "condition": 0.20,
            "location": 0.20,
            "risk": 0.15,
            "hoa": 0.10,
            "surrounding": 0.10,
        },
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="scoring_profiles")
