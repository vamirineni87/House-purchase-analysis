"""Pipeline orchestrator — wraps PropertyPipeline with first-class run/task tracking.

Every pipeline execution creates a PipelineRun with PipelineTaskRun children.
The dashboard can poll for status, see partial successes, and rerun individual tasks.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.pipeline_run import PipelineRun, PipelineTaskRun

logger = logging.getLogger(__name__)

# ======================================================================
# Task definitions per run type
# ======================================================================

FULL_PIPELINE_TASKS = [
    "zillow_scrape",
    "county_scrape",
    "school_lookup",
    "ai_pass_1",
    "resolver",
    "financial",
    "tax",
    "condition",
    "offer",
    "stress",
    "warning_engine",
    "ai_pass_2",
    "decision_packet",
]

RUN_TYPE_TASKS: dict[str, list[str]] = {
    "full_pipeline": FULL_PIPELINE_TASKS,
    "quick_ingest": [
        "zillow_scrape", "ai_pass_1", "resolver", "financial", "warning_engine",
    ],
    "refresh_zillow": ["zillow_scrape", "ai_pass_1", "resolver"],
    "refresh_county": ["county_scrape", "resolver"],
    "run_deep_comp": ["comp_deep"],
    "rerun_ai": ["ai_pass_1", "ai_pass_2"],
    "rerun_financials": ["financial", "tax", "condition", "offer", "stress"],
}

VALID_RUN_TYPES = set(RUN_TYPE_TASKS.keys())

VALID_TASK_NAMES = {
    "zillow_scrape", "county_scrape", "ai_pass_1", "resolver",
    "financial", "tax", "condition", "offer", "stress",
    "warning_engine", "ai_pass_2", "decision_packet",
    "school_lookup", "comp_quick", "comp_deep",
}


class PipelineOrchestrator:
    """Manages pipeline runs with per-task status tracking."""

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    async def start_run(
        db: AsyncSession,
        property_id: str,
        run_type: str = "full_pipeline",
        initiated_by: str = "user",
    ) -> PipelineRun:
        """Create a PipelineRun + PipelineTaskRun entries for all tasks in the run_type."""
        if run_type not in VALID_RUN_TYPES:
            raise ValueError(f"Invalid run_type: {run_type}. Must be one of {VALID_RUN_TYPES}")

        task_names = RUN_TYPE_TASKS[run_type]

        run = PipelineRun(
            property_id=property_id,
            run_type=run_type,
            status="queued",
            initiated_by=initiated_by,
        )
        db.add(run)
        await db.flush()  # get the run.id

        for task_name in task_names:
            task = PipelineTaskRun(
                pipeline_run_id=run.id,
                task_name=task_name,
                status="pending",
            )
            db.add(task)

        await db.flush()
        return run

    @staticmethod
    async def execute_run(
        db: AsyncSession,
        pipeline_run_id: str,
        *,
        listing_data: dict | None = None,
        county_data: dict | None = None,
        description: str = "",
        current_home: dict | None = None,
        max_monthly_payment: float = 8000,
        max_cash_at_closing: float = 300000,
        assessment_markup_pct: float = 7.0,
        commit_after_tasks: set[str] | None = None,
    ) -> PipelineRun:
        """Execute all tasks in a pipeline run, updating status as each completes.

        For each task:
        1. Set task status = running, started_at = now
        2. Execute the task (try/except)
        3. On success: status = succeeded, duration_ms, result_summary
        4. On failure: status = failed, error_details, increment run.error_count
        5. Continue to next task (don't stop on failure)

        After all tasks:
        - If all succeeded: run.status = succeeded
        - If some failed: run.status = partial_success
        - If all failed: run.status = failed

        commit_after_tasks: optional set of task names. After any task in
            this set completes (success or failure), the function calls
            ``db.commit()`` so partial pipeline results are durable and
            visible to other connections (e.g. the UI) without waiting for
            the slow tasks at the tail (AI Pass 2, decision packet) to
            finish. Used by the background ingest chain to surface AI
            Pass 1 / financial / condition results as soon as they exist.
        """
        result = await db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.tasks))
            .where(PipelineRun.id == pipeline_run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"PipelineRun {pipeline_run_id} not found")

        if run.status == "cancelled":
            return run

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.flush()

        # Build a shared context that tasks can read from / write to
        ctx = _ExecutionContext(
            property_id=run.property_id,
            listing_data=listing_data or {},
            county_data=county_data,
            description=description,
            current_home=current_home,
            max_monthly_payment=max_monthly_payment,
            max_cash_at_closing=max_cash_at_closing,
            assessment_markup_pct=assessment_markup_pct,
        )

        succeeded = 0
        failed = 0

        for task in run.tasks:
            if task.status == "skipped":
                continue

            # Check if the run was cancelled mid-flight
            await db.refresh(run, ["status"])
            if run.status == "cancelled":
                task.status = "skipped"
                await db.flush()
                continue

            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            await db.flush()

            t0 = time.monotonic()
            try:
                summary = await _execute_task(task.task_name, ctx, db)
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                task.status = "succeeded"
                task.completed_at = datetime.now(timezone.utc)
                task.duration_ms = elapsed_ms
                task.result_summary = summary or {}
                succeeded += 1
            except Exception:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                tb = traceback.format_exc()
                logger.exception("Task %s failed in run %s", task.task_name, pipeline_run_id)

                task.status = "failed"
                task.completed_at = datetime.now(timezone.utc)
                task.duration_ms = elapsed_ms
                task.error_details = tb[-2000:]  # cap at 2000 chars
                task.retry_count += 1
                run.error_count += 1
                failed += 1

            await db.flush()

            # Optional mid-run checkpoint commit so partial results are
            # visible to other connections (e.g. the UI) without waiting
            # for slow tail tasks (AI Pass 2, decision packet) to finish.
            if commit_after_tasks and task.task_name in commit_after_tasks:
                await db.commit()
                logger.info(
                    "Pipeline checkpoint commit after task %s (run %s)",
                    task.task_name, pipeline_run_id,
                )

        # Determine final run status
        run.completed_at = datetime.now(timezone.utc)
        total = succeeded + failed
        if failed == 0:
            run.status = "succeeded"
        elif succeeded == 0:
            run.status = "failed"
        else:
            run.status = "partial_success"

        # Store high-level summary
        run.summary_json = {
            "tasks_total": len(run.tasks),
            "tasks_succeeded": succeeded,
            "tasks_failed": failed,
            "tasks_skipped": len(run.tasks) - total,
        }
        # Count warnings from context
        run.warning_count = len(ctx.warnings)

        await db.flush()
        return run

    @staticmethod
    async def rerun_task(
        db: AsyncSession,
        pipeline_run_id: str,
        task_name: str,
    ) -> PipelineTaskRun:
        """Rerun a single task within an existing pipeline run."""
        result = await db.execute(
            select(PipelineTaskRun)
            .where(
                PipelineTaskRun.pipeline_run_id == pipeline_run_id,
                PipelineTaskRun.task_name == task_name,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError(
                f"Task '{task_name}' not found in run {pipeline_run_id}"
            )

        # Load the parent run for context
        run_result = await db.execute(
            select(PipelineRun).where(PipelineRun.id == pipeline_run_id)
        )
        run = run_result.scalar_one()

        # Reset task state
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        task.completed_at = None
        task.duration_ms = None
        task.error_details = None
        task.result_summary = None
        await db.flush()

        # Build minimal context — reruns get whatever data the caller provides
        ctx = _ExecutionContext(property_id=run.property_id)

        t0 = time.monotonic()
        try:
            summary = await _execute_task(task_name, ctx, db)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            task.status = "succeeded"
            task.completed_at = datetime.now(timezone.utc)
            task.duration_ms = elapsed_ms
            task.result_summary = summary or {}
            task.retry_count += 1

            # If the run was partial_success or failed, recheck
            if run.error_count > 0:
                run.error_count = max(0, run.error_count - 1)
            await _recompute_run_status(db, run)
        except Exception:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            tb = traceback.format_exc()
            logger.exception("Rerun of task %s failed", task_name)

            task.status = "failed"
            task.completed_at = datetime.now(timezone.utc)
            task.duration_ms = elapsed_ms
            task.error_details = tb[-2000:]
            task.retry_count += 1

        await db.flush()
        return task

    @staticmethod
    async def cancel_run(db: AsyncSession, pipeline_run_id: str) -> PipelineRun:
        """Cancel a running pipeline. Pending tasks are marked skipped."""
        result = await db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.tasks))
            .where(PipelineRun.id == pipeline_run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"PipelineRun {pipeline_run_id} not found")

        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)

        for task in run.tasks:
            if task.status in ("pending", "running"):
                task.status = "skipped"

        await db.flush()
        return run

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    async def get_run(db: AsyncSession, pipeline_run_id: str) -> dict | None:
        """Get a pipeline run with all task details."""
        result = await db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.tasks))
            .where(PipelineRun.id == pipeline_run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            return None
        return _run_to_dict(run)

    @staticmethod
    async def get_runs_for_property(
        db: AsyncSession,
        property_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent pipeline runs for a property."""
        result = await db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.tasks))
            .where(PipelineRun.property_id == property_id)
            .order_by(PipelineRun.created_at.desc())
            .limit(limit)
        )
        runs = result.scalars().all()
        return [_run_to_dict(r) for r in runs]

    @staticmethod
    async def get_latest_run(
        db: AsyncSession,
        property_id: str,
    ) -> dict | None:
        """Get the most recent pipeline run for a property."""
        result = await db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.tasks))
            .where(PipelineRun.property_id == property_id)
            .order_by(PipelineRun.created_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        if not run:
            return None
        return _run_to_dict(run)


# ======================================================================
# Internal helpers
# ======================================================================


class _ExecutionContext:
    """Mutable bag of data shared across tasks within a single run."""

    def __init__(
        self,
        property_id: str,
        listing_data: dict | None = None,
        county_data: dict | None = None,
        description: str = "",
        current_home: dict | None = None,
        max_monthly_payment: float = 8000,
        max_cash_at_closing: float = 300000,
        assessment_markup_pct: float = 7.0,
    ):
        self.property_id = property_id
        self.listing_data = listing_data or {}
        self.county_data = county_data
        self.description = description
        self.current_home = current_home
        self.max_monthly_payment = max_monthly_payment
        self.max_cash_at_closing = max_cash_at_closing
        self.assessment_markup_pct = assessment_markup_pct

        # Intermediate results produced by earlier tasks, consumed by later ones
        self.ai_extracted: dict = {}
        self.canonical: dict = {}
        self.conflicts: list[dict] = []
        self.unknowns: list[str] = []
        self.math_results: dict = {}
        self.warnings_output: dict = {}
        self.warnings: list[str] = []


async def _persist_analysis(
    db: AsyncSession,
    property_id: str,
    analysis_type: str,
    output: dict,
) -> None:
    """Persist an analysis result as an AnalysisRun record."""
    import hashlib
    import json as _json
    from pipa.models.analysis_models import AnalysisRun

    run = AnalysisRun(
        property_id=property_id,
        analysis_type=analysis_type,
        ruleset_version="1.0.0",
        code_version="0.1.0",
        input_snapshot_hash=hashlib.sha256(
            _json.dumps(output, default=str).encode()
        ).hexdigest(),
        output_json=output,
    )
    db.add(run)
    await db.flush()
    logger.debug("Persisted %s analysis for property %s", analysis_type, property_id)


async def _execute_task(
    task_name: str,
    ctx: _ExecutionContext,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Dispatch a single task by name and return a result summary dict."""
    handler = _TASK_HANDLERS.get(task_name)
    if handler is None:
        logger.warning("No handler registered for task: %s", task_name)
        return {"skipped": True, "reason": f"no handler for {task_name}"}
    return await handler(ctx, db)


# ------------------------------------------------------------------
# Task handler implementations
# ------------------------------------------------------------------


async def _task_zillow_scrape(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Load Zillow data from DB if not provided. Scrape if nothing stored."""
    if not ctx.listing_data:
        logger.info("Loading Zillow data from DB for property %s", ctx.property_id)
        from pipa.models.listing_page import ListingPageSnapshot
        result = await db.execute(
            select(ListingPageSnapshot)
            .where(ListingPageSnapshot.property_id == ctx.property_id)
            .order_by(ListingPageSnapshot.scraped_at.desc())
            .limit(1)
        )
        snap = result.scalar_one_or_none()
        if snap and snap.parsed_fields:
            ctx.listing_data = snap.parsed_fields
            ctx.description = ctx.listing_data.get("description", "")
            logger.info("Loaded %d fields from ListingPageSnapshot", len(ctx.listing_data))
        else:
            logger.info("No stored Zillow data found")

    field_count = len(ctx.listing_data)
    logger.info("Zillow scrape task: %d fields available", field_count)
    return {"fields_received": field_count}


async def _task_county_scrape(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Load county data from DB if not provided."""
    if not ctx.county_data:
        logger.info("Loading county data from DB for property %s", ctx.property_id)
        from pipa.models.source import SourceRecord
        result = await db.execute(
            select(SourceRecord)
            .where(
                SourceRecord.property_id == ctx.property_id,
                SourceRecord.source_name.in_(["loudoun_county", "loudoun_parcel", "county_comp_enrichment"]),
            )
            .order_by(SourceRecord.fetched_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if record and record.raw_payload:
            ctx.county_data = record.raw_payload
            logger.info("Loaded county data from SourceRecord (%d keys)", len(ctx.county_data))
        else:
            logger.info("No stored county data found")

    field_count = len(ctx.county_data) if ctx.county_data else 0
    logger.info("County scrape task: %d fields available", field_count)
    return {"fields_received": field_count}


async def _task_ai_pass_1(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """AI PASS 1: full extraction from listing + county cross-reference.

    Extracts components, red flags, seller motivation from listing text,
    then validates listing claims against county records to find discrepancies
    (sqft, bedrooms, basement, upgrade claims without permits, etc.).
    """
    # Get description from listing_data if not set directly
    if not ctx.description and ctx.listing_data:
        ctx.description = ctx.listing_data.get("description", "")

    if not ctx.description:
        logger.info("AI Pass 1: no description text available")
        return {"skipped": True, "reason": "no description text"}

    from pipa.services.ai_extraction import extract_all_from_listing

    # Build listing facts for cross-reference. Includes:
    #   - core typed fields (price/beds/baths/sqft/year)
    #   - all the normalized facts_and_features fields parsed by the
    #     Zillow scraper (HVAC, materials, foundation, roof, HOA,
    #     parking, rooms, etc.) — see _normalize_facts in zillow.py
    listing_facts = {}
    if ctx.listing_data:
        listing_fact_keys = (
            # Core
            "price", "bedrooms", "bathrooms", "full_bathrooms", "half_bathrooms",
            "main_level_bathrooms", "sqft", "lot_sqft", "lot_sqft_listing",
            "year_built", "home_type", "home_type_listing", "hoa_monthly",
            "description", "above_grade_sqft", "below_grade_sqft", "basement_sqft",
            "total_structure_area", "total_livable_area",
            "finished_above_ground", "finished_below_ground",
            # Construction / materials
            "architectural_style", "property_subtype", "exterior_materials",
            "foundation_type", "roof_material", "zillow_condition",
            "is_new_construction", "builder_model", "builder_name",
            "stories", "levels",
            # HVAC / systems
            "heating_features", "heating_fuel",
            "cooling_features", "cooling_fuel",
            "appliances_included", "laundry_features",
            # Interior
            "interior_features", "flooring", "windows_features",
            "basement_features", "fireplaces_count", "fireplace_features",
            # Exterior / lot
            "patio_porch", "pool_features", "fencing", "lot_features",
            "additional_structures",
            # Parking
            "parking_total_spaces", "parking_features",
            "attached_garage_spaces", "uncovered_spaces", "covered_spaces",
            "carport_spaces",
            # HOA / community
            "has_hoa", "hoa_amenities", "hoa_services", "hoa_name",
            "hoa_frequency", "subdivision", "security_features",
            # Utilities
            "sewer", "water", "utilities", "electric",
            # Tax / financial
            "tax_assessed_value_listing", "annual_tax_listing",
            "price_per_sqft", "date_on_market",
            "listing_agreement", "ownership_type",
            # Identity
            "parcel_number", "parcel_id", "zoning", "special_conditions",
            "region",
            # Per-room data (rich layout info)
            "rooms", "room_types",
            # Accessibility
            "accessibility_features",
        )
        for key in listing_fact_keys:
            if ctx.listing_data.get(key) is not None:
                listing_facts[key] = ctx.listing_data[key]

    # County summary for cross-reference
    county_summary = None
    if ctx.county_data:
        county_summary = ctx.county_data.get("_summary", ctx.county_data)

    result = await extract_all_from_listing(
        description=ctx.description,
        listing_facts=listing_facts if listing_facts else None,
        county_data=county_summary,
    )

    # Store extracted data
    if result.get("components"):
        ctx.ai_extracted["components"] = result["components"]
    if result.get("red_flags"):
        ctx.ai_extracted["red_flags"] = result["red_flags"]
    if result.get("seller_motivation"):
        ctx.ai_extracted["seller_motivation"] = result["seller_motivation"]
    if result.get("validation"):
        ctx.ai_extracted["validation"] = result["validation"]

    # Persist parsed results as AnalysisRun
    await _persist_analysis(db, ctx.property_id, "ai_extraction", result)

    # Persist raw prompts + responses for auditability
    from pipa.services.ai_extraction import get_call_log
    call_log = get_call_log()
    if call_log:
        from pipa.models.source import SourceRecord
        sr = SourceRecord(
            property_id=ctx.property_id,
            source_name="ai_pass_1_prompts",
            source_url=None,
            raw_payload={"calls": call_log},
            fetched_at=datetime.now(timezone.utc),
        )
        db.add(sr)
        await db.flush()
        logger.info("AI Pass 1: stored %d prompt/response pairs", len(call_log))

    counts = {
        "components": len(result.get("components", [])),
        "red_flags": len(result.get("red_flags", [])),
        "has_validation": bool(result.get("validation")),
        "has_motivation": bool(result.get("seller_motivation")),
    }
    logger.info("AI Pass 1: %s", counts)
    return counts


async def _task_resolver(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Deterministic resolver: merge sources into canonical values."""
    from pipa.services.pipeline import _resolve_canonical

    canonical, conflicts, unknowns = _resolve_canonical(
        ctx.listing_data, ctx.county_data, ctx.ai_extracted,
    )
    ctx.canonical = canonical
    ctx.conflicts = conflicts
    ctx.unknowns = unknowns

    # Log key canonical values for debugging
    logger.info(
        "Resolver: year_built=%s, price=%s, sqft=%s, beds=%s, components=%s",
        canonical.get("year_built"),
        canonical.get("asking_price"),
        canonical.get("sqft_above_grade") or canonical.get("sqft_listing"),
        canonical.get("bedrooms"),
        [k for k in canonical if k.startswith("component_")],
    )

    return {
        "canonical_fields": len(canonical),
        "conflicts": len(conflicts),
        "unknowns": len(unknowns),
    }


async def _task_financial(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Financial analysis on canonical data.

    Fetches live mortgage rates from FRED if API key is configured,
    otherwise falls back to config defaults.
    """
    from pipa.analysis.financial import run_financial_analysis
    from pipa.core.dependencies import get_config

    price = _to_float(ctx.canonical.get("asking_price"))
    if not price:
        logger.info("Financial: no asking_price in canonical. Keys: %s", list(ctx.canonical.keys())[:15])
        return {"skipped": True, "reason": "no asking price in canonical data"}

    config = get_config()
    hoa = _to_float(ctx.canonical.get("hoa_monthly")) or 0

    # Try live FRED rates
    rate_override = None
    fred_key = config.api_keys.fred_api_key
    if fred_key:
        try:
            from pipa.clients.fred import FREDClient
            fred = FREDClient(api_key=fred_key)
            live_rate = await fred.get_current_rate(30)
            await fred.close()
            if live_rate:
                rate_override = live_rate
                logger.info("Financial: using live FRED 30yr rate: %.2f%%", live_rate * 100)
        except Exception:
            logger.warning("Financial: FRED rate fetch failed, using defaults")

    result = run_financial_analysis(
        list_price=price, hoa_monthly=hoa,
        down_payment_pcts=[0.10, 0.20],
        term_years=[15, 30],
        rate_override=rate_override,
        property_tax_rate=0.00875,
    )
    ctx.math_results["financial"] = result.model_dump()
    await _persist_analysis(db, ctx.property_id, "financial", result.model_dump())
    return {"scenarios": len(result.model_dump().get("payment_breakdowns", {})), "rate_used": rate_override or "default"}


async def _task_tax(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Tax / sell-vs-rent analysis."""
    if not ctx.current_home:
        return {"skipped": True, "reason": "no current_home data"}

    from pipa.analysis.tax import run_tax_analysis

    price = _to_float(ctx.canonical.get("asking_price")) or 0
    result = run_tax_analysis(
        list_price=price,
        loan_amount=round(price * 0.80),
        property_tax_rate=0.00875,
        current_home_purchase_price=ctx.current_home.get("purchase_price"),
        current_home_estimated_value=ctx.current_home.get("estimated_value"),
        current_home_remaining_mortgage=ctx.current_home.get("remaining_mortgage"),
        years_as_primary=ctx.current_home.get("years_as_primary"),
        estimated_monthly_rent=ctx.current_home.get("estimated_monthly_rent"),
    )
    ctx.math_results["tax"] = result.model_dump()
    return {"computed": True}


async def _task_condition(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Condition scoring and capex forecast."""
    from pipa.analysis.condition import score_property_condition, calculate_capex_forecast
    from datetime import date

    current_year = date.today().year
    components = []
    type_map = {
        "roof": "roof_asphalt_shingle",
        "hvac": "hvac_heat_pump",
        "water_heater": "water_heater_tank",
        "electrical_panel": "electrical_panel",
        "windows": "windows",
        "appliances": "appliances",
    }
    for comp_type, mapped in type_map.items():
        year = _to_int(ctx.canonical.get(f"component_{comp_type}_year"))
        if year:
            components.append({"component_type": mapped, "estimated_install_year": year})

    if not components:
        logger.info("Condition: no components found. canonical keys with 'component': %s",
                     [k for k in ctx.canonical if 'component' in k])
        return {"skipped": True, "reason": "no component data"}

    score = score_property_condition(components, current_year=current_year)
    capex = calculate_capex_forecast(components, current_year=current_year)
    condition_result = {
        "score": score, "capex_forecast": capex, "components": components,
    }
    ctx.math_results["condition"] = condition_result

    # Persist as AnalysisRun so frontend can retrieve it
    from pipa.models.analysis_models import AnalysisRun
    import hashlib, json
    run = AnalysisRun(
        property_id=ctx.property_id,
        analysis_type="condition",
        ruleset_version="1.0.0",
        code_version="0.1.0",
        input_snapshot_hash=hashlib.sha256(json.dumps(components, default=str).encode()).hexdigest(),
        output_json=condition_result,
    )
    db.add(run)
    await db.flush()

    return {"score": score, "components_evaluated": len(components)}


async def _task_offer(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Offer strategy: max bid + appraisal gap."""
    from pipa.analysis.offer import calculate_max_bid, analyze_appraisal_gap

    price = _to_float(ctx.canonical.get("asking_price")) or 0
    assessed = _to_float(ctx.canonical.get("assessed_total"))
    hoa = _to_float(ctx.canonical.get("hoa_monthly")) or 0

    bid = calculate_max_bid(
        appraisal_value=assessed or price,
        max_monthly_payment=ctx.max_monthly_payment,
        max_cash_at_closing=ctx.max_cash_at_closing,
        interest_rate=0.065,
        term_years=30,
        property_tax_rate=0.00875,
        hoa_monthly=hoa,
    )
    offer_result: dict[str, Any] = {"max_bid": bid}

    if assessed:
        gap = analyze_appraisal_gap(
            offer_price=price,
            estimated_appraisal=assessed,
            cash_reserves=ctx.max_cash_at_closing,
        )
        offer_result["appraisal_gap"] = gap

    ctx.math_results["offer"] = offer_result
    return {"max_bid_computed": True}


async def _task_stress(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Stress testing."""
    from pipa.analysis.stress_testing import run_stress_tests

    price = _to_float(ctx.canonical.get("asking_price")) or 0
    if not price:
        return {"skipped": True, "reason": "no asking price"}

    loan_80 = round(price * 0.80)
    stress = run_stress_tests(list_price=price, loan_amount=loan_80, interest_rate=0.065)
    ctx.math_results["stress_tests"] = stress
    return {"scenarios_tested": len(stress) if isinstance(stress, list) else 1}


async def _task_warning_engine(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Deterministic warning engine."""
    from pipa.services.pipeline import _generate_warnings

    warnings_output = _generate_warnings(
        ctx.canonical, ctx.conflicts, ctx.unknowns, ctx.math_results,
    )
    ctx.warnings_output = warnings_output
    ctx.warnings = warnings_output.get("warnings", [])
    return {
        "pursue_signal": warnings_output.get("pursue_signal"),
        "blockers": len(warnings_output.get("blockers", [])),
        "warnings": len(warnings_output.get("warnings", [])),
    }


async def _task_ai_pass_2(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """AI PASS 2: interpretation and narrative.

    Feeds ALL available data to Claude — listing, county, comps, financial,
    condition, schools, flood, warnings — for a comprehensive buyer opinion.
    """
    import shutil

    # Check if Claude CLI is available
    claude_bin = shutil.which("claude")
    if not claude_bin:
        logger.warning("AI Pass 2: Claude CLI not found, skipping")
        return {"skipped": True, "reason": "claude CLI not found"}

    try:
        from pipa.services.ai_extraction import generate_property_summary

        # Load comp data from DB (quick comp + deep comp if available)
        comp_data = None
        try:
            from pipa.services.comp_service import CompService
            stored = await CompService.get_stored_results(db, ctx.property_id)
            if stored:
                comp_data = stored.get("quick_comp") or stored.get("deep_comp")
                # Prefer deep comp if both available
                if stored.get("deep_comp") and stored["deep_comp"].get("sold_comps"):
                    comp_data = stored["deep_comp"]
        except Exception:
            logger.debug("Could not load comp data for AI Pass 2")

        # Load school data from DB
        school_data = None
        try:
            from pipa.models.source import SourceRecord
            school_result = await db.execute(
                select(SourceRecord).where(
                    SourceRecord.property_id == ctx.property_id,
                    SourceRecord.source_name == "lcps_official",
                ).order_by(SourceRecord.fetched_at.desc()).limit(1)
            )
            school_record = school_result.scalar_one_or_none()
            if school_record and school_record.raw_payload:
                school_data = school_record.raw_payload
        except Exception:
            logger.debug("Could not load school data for AI Pass 2")

        # Load flood zone data
        flood_data = None
        try:
            from pipa.models.source import SourceRecord
            flood_result = await db.execute(
                select(SourceRecord).where(
                    SourceRecord.property_id == ctx.property_id,
                    SourceRecord.source_name == "fema_flood_zone",
                ).order_by(SourceRecord.fetched_at.desc()).limit(1)
            )
            flood_record = flood_result.scalar_one_or_none()
            if flood_record and flood_record.raw_payload:
                flood_data = flood_record.raw_payload
        except Exception:
            logger.debug("Could not load flood data for AI Pass 2")

        # Use a shorter timeout to avoid blocking the pipeline
        summary = await asyncio.wait_for(
            generate_property_summary(
                property_data=ctx.canonical,
                county_data=ctx.county_data,
                price_benchmarks=ctx.math_results.get("price_benchmarks"),
                comp_data=comp_data,
                financial_data=ctx.math_results.get("financial"),
                condition_data=ctx.math_results.get("condition"),
                school_data=school_data,
                flood_data=flood_data,
                warnings=ctx.warnings,
            ),
            timeout=60,  # 60 second max — more data to process
        )
        ctx.math_results["ai_interpretation"] = summary
        await _persist_analysis(db, ctx.property_id, "ai_interpretation", summary)

        # Store raw prompts + responses
        from pipa.services.ai_extraction import get_call_log
        call_log = get_call_log()
        if call_log:
            from pipa.models.source import SourceRecord
            sr = SourceRecord(
                property_id=ctx.property_id,
                source_name="ai_pass_2_prompts",
                source_url=None,
                raw_payload={"calls": call_log},
                fetched_at=datetime.now(timezone.utc),
            )
            db.add(sr)
            await db.flush()

        return {"has_summary": bool(summary)}
    except asyncio.TimeoutError:
        logger.warning("AI Pass 2: Claude CLI timed out after 45s, skipping")
        return {"skipped": True, "reason": "claude CLI timed out — may be competing with active session"}


async def _task_decision_packet(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Decision packet assembly."""
    from pipa.services.pipeline import _assemble_decision_packet

    packet = _assemble_decision_packet(
        ctx.canonical,
        ctx.math_results,
        ctx.warnings_output,
        ctx.ai_extracted,
        ctx.math_results.get("ai_interpretation", {}),
    )
    return {"sections": list(packet.keys())}


async def _task_school_lookup(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """LCPS school boundary lookup — uses cached data if available, scrapes only if missing."""
    from pipa.models.source import SourceRecord

    # Check for cached school data first (same pattern as zillow/county)
    result = await db.execute(
        select(SourceRecord).where(
            SourceRecord.property_id == ctx.property_id,
            SourceRecord.source_name == "lcps_official",
        ).order_by(SourceRecord.fetched_at.desc()).limit(1)
    )
    cached = result.scalar_one_or_none()
    if cached and cached.raw_payload:
        data = cached.raw_payload
        schools_found = sum(1 for k in ("elementary", "middle", "high") if data.get(k))
        logger.info("School lookup: using cached data (%d schools found)", schools_found)
        return {"schools_found": schools_found, "source": "cached"}

    # No cached data — scrape fresh
    logger.info("School lookup: no cached data, scraping LCPS...")
    from pipa.services.school_service import SchoolService

    try:
        data = await SchoolService.refresh(db, ctx.property_id, headless=False)
        if data.get("_error"):
            return {"skipped": True, "reason": data["_error"]}

        # Cross-reference against Zillow
        xref = await SchoolService.cross_reference_zillow(db, ctx.property_id)

        schools_found = sum(1 for k in ("elementary", "middle", "high") if data.get(k))
        return {
            "schools_found": schools_found,
            "mismatches": len(xref.get("mismatches", [])),
            "boundary_change": xref.get("boundary_change_warning", False),
            "source": "fresh_scrape",
        }
    except Exception as e:
        logger.exception("School lookup failed")
        return {"skipped": True, "reason": str(e)[:200]}


async def _task_comp_quick(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Quick comp search — placeholder for future implementation."""
    return {"skipped": True, "reason": "not yet implemented"}


async def _task_comp_deep(ctx: _ExecutionContext, db: AsyncSession) -> dict:
    """Deep comp analysis — placeholder for future implementation."""
    return {"skipped": True, "reason": "not yet implemented"}


# Handler dispatch table
_TASK_HANDLERS: dict[str, Any] = {
    "zillow_scrape": _task_zillow_scrape,
    "county_scrape": _task_county_scrape,
    "ai_pass_1": _task_ai_pass_1,
    "resolver": _task_resolver,
    "financial": _task_financial,
    "tax": _task_tax,
    "condition": _task_condition,
    "offer": _task_offer,
    "stress": _task_stress,
    "warning_engine": _task_warning_engine,
    "ai_pass_2": _task_ai_pass_2,
    "decision_packet": _task_decision_packet,
    "school_lookup": _task_school_lookup,
    "comp_quick": _task_comp_quick,
    "comp_deep": _task_comp_deep,
}


async def _recompute_run_status(db: AsyncSession, run: PipelineRun) -> None:
    """Recompute run-level status from task statuses after a rerun."""
    result = await db.execute(
        select(PipelineTaskRun)
        .where(PipelineTaskRun.pipeline_run_id == run.id)
    )
    tasks = result.scalars().all()

    statuses = [t.status for t in tasks]
    failed = statuses.count("failed")
    succeeded = statuses.count("succeeded")

    if failed == 0 and succeeded > 0:
        run.status = "succeeded"
    elif succeeded == 0 and failed > 0:
        run.status = "failed"
    elif succeeded > 0 and failed > 0:
        run.status = "partial_success"

    run.error_count = failed
    run.summary_json = {
        "tasks_total": len(tasks),
        "tasks_succeeded": succeeded,
        "tasks_failed": failed,
        "tasks_skipped": statuses.count("skipped"),
    }
    await db.flush()


def _run_to_dict(run: PipelineRun) -> dict:
    """Serialize a PipelineRun + tasks to a plain dict."""
    return {
        "id": run.id,
        "property_id": run.property_id,
        "run_type": run.run_type,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "initiated_by": run.initiated_by,
        "summary_json": run.summary_json,
        "error_count": run.error_count,
        "warning_count": run.warning_count,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "tasks": [
            {
                "id": t.id,
                "pipeline_run_id": t.pipeline_run_id,
                "task_name": t.task_name,
                "status": t.status,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "duration_ms": t.duration_ms,
                "retry_count": t.retry_count,
                "result_summary": t.result_summary,
                "error_details": t.error_details,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in run.tasks
        ],
    }


# ======================================================================
# Helpers (copied from pipeline.py for isolation)
# ======================================================================


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None
