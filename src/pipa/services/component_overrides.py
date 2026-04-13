"""User-managed component install year overrides.

Lets the buyer manually correct a component's install year when they
have private knowledge that beats the listing/county/AI signal —
e.g. seller mentioned in conversation that the water heater was
replaced in 2017 but no permit exists.

Stored in AppSetting (no extra table) under keys of the form
``component_override.{property_id}.{canonical_key}``. Value is a JSON
object: ``{"year": int, "notes": str|None, "set_at": iso}``.

The resolver loads these at the highest rank (100) so they beat
county (90), AI-extracted (35), and year_built defaults.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

_KEY_PREFIX = "component_override."
_CATEGORY = "component_overrides"


def _key(property_id: str, canonical_key: str) -> str:
    return f"{_KEY_PREFIX}{property_id}.{canonical_key}"


async def get_overrides(db: AsyncSession, property_id: str) -> dict[str, dict]:
    """Return all overrides for a property as ``{canonical_key: {year, notes, set_at}}``.

    Skips (with a warning) any rows whose ``value_json`` isn't a dict —
    silent drops would mean a corrupted or hand-edited row makes the
    user's saved year vanish without explanation, which is the worst
    failure mode for a feature whose whole purpose is correcting the
    automated pipeline.
    """
    prefix = f"{_KEY_PREFIX}{property_id}."
    # Escape SQL LIKE wildcards in the prefix. Property IDs are UUIDs
    # today so this is defence-in-depth, but the API documents this
    # function as taking arbitrary property_ids and a future caller
    # passing one with `%` or `_` would otherwise match unrelated rows.
    safe_prefix = prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    result = await db.execute(
        select(AppSetting).where(
            AppSetting.key.like(f"{safe_prefix}%", escape="\\")
        )
    )
    out: dict[str, dict] = {}
    for row in result.scalars().all():
        canonical_key = row.key[len(prefix):]
        if isinstance(row.value_json, dict):
            out[canonical_key] = row.value_json
        else:
            logger.warning(
                "Component override %s has non-dict value_json (%s); ignoring",
                row.key, type(row.value_json).__name__,
            )
    return out


async def set_override(
    db: AsyncSession,
    property_id: str,
    canonical_key: str,
    year: int,
    notes: Optional[str] = None,
) -> dict:
    """Upsert a manual install-year override.

    Uses SQLite's native ``INSERT ... ON CONFLICT DO UPDATE`` so two
    near-simultaneous saves (e.g. Enter + click in the inline editor)
    can't race past a select-then-insert check and trip the UNIQUE
    constraint.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "year": int(year),
        "notes": notes,
        "set_at": now.isoformat(),
    }
    key = _key(property_id, canonical_key)

    stmt = sqlite_insert(AppSetting).values(
        key=key,
        value_json=payload,
        category=_CATEGORY,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={"value_json": payload, "updated_at": now},
    )
    await db.execute(stmt)
    await db.flush()
    return payload


async def delete_override(
    db: AsyncSession, property_id: str, canonical_key: str
) -> bool:
    """Remove an override. Returns True if a row was deleted.

    Single atomic DELETE statement instead of select-then-delete so
    concurrent requests (double-click, two tabs hitting the red X) can't
    race past each other and crash with InvalidRequestError.
    """
    key = _key(property_id, canonical_key)
    result = await db.execute(
        sql_delete(AppSetting).where(AppSetting.key == key)
    )
    await db.flush()
    return (result.rowcount or 0) > 0
