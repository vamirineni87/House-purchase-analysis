"""HOA financial, rules, and document models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class HOAFeeHistory(Base, UUIDMixin, TimestampMixin):
    """Historical HOA / condo fee amounts over time."""

    __tablename__ = "hoa_fee_history"
    __table_args__ = (
        Index("ix_hoa_fee_community_date", "community_id", "effective_date"),
    )

    community_id: Mapped[str] = mapped_column(String(36), ForeignKey("community.id"), index=True)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    monthly_amount: Mapped[float] = mapped_column(Float)
    special_assessment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class HOARule(Base, UUIDMixin, TimestampMixin):
    """Individual rule or restriction from CC&Rs or bylaws."""

    __tablename__ = "hoa_rule"

    community_id: Mapped[str] = mapped_column(String(36), ForeignKey("community.id"), index=True)
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    restriction_level: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)


class HOAFinancialSnapshot(Base, UUIDMixin, TimestampMixin):
    """Annual financial health snapshot for an HOA."""

    __tablename__ = "hoa_financial_snapshot"
    __table_args__ = (
        Index("ix_hoa_fin_community_year", "community_id", "fiscal_year"),
    )

    community_id: Mapped[str] = mapped_column(String(36), ForeignKey("community.id"), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expenses: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reserve_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reserve_pct_funded: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delinquency_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class HOADocument(Base, UUIDMixin, TimestampMixin):
    """Links a community to a stored document (CC&Rs, budget, etc.)."""

    __tablename__ = "hoa_document"

    community_id: Mapped[str] = mapped_column(String(36), ForeignKey("community.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(50))
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=True,
    )
