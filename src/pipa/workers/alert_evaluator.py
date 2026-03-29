"""Alert evaluation worker.

Checks alert subscription conditions against recent data changes
and evaluates nearby property changes that might affect watched properties.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_session_factory
from pipa.models.alert import AlertEvent, AlertSubscription
from pipa.models.listing import ListingEpisode, PriceEvent, StatusEvent
from pipa.models.nearby import NearbyRelationship
from pipa.models.property import Property
from pipa.models.user import WatchlistEntry

logger = logging.getLogger(__name__)

# How far back to look for recent changes (in minutes)
LOOKBACK_MINUTES = 30


async def evaluate_alerts():
    """Main entry point: evaluate all alert subscriptions.

    Called by APScheduler every 15 minutes.
    """
    logger.info("Starting alert evaluation")
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            alerts_created = 0

            # Evaluate subscription-based alerts
            alerts_created += await _evaluate_subscriptions(session)

            # Evaluate nearby property changes
            alerts_created += await _evaluate_nearby_changes(session)

            await session.commit()
            logger.info("Alert evaluation complete: %d new alerts", alerts_created)

        except Exception:
            logger.exception("Alert evaluation job failed")
            await session.rollback()


async def _evaluate_subscriptions(session) -> int:
    """Check active alert subscriptions against recent data changes."""
    alerts_created = 0
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=LOOKBACK_MINUTES)

    # Load active subscriptions
    result = await session.execute(
        select(AlertSubscription).where(AlertSubscription.is_active == True)  # noqa: E712
    )
    subscriptions = result.scalars().all()

    if not subscriptions:
        return 0

    # Get recent alert events to avoid duplicates
    result = await session.execute(
        select(AlertEvent).where(AlertEvent.triggered_at >= lookback)
    )
    recent_alerts = result.scalars().all()
    recent_keys = {
        (a.property_id, a.alert_type) for a in recent_alerts
    }

    for sub in subscriptions:
        try:
            new_alerts = await _check_subscription(session, sub, lookback, recent_keys)
            for alert in new_alerts:
                session.add(alert)
                alerts_created += 1
        except Exception:
            logger.exception("Error evaluating subscription %s", sub.id)

    return alerts_created


async def _check_subscription(
    session,
    subscription: AlertSubscription,
    since: datetime,
    existing_keys: set[tuple],
) -> list[AlertEvent]:
    """Evaluate a single subscription and return any new alerts."""
    now = datetime.now(timezone.utc)
    new_alerts: list[AlertEvent] = []
    criteria = subscription.filter_criteria or {}

    # Get the user's watched properties
    result = await session.execute(
        select(WatchlistEntry).where(
            WatchlistEntry.user_id == subscription.user_id,
            WatchlistEntry.stage.notin_(["closed", "rejected"]),
        )
    )
    watched = result.scalars().all()
    watched_ids = {w.property_id for w in watched}

    if not watched_ids:
        return []

    # Subscription type: price_threshold
    if subscription.alert_type == "price_threshold":
        max_price = criteria.get("max_price")
        if max_price is not None:
            for prop_id in watched_ids:
                if (prop_id, "price_threshold_exceeded") in existing_keys:
                    continue

                result = await session.execute(
                    select(ListingEpisode)
                    .where(
                        ListingEpisode.property_id == prop_id,
                        ListingEpisode.status == "active",
                    )
                    .order_by(ListingEpisode.created_at.desc())
                    .limit(1)
                )
                episode = result.scalar_one_or_none()
                if episode and episode.original_list_price and episode.original_list_price > max_price:
                    new_alerts.append(AlertEvent(
                        property_id=prop_id,
                        alert_type="price_threshold_exceeded",
                        title=f"Price ${episode.original_list_price:,.0f} exceeds budget ${max_price:,.0f}",
                        severity="info",
                        data={"price": episode.original_list_price, "threshold": max_price},
                        triggered_at=now,
                    ))

    # Subscription type: days_on_market
    elif subscription.alert_type == "days_on_market":
        threshold_days = criteria.get("min_days", 30)
        for prop_id in watched_ids:
            if (prop_id, "high_dom") in existing_keys:
                continue

            result = await session.execute(
                select(ListingEpisode)
                .where(
                    ListingEpisode.property_id == prop_id,
                    ListingEpisode.status == "active",
                )
                .order_by(ListingEpisode.created_at.desc())
                .limit(1)
            )
            episode = result.scalar_one_or_none()
            if episode and episode.days_on_market and episode.days_on_market >= threshold_days:
                new_alerts.append(AlertEvent(
                    property_id=prop_id,
                    alert_type="high_dom",
                    title=f"Property on market for {episode.days_on_market} days (threshold: {threshold_days})",
                    description="Long days-on-market may indicate pricing or condition issues, or negotiation opportunity.",
                    severity="info",
                    data={"days_on_market": episode.days_on_market, "threshold": threshold_days},
                    triggered_at=now,
                ))

    # Subscription type: price_drop
    elif subscription.alert_type == "price_drop":
        min_drop_pct = criteria.get("min_drop_pct", 3.0)
        for prop_id in watched_ids:
            # Check for recent price events
            result = await session.execute(
                select(PriceEvent)
                .join(ListingEpisode)
                .where(
                    ListingEpisode.property_id == prop_id,
                    PriceEvent.event_date >= since,
                )
                .order_by(PriceEvent.event_date.desc())
                .limit(1)
            )
            pe = result.scalar_one_or_none()
            if pe and pe.old_price > 0:
                drop_pct = ((pe.old_price - pe.new_price) / pe.old_price) * 100
                if drop_pct >= min_drop_pct and (prop_id, "significant_price_drop") not in existing_keys:
                    new_alerts.append(AlertEvent(
                        property_id=prop_id,
                        alert_type="significant_price_drop",
                        title=f"Price dropped {drop_pct:.1f}% (>${pe.old_price - pe.new_price:,.0f})",
                        severity="warning",
                        data={
                            "old_price": pe.old_price,
                            "new_price": pe.new_price,
                            "drop_pct": round(drop_pct, 2),
                        },
                        triggered_at=now,
                    ))

    return new_alerts


async def _evaluate_nearby_changes(session) -> int:
    """Check for changes in nearby/surrounding properties.

    If a nearby property has a recent price cut or sale, it could affect
    the comp value of watched properties.
    """
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=LOOKBACK_MINUTES)
    alerts_created = 0

    # Get active watchlist property IDs
    result = await session.execute(
        select(WatchlistEntry.property_id).where(
            WatchlistEntry.stage.notin_(["closed", "rejected"])
        )
    )
    watched_ids = {row[0] for row in result.all()}

    if not watched_ids:
        return 0

    # For each watched property, check if any nearby property had recent changes
    for prop_id in watched_ids:
        try:
            result = await session.execute(
                select(NearbyRelationship).where(
                    NearbyRelationship.subject_property_id == prop_id,
                    NearbyRelationship.is_current == True,  # noqa: E712
                )
            )
            relationships = result.scalars().all()

            for rel in relationships:
                related_id = rel.related_property_id

                # Check for recent price events on the related property
                result = await session.execute(
                    select(PriceEvent)
                    .join(ListingEpisode)
                    .where(
                        ListingEpisode.property_id == related_id,
                        PriceEvent.event_date >= lookback,
                    )
                    .limit(1)
                )
                nearby_price_event = result.scalar_one_or_none()

                if nearby_price_event:
                    # Check we haven't already alerted on this
                    result = await session.execute(
                        select(AlertEvent).where(
                            AlertEvent.property_id == prop_id,
                            AlertEvent.alert_type == "nearby_price_change",
                            AlertEvent.triggered_at >= lookback,
                        ).limit(1)
                    )
                    if result.scalar_one_or_none() is None:
                        distance_str = (
                            f" ({rel.distance_feet:.0f} ft away)"
                            if rel.distance_feet
                            else ""
                        )
                        alert = AlertEvent(
                            property_id=prop_id,
                            alert_type="nearby_price_change",
                            title=f"Nearby comp price changed{distance_str}",
                            description=(
                                f"A {rel.relationship_type} property had a price change: "
                                f"${nearby_price_event.old_price:,.0f} -> ${nearby_price_event.new_price:,.0f}. "
                                f"This may affect comparable value estimates."
                            ),
                            severity="info",
                            data={
                                "related_property_id": related_id,
                                "relationship_type": rel.relationship_type,
                                "old_price": nearby_price_event.old_price,
                                "new_price": nearby_price_event.new_price,
                                "distance_feet": rel.distance_feet,
                            },
                            triggered_at=now,
                        )
                        session.add(alert)
                        alerts_created += 1

        except Exception:
            logger.exception("Error evaluating nearby changes for property %s", prop_id)

    return alerts_created
