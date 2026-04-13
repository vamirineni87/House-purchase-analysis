"""Rent vs Sell API router.

Routes:
  POST   /rent-vs-sell/calculate
  POST   /rent-vs-sell/sensitivity

  GET    /rent-vs-sell/prefill/{property_id}

  GET    /rent-vs-sell/current-home-profiles
  POST   /rent-vs-sell/current-home-profiles
  PUT    /rent-vs-sell/current-home-profiles/{id}
  DELETE /rent-vs-sell/current-home-profiles/{id}
  POST   /rent-vs-sell/current-home-profiles/bootstrap-default

  GET    /rent-vs-sell/runs
  GET    /rent-vs-sell/runs/{id}
  POST   /rent-vs-sell/runs
  PUT    /rent-vs-sell/runs/{id}
  DELETE /rent-vs-sell/runs/{id}
  POST   /rent-vs-sell/runs/{id}/duplicate
  POST   /rent-vs-sell/runs/compare
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.analysis import rent_vs_sell as rvs
from pipa.core.dependencies import get_db
from pipa.models.listing_page import ListingPageSnapshot
from pipa.models.property import Property
from pipa.models.rent_vs_sell import CurrentHomeProfile, RentVsSellRun

logger = logging.getLogger(__name__)

# Keys we're willing to snapshot from a target property's listing. Anything
# outside this list is dropped silently so future parser additions (agent
# contact info, etc.) don't leak into saved runs.
_LISTING_SNAPSHOT_ALLOW = frozenset((
    "price", "list_price", "hoa_fee", "hoa_monthly",
    "property_tax", "annual_tax", "monthly_property_tax",
    "insurance", "annual_insurance", "monthly_insurance",
    "bedrooms", "bathrooms", "sqft", "year_built", "lot_size",
))
from pipa.schemas.rent_vs_sell import (
    CalculateRequest,
    CalculateResponse,
    CurrentHomeProfileIn,
    CurrentHomeProfileOut,
    PrefillResponse,
    RunCompareRequest,
    RunDetail,
    RunIn,
    RunSummary,
    SensitivityRequest,
    SensitivityResponse,
)

router = APIRouter(tags=["rent_vs_sell"], prefix="/rent-vs-sell")


# Starter defaults for the bootstrap endpoint and for fallback new runs.
_STARTER_CONFIG = {
    "value_today": 790000,
    "basis": 478000,
    "loan_balance": 295413,
    "mortgage_rate": 0.025,
    "monthly_principal_interest": 1245,
    "monthly_taxes": 620,
    "monthly_insurance": 120,
    "monthly_hoa": 0,
    "monthly_misc_owner_paid": 80,
    "insurance_conversion_bump_pct": 0.15,
    "initial_lease_up_vacancy_months": 1.0,
    "sell_cost_pct_now": 0.07,
    "current_home_sell_cost_pct_future": 0.07,
    "monthly_rent_base": 3500,
    "land_pct": 0.2974,
    "building_pct": 0.7026,
    "move_out_month": "2026-05",
    "rent_start_month": "2026-06",
    "reserve_months_per_year": 2,
    "self_manage": True,
    "property_management_pct": 0.00,
    "vacancy_months_per_year_base": 0.5,
    "bad_debt_pct_of_gross_rent": 0.005,
    "leasing_fee_pct_of_annual_rent": 0.05,
    "turnover_cost_per_event": 2500,
    "turnover_frequency_months": 24,
    "routine_maintenance_pct_of_rent": 0.05,
    "maintenance_inflation_annual_pct": 0.03,
    "current_home_tax_growth_annual_pct": 0.03,
    "current_home_insurance_growth_annual_pct": 0.05,
    "current_home_hoa_growth_annual_pct": 0.03,
    "current_home_misc_growth_annual_pct": 0.03,
    "sale_prep_cost_flat": 3000,
    "pre_sale_vacancy_months": 0.5,
    "concession_pct_at_sale": 0.00,
    "total_value_change_5y": 0.10,
    "total_value_change_10y": 0.20,
    "total_rent_change_5y": 0.0,
    "total_rent_change_10y": 0.0,
}

# ─────────────────────────────────────────────────────────────────────
# Compute endpoints
# ─────────────────────────────────────────────────────────────────────


@router.post("/calculate", response_model=CalculateResponse)
async def calculate(req: CalculateRequest):
    """Compute all four strategies from one assumption set."""
    try:
        return rvs.compute_full_analysis(req.assumptions)
    except (ValueError, KeyError, TypeError) as e:
        # User-input errors
        raise HTTPException(status_code=400, detail=f"Invalid assumptions: {e}")
    except Exception:
        # Real bug — log the stack, return a static message
        logger.exception("compute_full_analysis crashed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


# In-memory sensitivity cache — single-user PIPA, fine to keep in process.
# Keyed by (CALC_VERSION, request hash) so bumping the engine version
# automatically invalidates stale cached results.
_SENSITIVITY_CACHE: dict[str, dict] = {}
_SENSITIVITY_CACHE_MAX = 64


def _sensitivity_cache_key(assumptions: dict, preset: str, comparator: str, horizon: str) -> str:
    subset_keys = (
        "current_home", "new_home", "refinance", "taxes",
        "ownership_cost_growth", "reinvestment", "new_home_drag",
        "current_home_capex_items", "new_home_capex_items", "modeling",
    )
    subset = {k: assumptions.get(k) for k in subset_keys}
    payload = json.dumps(
        {
            "v": rvs.CALC_VERSION,
            "a": subset,
            "p": preset,
            "c": comparator,
            "h": horizon,
        },
        sort_keys=True,
        default=repr,  # distinguishable from ambiguous str() on custom types
    )
    return hashlib.sha1(payload.encode()).hexdigest()


@router.post("/sensitivity", response_model=SensitivityResponse)
async def sensitivity(req: SensitivityRequest):
    """Compute a sensitivity heatmap. Cached by request hash."""
    key = _sensitivity_cache_key(req.assumptions, req.preset, req.comparator, req.horizon)
    if key in _SENSITIVITY_CACHE:
        return _SENSITIVITY_CACHE[key]
    try:
        result = rvs.compute_sensitivity_grid(
            req.assumptions,
            preset=req.preset,
            comparator=req.comparator,
            horizon=req.horizon,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("compute_sensitivity_grid crashed")
        raise HTTPException(status_code=500, detail="Internal sensitivity error")
    # Simple FIFO eviction
    if len(_SENSITIVITY_CACHE) >= _SENSITIVITY_CACHE_MAX:
        _SENSITIVITY_CACHE.pop(next(iter(_SENSITIVITY_CACHE)))
    _SENSITIVITY_CACHE[key] = result
    return result


# ─────────────────────────────────────────────────────────────────────
# Prefill from PIPA property
# ─────────────────────────────────────────────────────────────────────


def _num(val: Any) -> float | None:
    """Coerce a JSON value to a finite float, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


