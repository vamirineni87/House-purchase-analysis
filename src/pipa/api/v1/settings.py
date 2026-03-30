"""Settings endpoints — persist user preferences and API keys."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.app_setting import AppSetting

router = APIRouter(tags=["settings"])

# ── Schemas ─────────────────────────────────────────────────────────

class SettingPayload(BaseModel):
    key: str
    value: Any
    category: str = "ui_defaults"


class SettingResponse(BaseModel):
    key: str
    value: Any
    category: str

    model_config = {"from_attributes": True}


# ── Default settings applied on reset ───────────────────────────────

DEFAULTS: list[dict[str, Any]] = [
    # financial defaults
    {"key": "default_down_payment_pcts", "value": [5, 10, 20], "category": "financial_defaults"},
    {"key": "default_term_years", "value": [15, 30], "category": "financial_defaults"},
    {"key": "default_property_tax_rate", "value": 1.11, "category": "financial_defaults"},
    {"key": "default_homeowners_insurance", "value": 1800, "category": "financial_defaults"},
    {"key": "default_hoa_monthly", "value": 0, "category": "financial_defaults"},
    # ui defaults
    {"key": "default_tab", "value": "Summary", "category": "ui_defaults"},
    {"key": "properties_per_page", "value": 25, "category": "ui_defaults"},
    {"key": "toast_duration_ms", "value": 4000, "category": "ui_defaults"},
    {"key": "cache_ttl_ms", "value": 60000, "category": "ui_defaults"},
]


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/settings", response_model=dict[str, list[SettingResponse]])
async def list_settings(db: AsyncSession = Depends(get_db)):
    """Return all settings grouped by category."""
    result = await db.execute(select(AppSetting).order_by(AppSetting.category, AppSetting.key))
    rows = result.scalars().all()

    grouped: dict[str, list[SettingResponse]] = defaultdict(list)
    for row in rows:
        grouped[row.category].append(
            SettingResponse(key=row.key, value=row.value_json, category=row.category)
        )
    return dict(grouped)


@router.post("/settings", response_model=SettingResponse, status_code=200)
async def save_setting(body: SettingPayload, db: AsyncSession = Depends(get_db)):
    """Create or update a single setting."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == body.key))
    existing = result.scalar_one_or_none()

    if existing:
        existing.value_json = body.value
        existing.category = body.category
        await db.flush()
        return SettingResponse(key=existing.key, value=existing.value_json, category=existing.category)

    setting = AppSetting(key=body.key, value_json=body.value, category=body.category)
    db.add(setting)
    await db.flush()
    return SettingResponse(key=setting.key, value=setting.value_json, category=setting.category)


@router.post("/settings/reset", response_model=dict[str, list[SettingResponse]])
async def reset_settings(db: AsyncSession = Depends(get_db)):
    """Delete all settings and re-seed with defaults."""
    await db.execute(delete(AppSetting))

    for d in DEFAULTS:
        db.add(AppSetting(key=d["key"], value_json=d["value"], category=d["category"]))
    await db.flush()

    # Return the freshly-seeded settings grouped by category
    return await list_settings(db)
