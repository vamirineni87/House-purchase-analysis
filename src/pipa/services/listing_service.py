"""Listing lifecycle management service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.models.listing import (
    ListingEpisode,
    ListingSnapshot,
    PriceEvent,
    SaleEvent,
    StatusEvent,
)


class ListingService:
    """Manages listing episodes, snapshots, and timeline events."""

    # ------------------------------------------------------------------
    # Episode management
    # ------------------------------------------------------------------

    @staticmethod
    async def create_episode(
        db: AsyncSession,
        property_id: str,
        *,
        source: str = "manual",
        original_list_price: Optional[float] = None,
        original_list_date: Optional[datetime] = None,
        status: str = "active",
        bedrooms: Optional[int] = None,
        bathrooms: Optional[float] = None,
        sqft: Optional[float] = None,
        year_built: Optional[int] = None,
        mls_number: Optional[str] = None,
    ) -> ListingEpisode:
        """Create a new listing episode for a property."""
        episode = ListingEpisode(
            property_id=property_id,
            source=source,
            original_list_price=original_list_price,
            original_list_date=original_list_date,
            status=status,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            year_built=year_built,
            mls_number=mls_number,
        )
        db.add(episode)
        await db.flush()
        return episode

    @staticmethod
    async def get_episode(
        db: AsyncSession,
        episode_id: str,
    ) -> Optional[ListingEpisode]:
        """Fetch a listing episode by ID with snapshots loaded."""
        result = await db.execute(
            select(ListingEpisode)
            .options(
                selectinload(ListingEpisode.snapshots),
                selectinload(ListingEpisode.status_events),
                selectinload(ListingEpisode.price_events),
            )
            .where(ListingEpisode.id == episode_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_episodes_for_property(
        db: AsyncSession,
        property_id: str,
    ) -> list[ListingEpisode]:
        """Get all listing episodes for a property."""
        result = await db.execute(
            select(ListingEpisode)
            .options(selectinload(ListingEpisode.snapshots))
            .where(ListingEpisode.property_id == property_id)
            .order_by(ListingEpisode.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------

    @staticmethod
    async def add_snapshot(
        db: AsyncSession,
        episode_id: str,
        price: float,
        status: str,
    ) -> ListingSnapshot:
        """Add a price/status snapshot to a listing episode.

        Automatically detects price and status changes and creates
        the corresponding event records.
        """
        now = datetime.now(timezone.utc)

        # Load the episode with existing snapshots
        result = await db.execute(
            select(ListingEpisode)
            .options(selectinload(ListingEpisode.snapshots))
            .where(ListingEpisode.id == episode_id)
        )
        episode = result.scalar_one_or_none()
        if episode is None:
            raise ValueError(f"Listing episode {episode_id} not found")

        # Compute delta from last snapshot
        delta_price: Optional[float] = None
        last_snapshot = None
        if episode.snapshots:
            last_snapshot = max(episode.snapshots, key=lambda s: s.captured_at)
            delta_price = round(price - last_snapshot.price, 2)

        snapshot = ListingSnapshot(
            listing_episode_id=episode_id,
            captured_at=now,
            price=price,
            status=status,
            delta_price=delta_price,
        )
        db.add(snapshot)

        # Create events if there were changes
        if last_snapshot is not None:
            if abs(price - last_snapshot.price) > 0.01:
                price_event = PriceEvent(
                    listing_episode_id=episode_id,
                    old_price=last_snapshot.price,
                    new_price=price,
                    event_date=now,
                )
                db.add(price_event)

            if status != last_snapshot.status:
                status_event = StatusEvent(
                    listing_episode_id=episode_id,
                    from_status=last_snapshot.status,
                    to_status=status,
                    event_date=now,
                )
                db.add(status_event)

        # Update episode status
        episode.status = status

        await db.flush()
        return snapshot

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    @staticmethod
    async def get_timeline(
        db: AsyncSession,
        property_id: str,
    ) -> list[dict]:
        """Build a chronological timeline of all listing events for a property."""
        events: list[dict] = []

        # Listing episodes
        ep_result = await db.execute(
            select(ListingEpisode)
            .options(
                selectinload(ListingEpisode.snapshots),
                selectinload(ListingEpisode.status_events),
                selectinload(ListingEpisode.price_events),
            )
            .where(ListingEpisode.property_id == property_id)
        )
        episodes = ep_result.scalars().all()

        for ep in episodes:
            if ep.original_list_date:
                events.append({
                    "event_type": "listing",
                    "date": ep.original_list_date.isoformat(),
                    "description": f"Listed at ${ep.original_list_price:,.0f}" if ep.original_list_price else "Listed",
                    "data": {"episode_id": ep.id, "source": ep.source},
                })

            for pe in ep.price_events:
                events.append({
                    "event_type": "price_change",
                    "date": pe.event_date.isoformat(),
                    "description": f"Price changed from ${pe.old_price:,.0f} to ${pe.new_price:,.0f}",
                    "data": {"episode_id": ep.id, "delta": round(pe.new_price - pe.old_price, 2)},
                })

            for se in ep.status_events:
                events.append({
                    "event_type": "status_change",
                    "date": se.event_date.isoformat(),
                    "description": f"Status changed from {se.from_status} to {se.to_status}",
                    "data": {"episode_id": ep.id},
                })

        # Sale events
        sale_result = await db.execute(
            select(SaleEvent)
            .where(SaleEvent.property_id == property_id)
            .order_by(SaleEvent.sale_date.desc())
        )
        for sale in sale_result.scalars().all():
            events.append({
                "event_type": "sale",
                "date": sale.sale_date.isoformat(),
                "description": f"Sold for ${sale.sale_price:,.0f}",
                "data": {"source": sale.source},
            })

        # Sort chronologically
        events.sort(key=lambda e: e["date"])
        return events
