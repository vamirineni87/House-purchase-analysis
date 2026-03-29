"""Enhanced base HTTP client with connection pooling, retry, rate limiting, disk cache, and raw payload archival.

All external data access goes through this base. Every response is optionally
archived as a SourceRecord for provenance tracking.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Default retry config
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0  # seconds, doubles each retry
DEFAULT_TIMEOUT = 30.0


class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self._last_call = 0.0

    async def wait(self):
        """Wait until we can make the next call."""
        import asyncio

        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()


class DiskCache:
    """Simple disk-based response cache with TTL."""

    def __init__(self, cache_dir: Path, ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_hours * 3600
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, url: str, params: dict | None = None) -> str:
        raw = f"{url}|{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, url: str, params: dict | None = None) -> Optional[dict]:
        """Return cached response if fresh, else None."""
        key = self._key(url, params)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            cached_at = data.get("_cached_at", 0)
            if time.time() - cached_at > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            return data.get("payload")
        except (json.JSONDecodeError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def put(self, url: str, params: dict | None, payload: Any):
        """Cache a response."""
        key = self._key(url, params)
        path = self.cache_dir / f"{key}.json"
        data = {"_cached_at": time.time(), "url": url, "payload": payload}
        path.write_text(json.dumps(data, default=str))


class BaseClient:
    """Enhanced async HTTP client base class.

    Features:
    - Connection pooling via shared httpx.AsyncClient
    - Configurable retry with exponential backoff
    - Per-domain rate limiting
    - Disk-based response caching with TTL
    - Raw payload archival for provenance
    """

    source_name: str = "unknown"
    base_url: str = ""

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 24,
        raw_payload_dir: Path | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._rate_limiter = RateLimiter(rate_limit)
        self._cache = DiskCache(cache_dir, cache_ttl_hours) if cache_dir else None
        self._raw_payload_dir = raw_payload_dir

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self._default_headers(),
            )
        return self._client

    def _default_headers(self) -> dict[str, str]:
        """Override in subclasses to set auth headers."""
        return {"User-Agent": "PIPA/0.1.0"}

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        use_cache: bool = True,
        archive: bool = True,
    ) -> Optional[Any]:
        """Make a GET request with retry, rate limiting, caching, and archival.

        Returns parsed JSON response or None on failure.
        """
        full_url = f"{self.base_url}{url}" if not url.startswith("http") else url

        # Check cache
        if use_cache and self._cache:
            cached = self._cache.get(full_url, params)
            if cached is not None:
                logger.debug("Cache hit: %s", full_url)
                return cached

        # Rate limit
        await self._rate_limiter.wait()

        # Retry loop
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                response = await client.get(full_url, params=params, headers=headers)
                response.raise_for_status()

                data = response.json()

                # Cache response
                if use_cache and self._cache:
                    self._cache.put(full_url, params, data)

                # Archive raw payload
                if archive and self._raw_payload_dir:
                    self._archive_payload(full_url, params, data)

                return data

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    # Rate limited — wait longer
                    wait = DEFAULT_RETRY_BACKOFF * (2 ** attempt) * 5
                    logger.warning("Rate limited on %s, waiting %.1fs", full_url, wait)
                    import asyncio
                    await asyncio.sleep(wait)
                    continue
                elif e.response.status_code >= 500:
                    # Server error — retry
                    wait = DEFAULT_RETRY_BACKOFF * (2 ** attempt)
                    logger.warning("Server error %d on %s, retry %d", e.response.status_code, full_url, attempt + 1)
                    import asyncio
                    await asyncio.sleep(wait)
                    continue
                else:
                    # Client error (4xx except 429) — don't retry
                    logger.error("Client error %d on %s: %s", e.response.status_code, full_url, e.response.text[:200])
                    return None

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                last_error = e
                wait = DEFAULT_RETRY_BACKOFF * (2 ** attempt)
                logger.warning("Connection error on %s, retry %d: %s", full_url, attempt + 1, str(e)[:100])
                import asyncio
                await asyncio.sleep(wait)
                continue

            except Exception as e:
                logger.exception("Unexpected error fetching %s", full_url)
                return None

        logger.error("All retries exhausted for %s: %s", full_url, last_error)
        return None

    def _archive_payload(self, url: str, params: dict | None, data: Any):
        """Archive raw API response to disk for provenance."""
        if not self._raw_payload_dir:
            return
        try:
            self._raw_payload_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            key = hashlib.sha256(f"{url}|{params}".encode()).hexdigest()[:12]
            path = self._raw_payload_dir / f"{self.source_name}_{ts}_{key}.json"
            payload = {
                "source": self.source_name,
                "url": url,
                "params": params,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
            path.write_text(json.dumps(payload, default=str, indent=2))
        except Exception:
            logger.debug("Failed to archive payload for %s", url, exc_info=True)