SOURCE_PREFILL_VERSION = "1.0.0"


@router.get("/prefill/{property_id}", response_model=PrefillResponse)
async def prefill_from_property(property_id: str, db: AsyncSession = Depends(get_db)):
    """Pull the most recent scraped listing fields and convert to new_home inputs."""
    prop = await db.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    result = await db.execute(
        select(ListingPageSnapshot)
        .where(ListingPageSnapshot.property_id == property_id)
        .order_by(ListingPageSnapshot.scraped_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()

    new_home: dict[str, Any] = {
        "base_down_pct": 0.20,
        "initial_rate": 0.0646,
        "loan_term_years": 30,
        "monthly_hoa": 0,
        "monthly_taxes": 0,
        "monthly_insurance": 0,
    }
    # Defensive: `parsed_fields` is typed as JSON on the ORM model, but nothing
    # enforces it being a dict (historical rows, future parser bugs, etc.).
    pf = snap.parsed_fields if snap else None
    if isinstance(pf, dict):
        price = _num(pf.get("price")) or _num(pf.get("list_price"))
        if price is not None:
            new_home["purchase_price"] = price

        hoa = _num(pf.get("hoa_monthly")) or _num(pf.get("hoa_fee"))
        if hoa is not None:
            new_home["monthly_hoa"] = hoa

        prop_tax_monthly = _num(pf.get("monthly_property_tax"))
        prop_tax_annual = _num(pf.get("property_tax")) or _num(pf.get("annual_tax"))
        if prop_tax_monthly is not None:
            new_home["monthly_taxes"] = prop_tax_monthly
        elif prop_tax_annual is not None:
            new_home["monthly_taxes"] = prop_tax_annual / 12.0

        ins_monthly = _num(pf.get("monthly_insurance"))
        ins_annual = _num(pf.get("insurance")) or _num(pf.get("annual_insurance"))
        if ins_monthly is not None:
            new_home["monthly_insurance"] = ins_monthly
        elif ins_annual is not None:
            new_home["monthly_insurance"] = ins_annual / 12.0

    return {"new_home": new_home, "source_prefill_version": SOURCE_PREFILL_VERSION}


# ─────────────────────────────────────────────────────────────────────
# Current home profiles
# ─────────────────────────────────────────────────────────────────────


def _profile_to_out(p: CurrentHomeProfile) -> CurrentHomeProfileOut:
    return CurrentHomeProfileOut(
        id=p.id,
        name=p.name,
        is_default=p.is_default,
        config_json=p.config_json,
        created_at=p.created_at.isoformat() if p.created_at else None,
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
    )


@router.get("/current-home-profiles", response_model=list[CurrentHomeProfileOut])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    """Return all saved current-home profiles (no write-on-read seeding)."""
    result = await db.execute(
        select(CurrentHomeProfile).order_by(CurrentHomeProfile.created_at.asc())
    )
    return [_profile_to_out(p) for p in result.scalars().all()]


@router.post("/current-home-profiles", response_model=CurrentHomeProfileOut)
async def create_profile(body: CurrentHomeProfileIn, db: AsyncSession = Depends(get_db)):
    if body.is_default:
        # Clear existing defaults
        existing = await db.execute(
            select(CurrentHomeProfile).where(CurrentHomeProfile.is_default.is_(True))
        )
        for p in existing.scalars().all():
            p.is_default = False
    profile = CurrentHomeProfile(
        id=str(uuid.uuid4()),
        name=body.name,
        is_default=body.is_default,
        config_json=body.config_json,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _profile_to_out(profile)


@router.put("/current-home-profiles/{profile_id}", response_model=CurrentHomeProfileOut)
async def update_profile(
    profile_id: str, body: CurrentHomeProfileIn, db: AsyncSession = Depends(get_db)
):
    profile = await db.get(CurrentHomeProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.name = body.name
    profile.is_default = body.is_default
    profile.config_json = body.config_json
    await db.commit()
    await db.refresh(profile)
    return _profile_to_out(profile)


@router.delete("/current-home-profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    profile = await db.get(CurrentHomeProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.delete(profile)
    await db.commit()


@router.post("/current-home-profiles/bootstrap-default", response_model=CurrentHomeProfileOut)
async def bootstrap_default_profile(db: AsyncSession = Depends(get_db)):
    """Insert the starter White Cap Ter profile if none exists."""
    # If any default already exists, return it
    existing = await db.execute(
        select(CurrentHomeProfile).where(CurrentHomeProfile.is_default.is_(True)).limit(1)
    )
    p = existing.scalar_one_or_none()
    if p:
        return _profile_to_out(p)
    profile = CurrentHomeProfile(
        id=str(uuid.uuid4()),
        name="43629 White Cap Ter",
        is_default=True,
        config_json=_STARTER_CONFIG,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _profile_to_out(profile)


# ─────────────────────────────────────────────────────────────────────
# Saved runs
# ─────────────────────────────────────────────────────────────────────


def _run_to_summary(r: RentVsSellRun) -> RunSummary:
    return RunSummary(
        id=r.id,
        name=r.name,
        scenario_label=r.scenario_label,
        target_property_id=r.target_property_id,
        comparison_horizon_years=r.comparison_horizon_years,
        summary_json=r.summary_json,
        calc_version=r.calc_version,
        created_at=r.created_at.isoformat() if r.created_at else None,
        updated_at=r.updated_at.isoformat() if r.updated_at else None,
    )


def _run_to_detail(r: RentVsSellRun, recomputed: bool = False) -> RunDetail:
    return RunDetail(
        id=r.id,
        name=r.name,
        notes=r.notes,
        scenario_label=r.scenario_label,
        target_property_id=r.target_property_id,
        current_home_profile_id=r.current_home_profile_id,
        comparison_horizon_years=r.comparison_horizon_years,
        summary_json=r.summary_json,
        assumptions_json=r.assumptions_json,
        outputs_json=r.outputs_json,
        target_property_snapshot_json=r.target_property_snapshot_json,
        current_home_snapshot_json=r.current_home_snapshot_json,
        created_from_property_detail=r.created_from_property_detail,
        source_prefill_version=r.source_prefill_version,
        calc_version=r.calc_version,
        input_schema_version=r.input_schema_version,
        recomputed=recomputed,
        created_at=r.created_at.isoformat() if r.created_at else None,
        updated_at=r.updated_at.isoformat() if r.updated_at else None,
    )


def _build_summary_from_outputs(outputs: dict) -> dict:
    """Extract headline metrics for the saved-runs list page.

    Includes both 5Y and 10Y sell_now net worth so the UI can display the
    correct column regardless of the run's horizon.
    """
    strategies = outputs.get("strategies", {})
    return {
        "lean": outputs.get("lean"),
        "sell_now_net_worth_5y": (strategies.get("sell_now") or {}).get("net_worth_end"),
        "sell_now_net_worth_10y": (strategies.get("sell_now_10y") or {}).get("net_worth_end"),
        "keep_5y_net_worth": (strategies.get("keep_5y") or {}).get("net_worth_end"),
        "keep_10y_net_worth": (strategies.get("keep_10y") or {}).get("net_worth_end"),
        "rent_then_sell_net_worth": (strategies.get("rent_then_sell") or {}).get("net_worth_end"),
        "monthly_stress_delta": outputs.get("top_line", {}).get("monthly_stress_delta"),
    }


async def _snapshot_target_property(db: AsyncSession, property_id: str | None) -> dict | None:
    """Freeze an allow-listed subset of the target property's listing fields.

    The allow-list protects saved runs from silently inheriting any future
    `parsed_fields` additions (owner name, agent phone, showing instructions,
    etc.). Only numeric fields used by the rent-vs-sell engine are captured.
    """
    if not property_id:
        return None
    prop = await db.get(Property, property_id)
    if not prop:
        return None
    result = await db.execute(
        select(ListingPageSnapshot)
        .where(ListingPageSnapshot.property_id == property_id)
        .order_by(ListingPageSnapshot.scraped_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    out: dict[str, Any] = {"property_id": property_id}
    pf = snap.parsed_fields if snap else None
    if isinstance(pf, dict):
        snapshot_fields: dict[str, Any] = {}
        for k in _LISTING_SNAPSHOT_ALLOW:
            if k in pf:
                v = _num(pf.get(k))
                if v is not None:
                    snapshot_fields[k] = v
        if snapshot_fields:
            out["fields"] = snapshot_fields
        out["scraped_at"] = snap.scraped_at.isoformat() if snap.scraped_at else None
        out["source_site"] = snap.source_site
    return out


async def _snapshot_profile(db: AsyncSession, profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    p = await db.get(CurrentHomeProfile, profile_id)
    if not p:
        return None
    return {"id": p.id, "name": p.name, "config_json": p.config_json}


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RentVsSellRun).order_by(RentVsSellRun.updated_at.desc())
    )
    return [_run_to_summary(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(RentVsSellRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    recomputed = False
    # Stale detection: recompute if calc_version changed
    if run.calc_version != rvs.CALC_VERSION or run.outputs_json is None:
        if not run.assumptions_json:
            raise HTTPException(
                status_code=500,
                detail="Run has no assumptions_json and cannot be recomputed",
            )
        try:
            outputs = rvs.compute_full_analysis(run.assumptions_json)
        except Exception:
            logger.exception("get_run recompute failed for %s", run_id)
            raise HTTPException(status_code=500, detail="Internal recompute error")
        run.outputs_json = outputs
        run.summary_json = _build_summary_from_outputs(outputs)
        run.calc_version = rvs.CALC_VERSION
        run.input_schema_version = rvs.INPUT_SCHEMA_VERSION
        await db.commit()
        await db.refresh(run)
        recomputed = True
    return _run_to_detail(run, recomputed=recomputed)


@router.post("/runs", response_model=RunDetail)
async def create_run(body: RunIn, db: AsyncSession = Depends(get_db)):
    try:
        outputs = rvs.compute_full_analysis(body.assumptions_json)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid assumptions: {e}")
    except Exception:
        logger.exception("create_run compute failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")

    target_snapshot = await _snapshot_target_property(db, body.target_property_id)
    profile_snapshot = await _snapshot_profile(db, body.current_home_profile_id)

    run = RentVsSellRun(
        id=str(uuid.uuid4()),
        name=body.name,
        notes=body.notes,
        scenario_label=body.scenario_label,
        target_property_id=body.target_property_id,
        current_home_profile_id=body.current_home_profile_id,
        comparison_horizon_years=body.comparison_horizon_years,
        assumptions_json=body.assumptions_json,
        target_property_snapshot_json=target_snapshot,
        current_home_snapshot_json=profile_snapshot,
        created_from_property_detail=body.created_from_property_detail,
        source_prefill_version=body.source_prefill_version,
        calc_version=rvs.CALC_VERSION,
        input_schema_version=rvs.INPUT_SCHEMA_VERSION,
        summary_json=_build_summary_from_outputs(outputs),
        outputs_json=outputs,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return _run_to_detail(run)


@router.put("/runs/{run_id}", response_model=RunDetail)
async def update_run(run_id: str, body: RunIn, db: AsyncSession = Depends(get_db)):
    run = await db.get(RentVsSellRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        outputs = rvs.compute_full_analysis(body.assumptions_json)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid assumptions: {e}")
    except Exception:
        logger.exception("update_run compute failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")
    run.name = body.name
    run.notes = body.notes
    run.scenario_label = body.scenario_label
    run.target_property_id = body.target_property_id
    run.current_home_profile_id = body.current_home_profile_id
    run.comparison_horizon_years = body.comparison_horizon_years
    run.assumptions_json = body.assumptions_json
    run.calc_version = rvs.CALC_VERSION
    run.input_schema_version = rvs.INPUT_SCHEMA_VERSION
    run.summary_json = _build_summary_from_outputs(outputs)
    run.outputs_json = outputs
    if body.target_property_id:
        run.target_property_snapshot_json = await _snapshot_target_property(
            db, body.target_property_id
        )
    if body.current_home_profile_id:
        run.current_home_snapshot_json = await _snapshot_profile(
            db, body.current_home_profile_id
        )
    await db.commit()
    await db.refresh(run)
    return _run_to_detail(run)


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(RentVsSellRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    await db.delete(run)
    await db.commit()


@router.post("/runs/{run_id}/duplicate", response_model=RunDetail)
async def duplicate_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(RentVsSellRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    new_run = RentVsSellRun(
        id=str(uuid.uuid4()),
        name=f"{run.name} (copy)",
        notes=run.notes,
        scenario_label=run.scenario_label,
        target_property_id=run.target_property_id,
        current_home_profile_id=run.current_home_profile_id,
        comparison_horizon_years=run.comparison_horizon_years,
        assumptions_json=run.assumptions_json,
        target_property_snapshot_json=run.target_property_snapshot_json,
        current_home_snapshot_json=run.current_home_snapshot_json,
        created_from_property_detail=run.created_from_property_detail,
        source_prefill_version=run.source_prefill_version,
        calc_version=run.calc_version,
        input_schema_version=run.input_schema_version,
        summary_json=run.summary_json,
        outputs_json=run.outputs_json,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)
    return _run_to_detail(new_run)


@router.post("/runs/compare")
async def compare_runs(body: RunCompareRequest, db: AsyncSession = Depends(get_db)):
    # Single query for all requested runs (no N+1)
    result = await db.execute(
        select(RentVsSellRun).where(RentVsSellRun.id.in_(body.run_ids))
    )
    runs_by_id = {r.id: r for r in result.scalars().all()}
    missing = [rid for rid in body.run_ids if rid not in runs_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Run(s) not found: {missing}")

    runs_out: list[dict] = []
    any_recomputed = False
    # Preserve the caller's order
    for rid in body.run_ids:
        run = runs_by_id[rid]
        recomputed = False
        if run.calc_version != rvs.CALC_VERSION or run.outputs_json is None:
            if not run.assumptions_json:
                raise HTTPException(
                    status_code=500,
                    detail=f"Run {rid} has empty assumptions_json and cannot be recomputed",
                )
            try:
                outputs = rvs.compute_full_analysis(run.assumptions_json)
            except Exception:
                logger.exception("compare_runs recompute failed for %s", rid)
                raise HTTPException(status_code=500, detail="Internal recompute error")
            run.outputs_json = outputs
            run.summary_json = _build_summary_from_outputs(outputs)
            run.calc_version = rvs.CALC_VERSION
            run.input_schema_version = rvs.INPUT_SCHEMA_VERSION
            recomputed = True
            any_recomputed = True
        runs_out.append(
            {
                "id": run.id,
                "name": run.name,
                "scenario_label": run.scenario_label,
                "assumptions_json": run.assumptions_json,
                "outputs_json": run.outputs_json,
                "recomputed": recomputed,
            }
        )
    if any_recomputed:
        await db.commit()
    return {"runs": runs_out}
