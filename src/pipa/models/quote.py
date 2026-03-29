"""Mortgage, insurance, and repair estimate quote models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class MortgageQuote(Base, UUIDMixin, TimestampMixin):
    """Captured mortgage rate / payment quote."""

    __tablename__ = "mortgage_quote"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    lender: Mapped[str] = mapped_column(String(200))
    rate: Mapped[float] = mapped_column(Float)
    apr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    term: Mapped[int] = mapped_column(Integer, comment="Loan term in months")
    loan_amount: Mapped[float] = mapped_column(Float)
    down_payment_pct: Mapped[float] = mapped_column(Float)
    monthly_payment: Mapped[float] = mapped_column(Float)
    points: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    closing_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class InsuranceQuote(Base, UUIDMixin, TimestampMixin):
    """Captured homeowner's or specialty insurance quote."""

    __tablename__ = "insurance_quote"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    provider: Mapped[str] = mapped_column(String(200))
    policy_type: Mapped[str] = mapped_column(String(50))
    annual_premium: Mapped[float] = mapped_column(Float)
    deductible: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    coverage_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RepairEstimate(Base, UUIDMixin, TimestampMixin):
    """Cost estimate for a repair or replacement."""

    __tablename__ = "repair_estimate"

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    component_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_low: Mapped[float] = mapped_column(Float)
    cost_mid: Mapped[float] = mapped_column(Float)
    cost_high: Mapped[float] = mapped_column(Float)
    urgency: Mapped[str] = mapped_column(
        String(20),
        comment="immediate, 1_year, 3_year, 5_year",
    )
    contractor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
