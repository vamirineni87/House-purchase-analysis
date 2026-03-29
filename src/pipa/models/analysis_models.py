"""Analysis versioning and reproducibility models.

Every analysis run is recorded with its ruleset version, code version,
and input data hash. Assumption sets track configurable parameters separately
from code, so changes in either can be traced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class AnalysisRun(Base, UUIDMixin, TimestampMixin):
    """Record of a single analysis execution for reproducibility.

    Answers: "why did this property's score change?"
    Was it new data (input_snapshot_hash changed) or new logic (ruleset_version changed)?
    """

    __tablename__ = "analysis_run"
    __table_args__ = (
        Index("ix_analysis_run_property", "property_id", "analysis_type", "computed_at"),
    )

    property_id: Mapped[str] = mapped_column(String(36), ForeignKey("property.id"), index=True)
    analysis_type: Mapped[str] = mapped_column(
        String(50),
        comment="financial, appraisal, neighborhood, tax, insurance, investment, condition, hoa, surrounding, offer",
    )
    ruleset_version: Mapped[str] = mapped_column(String(20), comment="Semantic version of the analysis logic")
    code_version: Mapped[str] = mapped_column(String(50), comment="Git commit hash or package version")
    input_snapshot_hash: Mapped[str] = mapped_column(
        String(64),
        comment="SHA-256 of the serialized input data — detect data changes",
    )
    output_json: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AssumptionSet(Base, UUIDMixin, TimestampMixin):
    """Versioned set of configurable assumptions used by analyzers.

    Separate from code so financial defaults, replacement costs, scoring weights,
    and stress-test parameters can be tracked and compared independently.
    """

    __tablename__ = "assumption_set"
    __table_args__ = (
        Index("ix_assumption_set_active", "category", "active_from"),
    )

    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(
        String(50),
        comment="reserve_life, replacement_cost, stress_test, scoring_weight, appreciation, financial_defaults",
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    values_json: Mapped[dict] = mapped_column(JSON)
    active_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
