"""Decision workflow models — living case files, due diligence tracking,
and versioned buyer-facing recommendations.

These models manage the buyer's active decision process for each listing
under consideration, not just computed analysis numbers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class DecisionCase(Base, UUIDMixin, TimestampMixin):
    """Living case file for each listing under consideration.

    Tracks the buyer's current stance, pricing thresholds, and status
    through the full lifecycle from discovery to outcome.
    """

    __tablename__ = "decision_case"
    __table_args__ = (
        Index("ix_decision_case_property", "property_id"),
        Index("ix_decision_case_stage", "stage", "decision_status"),
    )

    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("property.id"), unique=True, index=True,
    )
    stage: Mapped[str] = mapped_column(
        String(30),
        default="discovered",
        comment="discovered, shortlisted, touring, researching, waiting_on_docs, "
                "offer_ready, offered, passed, lost, won",
    )
    decision_status: Mapped[str] = mapped_column(
        String(20),
        default="maybe",
        comment="pursue, maybe, deprioritize, reject",
    )
    priority: Mapped[int] = mapped_column(Integer, default=5, comment="1-10")
    pursue_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="0-100 computed score",
    )
    max_offer_current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    walk_away_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_monthly_payment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="high, medium, low",
    )
    status_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    offer_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    spouse_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    family_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DueDiligenceItem(Base, UUIDMixin, TimestampMixin):
    """Trackable due diligence task for a property.

    Each item represents something the buyer needs to verify, request,
    or resolve before making an informed decision.
    """

    __tablename__ = "due_diligence_item"
    __table_args__ = (
        Index("ix_dd_item_property", "property_id", "status"),
        Index("ix_dd_item_case", "decision_case_id"),
    )

    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("property.id"), index=True,
    )
    decision_case_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("decision_case.id"), nullable=True,
    )
    category: Mapped[str] = mapped_column(
        String(30),
        comment="hoa, permit, inspection, financing, insurance, legal, "
                "seller_question, agent_question, general",
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        comment="open, requested, received, resolved, blocked",
    )
    severity: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="important",
        comment="critical, important, minor, info",
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=True,
        comment="Link to uploaded document if resolved with a doc",
    )


class RecommendationSnapshot(Base, UUIDMixin, TimestampMixin):
    """Versioned buyer-facing recommendation — changes as new facts arrive.

    Each snapshot captures the system's recommendation at a point in time,
    allowing the buyer to see how the recommendation evolved as data was gathered.
    """

    __tablename__ = "recommendation_snapshot"
    __table_args__ = (
        Index("ix_recommendation_property", "property_id", "created_at"),
        Index("ix_recommendation_case", "decision_case_id"),
    )

    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("property.id"), index=True,
    )
    decision_case_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("decision_case.id"), nullable=True,
    )
    pursue_recommendation: Mapped[str] = mapped_column(
        String(10), comment="pursue, maybe, pass",
    )
    max_offer: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    walk_away_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    main_red_flags: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="List of red-flag strings",
    )
    unresolved_unknowns: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="List of unknown strings",
    )
    top_questions: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="List of questions for agent/inspector",
    )
    compare_rank: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Rank among current shortlist",
    )
    analysis_run_ids: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="List of analysis_run IDs that fed this",
    )
    confidence: Mapped[str] = mapped_column(
        String(10), default="medium", comment="high, medium, low",
    )
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
