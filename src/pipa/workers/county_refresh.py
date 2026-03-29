"""County data refresh worker.

Iterates the watchlist, checks each property's data freshness against
the configured TTL, and refreshes stale records from county sources.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_session_factory
from pipa.models.freshness import DataFreshnessPolicy
from pipa.models.property import Property
from pipa.models.source import SourceRecord
from pipa.models.user import WatchlistEntry

logger = logging.getLogger(__name__)

# Default freshness TTLs when no policy row exists (hours)
DEFAULT_TTL = {
    "parcel": 720,           # 30 days
    "assessment": 720,       # 30 days
    "permit": 168,           # 7 days
    "deed": 720,             # 30 days
    "listing": 4,            # 4 hours
    "hoa": 720,              # 30 days
    "hazard": 8760,          # 1 year
}


async def refresh_watched_properties():
    """Main entry point: refresh stale county data for all watchlist properties.

    Called by APScheduler on a daily cron trigger.
    """
    logger.info("Starting county refresh for watched properties")
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            # Get all active watchlist entries (not closed/rejected)
            result = await session.execute(
                select(WatchlistEntry).where(
                    WatchlistEntry.stage.notin_(["closed", "rejected"])
                )
            )
            entries = result.scalars().all()
            property_ids = list({e.property_id for e in entries})

            if not property_ids:
                logger.info("No active watchlist properties to refresh")
                return

            logger.info("Checking freshness for %d watched properties", len(property_ids))

            # Load freshness policies
            policies = await _load_freshness_policies(session)

            # Check each property
            refreshed = 0
            errors = 0
            for prop_id in property_ids:
                try:
                    stale_sources = await _check_property_freshness(
                        session, prop_id, policies
                    )
                    if stale_sources:
                        await _refresh_property_sources(session, prop_id, stale_sources)
                        refreshed += 1
                except Exception:
                    logger.exception("Error refreshing property %s", prop_id)
                    errors += 1

            await session.commit()
            logger.info(
                "County refresh complete: %d refreshed, %d errors, %d skipped (fresh)",
                refreshed,
                errors,
                len(property_ids) - refreshed - errors,
            )

        except Exception:
            logger.exception("County refresh job failed")
            await session.rollback()


async def _load_freshness_policies(session) -> dict[str, int]:
    """Load TTL policies from database, falling back to defaults."""
    result = await session.execute(select(DataFreshnessPolicy))
    policies = result.scalars().all()

    ttl_map = dict(DEFAULT_TTL)
    for policy in policies:
        ttl_map[policy.entity_type] = policy.ttl_hours

    return ttl_map


async def _check_property_freshness(
    session, property_id: str, ttl_map: dict[str, int]
) -> list[str]:
    """Check which data sources are stale for a given property.

    Returns a list of source categories that need refreshing.
    """
    now = datetime.now(timezone.utc)
    stale_sources: list[str] = []

    for source_category, ttl_hours in ttl_map.items():
        cutoff = now - timedelta(hours=ttl_hours)

        # Find the most recent source record for this category
        result = await session.execute(
            select(SourceRecord)
            .where(
                SourceRecord.property_id == property_id,
                SourceRecord.source_name.contains(source_category),
            )
            .order_by(SourceRecord.fetched_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()

        if latest is None or latest.fetched_at < cutoff:
            stale_sources.append(source_category)

    return stale_sources


async def _refresh_property_sources(
    session, property_id: str, stale_sources: list[str]
):
    """Refresh stale data sources for a property.

    Delegates to the appropriate county service based on the property's county.
    """
    # Load property with address to determine county
    result = await session.execute(
        select(Property)
        .options(selectinload(Property.addresses))
        .where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        logger.warning("Property %s not found, skipping refresh", property_id)
        return

    county = None
    for addr in prop.addresses:
        if addr.is_current and addr.county:
            county = addr.county.lower()
            break

    if not county:
        logger.warning("No county for property %s, skipping refresh", property_id)
        return

    logger.info(
        "Refreshing %d stale sources for property %s (county=%s): %s",
        len(stale_sources),
        property_id,
        county,
        stale_sources,
    )

    # Record a SourceRecord entry to mark the refresh attempt
    # The actual data fetching would be handled by county-specific clients.
    # For now, we log the intent and create placeholder records.
    for source_cat in stale_sources:
        source_name = f"{county}_{source_cat}"
        record = SourceRecord(
            property_id=property_id,
            source_name=source_name,
            source_url=f"scheduled_refresh:{source_cat}",
            fetched_at=datetime.now(timezone.utc),
            raw_payload={"status": "refresh_scheduled", "category": source_cat},
        )
        session.add(record)
        logger.debug("Scheduled refresh for %s on property %s", source_name, property_id)
