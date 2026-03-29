"""Listing monitor worker.

For each watched property, checks whether price or status has changed
since the last snapshot. Creates alert events for significant changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_session_factory
from pipa.core.events import Event, event_bus
from pipa.models.alert import AlertEvent
from pipa.models.listing import ListingEpisode, ListingSnapshot, PriceEvent, StatusEvent
from pipa.models.property import Property
from pipa.models.user import WatchlistEntry

logger = logging.getLogger(__name__)


async def check_listing_changes():
    """Main entry point: check all watched properties for listing changes.

    Called by APScheduler every 4 hours.
    """
    logger.info("Starting listing change check")
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            # Get active watchlist property IDs
            result = await session.execute(
                select(WatchlistEntry.property_id).where(
                    WatchlistEntry.stage.notin_(["closed", "rejected"])
                )
            )
            property_ids = list({row[0] for row in result.all()})

            if not property_ids:
                logger.info("No active watchlist properties to monitor")
                return

            alerts_created = 0
            for prop_id in property_ids:
                try:
                    count = await _check_property_listing(session, prop_id)
                    alerts_created += count
                except Exception:
                    logger.exception("Error checking listing for property %s", prop_id)

            await session.commit()
            logger.info(
                "Listing monitor complete: checked %d properties, created %d alerts",
                len(property_ids),
                alerts_created,
            )

        except Exception:
            logger.exception("Listing monitor job failed")
            await session.rollback()


async def _check_property_listing(session, property_id: str) -> int:
    """Check a single property for listing changes. Returns number of alerts created."""
    now = datetime.now(timezone.utc)
    alerts_created = 0

    # Get the most recent active listing episode
    result = await session.execute(
        select(ListingEpisode)
        .options(
            selectinload(ListingEpisode.snapshots),
            selectinload(ListingEpisode.status_events),
            selectinload(ListingEpisode.price_events),
        )
        .where(
            ListingEpisode.property_id == property_id,
        )
        .order_by(ListingEpisode.created_at.desc())
        .limit(1)
    )
    episode = result.scalar_one_or_none()

    if episode is None:
        return 0

    # Get the two most recent snapshots to detect changes
    snapshots = sorted(episode.snapshots, key=lambda s: s.captured_at, reverse=True)

    if len(snapshots) < 2:
        return 0

    current = snapshots[0]
    previous = snapshots[1]

    # Check for price cut
    if current.price < previous.price:
        price_drop = previous.price - current.price
        price_drop_pct = (price_drop / previous.price) * 100

        alert = AlertEvent(
            property_id=property_id,
            alert_type="price_cut",
            title=f"Price reduced by ${price_drop:,.0f} ({price_drop_pct:.1f}%)",
            description=(
                f"Price dropped from ${previous.price:,.0f} to ${current.price:,.0f}. "
                f"Original list price: ${episode.original_list_price:,.0f}."
                if episode.original_list_price
                else f"Price dropped from ${previous.price:,.0f} to ${current.price:,.0f}."
            ),
            severity="warning" if price_drop_pct >= 5 else "info",
            data={
                "old_price": previous.price,
                "new_price": current.price,
                "drop_amount": price_drop,
                "drop_pct": round(price_drop_pct, 2),
                "original_list_price": episode.original_list_price,
            },
            triggered_at=now,
        )
        session.add(alert)
        alerts_created += 1

        # Also record the price event on the episode
        price_event = PriceEvent(
            listing_episode_id=episode.id,
            old_price=previous.price,
            new_price=current.price,
            event_date=now,
        )
        session.add(price_event)

        # Emit internal event
        await event_bus.emit(Event(
            event_type="price_changed",
            property_id=property_id,
            data={"old_price": previous.price, "new_price": current.price},
        ))

        logger.info(
            "Price cut detected for property %s: $%s -> $%s (%.1f%%)",
            property_id,
            f"{previous.price:,.0f}",
            f"{current.price:,.0f}",
            price_drop_pct,
        )

    # Check for status change
    if current.status != previous.status:
        alert = AlertEvent(
            property_id=property_id,
            alert_type="status_change",
            title=f"Status changed: {previous.status} -> {current.status}",
            description=f"Listing status changed from '{previous.status}' to '{current.status}'.",
            severity=_status_change_severity(previous.status, current.status),
            data={
                "old_status": previous.status,
                "new_status": current.status,
            },
            triggered_at=now,
        )
        session.add(alert)
        alerts_created += 1

        # Record the status event
        status_event = StatusEvent(
            listing_episode_id=episode.id,
            from_status=previous.status,
            to_status=current.status,
            event_date=now,
        )
        session.add(status_event)

        # Emit internal event
        await event_bus.emit(Event(
            event_type="status_changed",
            property_id=property_id,
            data={"old_status": previous.status, "new_status": current.status},
        ))

        logger.info(
            "Status change for property %s: %s -> %s",
            property_id,
            previous.status,
            current.status,
        )

    # Check for back-on-market
    if (
        current.status == "active"
        and previous.status in ("pending", "withdrawn", "expired")
    ):
        alert = AlertEvent(
            property_id=property_id,
            alert_type="back_on_market",
            title="Property is back on market",
            description=(
                f"Property returned to active status from '{previous.status}'. "
                f"Current price: ${current.price:,.0f}."
            ),
            severity="warning",
            data={
                "previous_status": previous.status,
                "current_price": current.price,
            },
            triggered_at=now,
        )
        session.add(alert)
        alerts_created += 1

        await event_bus.emit(Event(
            event_type="back_on_market",
            property_id=property_id,
            data={"previous_status": previous.status, "price": current.price},
        ))

        logger.info("Back on market: property %s", property_id)

    return alerts_created


def _status_change_severity(old_status: str, new_status: str) -> str:
    """Determine alert severity for a status transition."""
    critical_transitions = {
        ("active", "pending"),      # Someone put in an offer
        ("pending", "sold"),        # Lost opportunity
    }
    warning_transitions = {
        ("active", "withdrawn"),
        ("pending", "active"),      # Deal fell through — back on market
    }

    pair = (old_status, new_status)
    if pair in critical_transitions:
        return "critical"
    if pair in warning_transitions:
        return "warning"
    return "info"
