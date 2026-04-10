"""Datetime utilities — primarily for working around the SQLite naive
vs aware datetime gotcha.

SQLite stores datetimes as naive ISO strings even when the column is
declared ``DateTime(timezone=True)``. Values come back from the DB
without ``tzinfo``, so comparing them against an aware ``datetime``
(e.g. ``datetime.now(timezone.utc)``) raises::

    TypeError: can't compare offset-naive and offset-aware datetimes

Use ``as_utc`` whenever you read a timestamp out of the DB and need to
compare it against ``datetime.now(timezone.utc)`` or arithmetic with a
``timedelta`` involving an aware datetime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to UTC-aware.

    A naive datetime is treated as already being in UTC and gets the
    tzinfo attached. An aware datetime is returned unchanged. ``None``
    passes through.

    >>> from datetime import datetime, timezone
    >>> as_utc(datetime(2026, 1, 1)).tzinfo is timezone.utc
    True
    >>> as_utc(datetime(2026, 1, 1, tzinfo=timezone.utc)).tzinfo is timezone.utc
    True
    >>> as_utc(None) is None
    True
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
