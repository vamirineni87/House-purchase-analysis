"""Pipeline run and task tracking models.

Provides first-class run/task status tracking so the dashboard can show
pipeline progress, partial successes, retries, and per-task control.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class PipelineRun(Base, UUIDMixin, TimestampMixin):
    """Top-level pipeline execution record for a property."""

    __tablename__ = "pipeline_run"
    __table_args__ = (
        Index("ix_pipeline_run_property", "property_id", "created_at"),
        Index("ix_pipeline_run_status", "status"),
    )

    property_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("property.id"), index=True,
    )
    run_type: Mapped[str] = mapped_column(
        String(50),
        comment="quick_ingest, full_pipeline, refresh_zillow, refresh_county, "
                "run_deep_comp, rerun_ai, rerun_financials",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="queued",
        comment="queued, running, partial_success, succeeded, failed, cancelled",
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    initiated_by: Mapped[str] = mapped_column(
        String(20), default="user",
        comment="user, scheduler, system",
    )

    summary_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    tasks: Mapped[list[PipelineTaskRun]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="PipelineTaskRun.created_at",
    )


class PipelineTaskRun(Base, UUIDMixin, TimestampMixin):
    """Individual task execution within a pipeline run."""

    __tablename__ = "pipeline_task_run"
    __table_args__ = (
        Index("ix_pipeline_task_run_run", "pipeline_run_id", "task_name"),
        Index("ix_pipeline_task_run_status", "status"),
    )

    pipeline_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_run.id"), index=True,
    )
    task_name: Mapped[str] = mapped_column(
        String(50),
        comment="zillow_scrape, county_scrape, ai_pass_1, resolver, financial, "
                "tax, condition, offer, stress, warning_engine, ai_pass_2, "
                "decision_packet, school_lookup, comp_quick, comp_deep",
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending, running, succeeded, failed, skipped",
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="tasks")
