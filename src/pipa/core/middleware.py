"""Request-timing middleware for FastAPI.

Logs every HTTP request as one line on entry (so we can see in-flight
requests when the page is "stuck loading") and one line on exit with
status + duration. Slow requests (>1s) are flagged at WARNING.

Without this we have no view into which API call is hanging when the
SPA stops responding while the background pipeline is running.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("pipa.core.middleware")

# Threshold (ms) above which a request is flagged at WARNING.
SLOW_REQUEST_MS = 1000

# Paths we don't want flooding the log on every page load.
_NOISY_PREFIXES = ("/static/", "/favicon")


def _should_skip(path: str) -> bool:
    return any(path.startswith(p) for p in _NOISY_PREFIXES)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Logs entry / exit / duration for every API call."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        method = request.method

        # Static assets and favicon don't need timing — too noisy
        if _should_skip(path):
            return await call_next(request)

        # Short request id so we can correlate the entry and exit lines
        rid = uuid.uuid4().hex[:8]
        client = request.client.host if request.client else "?"
        query = ("?" + request.url.query) if request.url.query else ""

        logger.info("→ [%s] %s %s%s from %s", rid, method, path, query, client)

        start = time.monotonic()
        status_code = 0
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.exception("✗ [%s] %s %s FAILED after %.0fms", rid, method, path, elapsed_ms)
            raise
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            level = logging.WARNING if elapsed_ms >= SLOW_REQUEST_MS else logging.INFO
            logger.log(
                level,
                "← [%s] %s %s → %d in %.0fms",
                rid, method, path, status_code, elapsed_ms,
            )
