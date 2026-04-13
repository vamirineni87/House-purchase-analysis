"""Pydantic schemas for the Rent vs Sell API.

The inputs dict is deliberately loose — every key has a default in the
engine so the frontend can POST partial assumptions without failing
validation. What we DO validate:
  - payload size (reject 256 KB+ blobs; nobody is hand-editing that much)
  - non-finite floats (inf/nan corrupt the engine and break JSON serialization)
  - month-string format (YYYY-MM only; loose formats silently produce
    nonsense horizons because _month_diff defaults to 0)
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

_MAX_ASSUMPTIONS_BYTES = 256 * 1024  # 256 KB of JSON — ~100x real payload
_MAX_CAPEX_ITEMS = 100               # per-list cap — protects engine loops
_MONTH_RE = re.compile(r"^\d{4}-\d{1,2}$")


_MONTH_KEYS = frozenset((
    "move_out_month", "rent_start_month", "rent_then_sell_date", "purchase_date",
))


def _walk_and_clean(obj: Any, path: str = "") -> Any:
    """Walk a nested structure, strip non-finite floats in place, and raise
    ValueError for bad months / oversized strings / oversized collections.

    Non-finite floats are replaced with 0.0 (caller will never see `inf` or
    `nan` in the returned dict). This matters because FastAPI's validation
    error responses echo the raw input — a pristine dict is needed so the
    error itself serializes cleanly even when the cause is a bad month.
    """
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return 0.0
        return obj
    if isinstance(obj, (int, bool)) or obj is None:
        return obj
    if isinstance(obj, str):
        if len(obj) > 512:
            raise ValueError(f"String too long at {path or '<root>'}")
        return obj
    if isinstance(obj, list):
        if len(obj) > 256:
            raise ValueError(f"List too long at {path or '<root>'}")
        for i in range(len(obj)):
            obj[i] = _walk_and_clean(obj[i], f"{path}[{i}]")
        return obj
    if isinstance(obj, dict):
        if len(obj) > 256:
            raise ValueError(f"Dict too wide at {path or '<root>'}")
        for k, v in list(obj.items()):
            if not isinstance(k, str):
                raise ValueError(f"Non-string key at {path}")
            child_path = f"{path}.{k}" if path else k
            # Month-string keys
            if k in _MONTH_KEYS:
                if v is None or v == "":
                    continue
                if not isinstance(v, str) or not _MONTH_RE.match(v):
                    raise ValueError(f"Invalid month format at {child_path}: expected YYYY-MM")
            obj[k] = _walk_and_clean(v, child_path)
        return obj
    raise ValueError(f"Unsupported type at {path or '<root>'}: {type(obj).__name__}")


def _validate_assumptions(v: Any) -> dict:
    if not isinstance(v, dict):
        raise ValueError("assumptions must be an object")
    # Clean non-finite floats in place first, so any later ValueError can
    # round-trip cleanly through FastAPI's error serializer.
    _walk_and_clean(v)
    # Size check (cheap)
    try:
        size = len(json.dumps(v, default=str))
    except (TypeError, ValueError):
        raise ValueError("assumptions not JSON-serializable")
    if size > _MAX_ASSUMPTIONS_BYTES:
        raise ValueError(f"assumptions too large ({size} bytes > {_MAX_ASSUMPTIONS_BYTES})")
    # Capex list caps — the engine iterates these lists inside every
    # bisection clone. A malicious payload with 5000 items × 50 breakeven
    # passes per /calculate would pin CPU.
    for key in ("current_home_capex_items", "new_home_capex_items"):
        items = v.get(key)
        if items is not None:
            if not isinstance(items, list):
                raise ValueError(f"{key} must be a list")
            if len(items) > _MAX_CAPEX_ITEMS:
                raise ValueError(
                    f"{key} has {len(items)} entries; max is {_MAX_CAPEX_ITEMS}"
                )
    return v


# ─────────────────────────────────────────────────────────────────────
# Compute
# ─────────────────────────────────────────────────────────────────────


class CalculateRequest(BaseModel):
    """Compute all four strategies from one assumption set."""

    assumptions: dict[str, Any]

    @field_validator("assumptions")
    @classmethod
    def _validate_assumptions(cls, v):
        return _validate_assumptions(v)


class CalculateResponse(BaseModel):
    strategies: dict[str, Any]
    top_line: dict[str, Any]
    lean: str
    calc_version: str
    input_schema_version: str


_PRESETS = frozenset(("value_x_rent", "value_x_capex", "value_x_refi", "rent_x_vacancy", "rent_x_reinvest"))
_COMPARATORS = frozenset(("sell_vs_keep_5y", "sell_vs_keep_10y", "sell_vs_rent_then_sell"))
_HORIZONS = frozenset(("5y", "10y"))


class SensitivityRequest(BaseModel):
    assumptions: dict[str, Any]
    preset: str = Field(default="value_x_rent")
    comparator: str = Field(default="sell_vs_keep_5y")
    horizon: str = Field(default="5y")

    @field_validator("assumptions")
    @classmethod
    def _validate_assumptions(cls, v):
        return _validate_assumptions(v)

    @field_validator("preset")
    @classmethod
    def _validate_preset(cls, v):
        if v not in _PRESETS:
            raise ValueError(f"Unknown preset: {v}")
        return v

    @field_validator("comparator")
    @classmethod
    def _validate_comparator(cls, v):
        if v not in _COMPARATORS:
            raise ValueError(f"Unknown comparator: {v}")
        return v

    @field_validator("horizon")
    @classmethod
    def _validate_horizon(cls, v):
        if v not in _HORIZONS:
            raise ValueError(f"Unknown horizon: {v}")
        return v


class SensitivityResponse(BaseModel):
    preset: str
    comparator: str
    horizon: str
    x_label: str
    y_label: str
    x_values: list[Any]
    y_values: list[Any]
    cells: list[list[dict[str, Any]]]
    # Breakeven crossover metrics (None when bisection bracket doesn't straddle zero)
    breakeven_value_change_pct: Optional[float] = None
    breakeven_rent_change_pct: Optional[float] = None
    breakeven_capex_shock_dollars: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────
# Current home profiles
# ─────────────────────────────────────────────────────────────────────


class CurrentHomeProfileIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_default: bool = False
    config_json: dict[str, Any]

    @field_validator("config_json")
    @classmethod
    def _validate_config(cls, v):
        return _validate_assumptions(v)


class CurrentHomeProfileOut(BaseModel):
    id: str
    name: str
    is_default: bool
    config_json: dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# Saved runs
# ─────────────────────────────────────────────────────────────────────


class RunIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=4000)
    scenario_label: str = Field(default="base", max_length=32)
    target_property_id: Optional[str] = Field(default=None, max_length=64)
    current_home_profile_id: Optional[str] = Field(default=None, max_length=64)
    comparison_horizon_years: int = Field(default=10, ge=1, le=30)
    assumptions_json: dict[str, Any]
    created_from_property_detail: bool = False
    source_prefill_version: Optional[str] = Field(default=None, max_length=32)

    @field_validator("assumptions_json")
    @classmethod
    def _validate_assumptions(cls, v):
        return _validate_assumptions(v)


class RunSummary(BaseModel):
    """Lightweight list row."""

    id: str
    name: str
    scenario_label: str
    target_property_id: Optional[str] = None
    comparison_horizon_years: int
    summary_json: Optional[dict[str, Any]] = None
    calc_version: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RunDetail(RunSummary):
    notes: Optional[str] = None
    current_home_profile_id: Optional[str] = None
    assumptions_json: dict[str, Any]
    outputs_json: Optional[dict[str, Any]] = None
    target_property_snapshot_json: Optional[dict[str, Any]] = None
    current_home_snapshot_json: Optional[dict[str, Any]] = None
    created_from_property_detail: bool = False
    source_prefill_version: Optional[str] = None
    input_schema_version: str
    recomputed: bool = False


class RunCompareRequest(BaseModel):
    run_ids: list[str] = Field(..., min_length=2, max_length=4)

    @field_validator("run_ids")
    @classmethod
    def _dedupe_and_size(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("run_ids must be unique")
        for rid in v:
            if not isinstance(rid, str) or len(rid) > 64:
                raise ValueError("invalid run id")
        return v


# ─────────────────────────────────────────────────────────────────────
# Prefill
# ─────────────────────────────────────────────────────────────────────


class PrefillResponse(BaseModel):
    """Subset of new_home inputs derived from a PIPA property."""

    new_home: dict[str, Any]
    source_prefill_version: str
