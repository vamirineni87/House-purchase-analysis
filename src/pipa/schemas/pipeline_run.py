"""Pydantic v2 schemas for pipeline run and task tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Response schemas ---


class PipelineTaskRunResponse(BaseModel):
    """Single task within a pipeline run."""

    id: str
    pipeline_run_id: str
    task_name: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    retry_count: int = 0
    result_summary: Optional[dict[str, Any]] = None
    error_details: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunResponse(BaseModel):
    """Pipeline run without nested tasks."""

    id: str
    property_id: str
    run_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    initiated_by: str = "user"
    summary_json: Optional[dict[str, Any]] = None
    error_count: int = 0
    warning_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunDetail(PipelineRunResponse):
    """Pipeline run with all nested task details."""

    tasks: list[PipelineTaskRunResponse] = []


# --- Request schemas ---


class PipelineRunRequest(BaseModel):
    """Request to start a pipeline run."""

    run_type: str = Field(
        ...,
        description="One of: quick_ingest, full_pipeline, refresh_zillow, "
                    "refresh_county, run_deep_comp, rerun_ai, rerun_financials",
    )
    initiated_by: str = Field(
        default="user",
        description="One of: user, scheduler, system",
    )


class TaskRerunRequest(BaseModel):
    """Request to rerun a single task within a pipeline run."""

    task_name: str = Field(
        ...,
        description="One of: zillow_scrape, county_scrape, ai_pass_1, resolver, "
                    "financial, tax, condition, offer, stress, warning_engine, "
                    "ai_pass_2, decision_packet, school_lookup, comp_quick, comp_deep",
    )
