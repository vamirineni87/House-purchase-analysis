"""Pipeline orchestration endpoints — run, monitor, retry, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.property import Property
from pipa.schemas.pipeline_run import (
    PipelineRunDetail,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineTaskRunResponse,
    TaskRerunRequest,
)
from pipa.services.pipeline_orchestrator import (
    PipelineOrchestrator,
    VALID_RUN_TYPES,
    VALID_TASK_NAMES,
)

router = APIRouter(tags=["pipeline"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _verify_property(db: AsyncSession, property_id: str) -> Property:
    """Load and return the property or raise 404."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


# ------------------------------------------------------------------
# Property-scoped endpoints
# ------------------------------------------------------------------


@router.post(
    "/properties/{property_id}/pipeline/run",
    response_model=PipelineRunDetail,
    status_code=201,
    summary="Start a pipeline run for a property",
)
async def start_pipeline_run(
    property_id: str,
    body: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new pipeline run with task entries and begin execution.

    The run is created in 'queued' status, tasks are initialized as 'pending',
    then execution begins immediately.
    """
    await _verify_property(db, property_id)

    if body.run_type not in VALID_RUN_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid run_type: {body.run_type}. Must be one of {sorted(VALID_RUN_TYPES)}",
        )

    run = await PipelineOrchestrator.start_run(
        db,
        property_id=property_id,
        run_type=body.run_type,
        initiated_by=body.initiated_by,
    )

    # Execute the pipeline (updates task statuses in-flight)
    run = await PipelineOrchestrator.execute_run(db, run.id)

    # Re-fetch with tasks for the response
    run_data = await PipelineOrchestrator.get_run(db, run.id)
    if not run_data:
        raise HTTPException(status_code=500, detail="Run created but could not be retrieved")
    return run_data


@router.post(
    "/properties/{property_id}/pipeline/run-task",
    response_model=PipelineRunDetail,
    status_code=201,
    summary="Run a single task for a property",
)
async def run_single_task(
    property_id: str,
    body: TaskRerunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a pipeline run with a single task and execute it."""
    await _verify_property(db, property_id)

    if body.task_name not in VALID_TASK_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid task_name: {body.task_name}. Must be one of {sorted(VALID_TASK_NAMES)}",
        )

    # Create a minimal run with just this one task
    run = await PipelineOrchestrator.start_run(
        db,
        property_id=property_id,
        run_type="full_pipeline",  # generic container
        initiated_by="user",
    )

    # Skip all tasks except the requested one
    from pipa.models.pipeline_run import PipelineTaskRun
    result = await db.execute(
        select(PipelineTaskRun).where(PipelineTaskRun.pipeline_run_id == run.id)
    )
    for task in result.scalars().all():
        if task.task_name != body.task_name:
            task.status = "skipped"
    await db.flush()

    run = await PipelineOrchestrator.execute_run(db, run.id)

    run_data = await PipelineOrchestrator.get_run(db, run.id)
    if not run_data:
        raise HTTPException(status_code=500, detail="Run created but could not be retrieved")
    return run_data


@router.post(
    "/properties/{property_id}/pipeline/cancel",
    response_model=PipelineRunResponse,
    summary="Cancel the latest running pipeline for a property",
)
async def cancel_pipeline_run(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Cancel the most recent running pipeline run for a property."""
    await _verify_property(db, property_id)

    latest = await PipelineOrchestrator.get_latest_run(db, property_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No pipeline runs found for this property")

    if latest["status"] not in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel a run with status '{latest['status']}'",
        )

    run = await PipelineOrchestrator.cancel_run(db, latest["id"])
    return run


@router.get(
    "/properties/{property_id}/pipeline/runs",
    response_model=list[PipelineRunDetail],
    summary="List pipeline runs for a property",
)
async def list_pipeline_runs(
    property_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Return recent pipeline runs for a property, newest first."""
    await _verify_property(db, property_id)
    runs = await PipelineOrchestrator.get_runs_for_property(db, property_id, limit=limit)
    return runs


# ------------------------------------------------------------------
# Run-scoped endpoints (not property-scoped)
# ------------------------------------------------------------------


@router.get(
    "/pipeline-runs/{run_id}",
    response_model=PipelineRunDetail,
    summary="Get pipeline run detail with all tasks",
)
async def get_pipeline_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single pipeline run with its task details."""
    run_data = await PipelineOrchestrator.get_run(db, run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run_data


@router.post(
    "/pipeline-runs/{run_id}/rerun-task",
    response_model=PipelineTaskRunResponse,
    summary="Rerun a failed task within an existing pipeline run",
)
async def rerun_task(
    run_id: str,
    body: TaskRerunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rerun a single task within an existing pipeline run.

    Useful for retrying failed tasks without re-running the entire pipeline.
    """
    if body.task_name not in VALID_TASK_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid task_name: {body.task_name}. Must be one of {sorted(VALID_TASK_NAMES)}",
        )

    try:
        task = await PipelineOrchestrator.rerun_task(db, run_id, body.task_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return task
