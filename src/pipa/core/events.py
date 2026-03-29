"""Internal event bus for decoupled alert triggers.

Simple in-process pub/sub. Components emit events (e.g., "price_changed"),
and subscribers (e.g., alert evaluator) react to them.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """An internal domain event."""

    event_type: str
    property_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Type for async event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Simple async event bus for internal domain events."""

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler):
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        """Remove a handler for an event type."""
        self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]

    async def emit(self, event: Event):
        """Emit an event to all subscribed handlers."""
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("Event handler failed for %s", event.event_type)

    async def emit_many(self, events: list[Event]):
        """Emit multiple events."""
        for event in events:
            await self.emit(event)


# Module-level singleton
event_bus = EventBus()
