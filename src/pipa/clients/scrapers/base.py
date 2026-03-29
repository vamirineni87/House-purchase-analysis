"""Base scraper using Playwright for JavaScript-rendered pages."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default rate limit: 1 request per second to be respectful
_DEFAULT_RATE_LIMIT = 1.0
_DEFAULT_CACHE_TTL_HOURS = 24


class BaseScraper:
    """Async scraper base class using Playwright for JS-heavy county portals.

    Features:
    - Headless Chromium via Playwright
    - Rate limiting (default 1 req/sec)
    - HTML snapshot caching with configurable TTL
    - DOM fingerprinting for change detection
    """

    def __init__(
        self,
        headless: bool = True,
        rate_limit: float = _DEFAULT_RATE_LIMIT,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = _DEFAULT_CACHE_TTL_HOURS,
    ):
        self.headless = headless
        self.rate_limit = rate_limit
        self.cache_dir = cache_dir
        self.cache_ttl_hours = cache_ttl_hours
        self._min_interval = 1.0 / rate_limit if rate_limit > 0 else 0.0
        self._last_request_time = 0.0
        self._browser = None
        self._context = None

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_browser(self):
        """Launch Playwright browser if not already running."""
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

    async def close(self):
        """Shut down the browser and Playwright."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, "_pw") and self._pw:
            await self._pw.stop()
            self._pw = None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _rate_limit_wait(self):
        """Enforce minimum interval between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _cache_key(self, url: str) -> str:
        """Generate a cache key from the URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    def _get_cached_html(self, url: str) -> str | None:
        """Return cached HTML if still fresh, else None."""
        if not self.cache_dir:
            return None
        key = self._cache_key(url)
        meta_path = self.cache_dir / f"{key}.meta.json"
        html_path = self.cache_dir / f"{key}.html"
        if not meta_path.exists() or not html_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text())
            cached_at = meta.get("cached_at", 0)
            ttl_seconds = self.cache_ttl_hours * 3600
            if time.time() - cached_at > ttl_seconds:
                meta_path.unlink(missing_ok=True)
                html_path.unlink(missing_ok=True)
                return None
            return html_path.read_text(encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            return None

    def _put_cached_html(self, url: str, html: str):
        """Cache HTML content to disk."""
        if not self.cache_dir:
            return
        key = self._cache_key(url)
        meta_path = self.cache_dir / f"{key}.meta.json"
        html_path = self.cache_dir / f"{key}.html"
        meta = {
            "url": url,
            "cached_at": time.time(),
            "fingerprint": self._compute_dom_fingerprint(html),
        }
        meta_path.write_text(json.dumps(meta))
        html_path.write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------
    # Core scraping
    # ------------------------------------------------------------------

    async def scrape(self, url: str, wait_for_selector: str | None = None) -> str:
        """Navigate to a URL and return the rendered HTML content.

        Args:
            url: Page URL to scrape.
            wait_for_selector: Optional CSS selector to wait for before capturing HTML.

        Returns:
            Full HTML content of the rendered page.
        """
        # Check cache first
        cached = self._get_cached_html(url)
        if cached is not None:
            logger.debug("Cache hit for scrape: %s", url)
            return cached

        await self._rate_limit_wait()
        await self._ensure_browser()

        page = await self._context.new_page()
        try:
            logger.debug("Scraping: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=30000)

            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=15000)

            html = await page.content()
            self._put_cached_html(url, html)
            return html
        except Exception:
            logger.exception("Failed to scrape %s", url)
            return ""
        finally:
            await page.close()

    async def scrape_with_screenshot(
        self, url: str, screenshot_path: str | Path, wait_for_selector: str | None = None
    ) -> str:
        """Scrape a page and save a screenshot for debugging.

        Args:
            url: Page URL to scrape.
            screenshot_path: File path to save the screenshot PNG.
            wait_for_selector: Optional CSS selector to wait for before capturing.

        Returns:
            Full HTML content of the rendered page.
        """
        await self._rate_limit_wait()
        await self._ensure_browser()

        page = await self._context.new_page()
        try:
            logger.debug("Scraping with screenshot: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=30000)

            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=15000)

            screenshot_path = Path(screenshot_path)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=True)

            html = await page.content()
            self._put_cached_html(url, html)
            return html
        except Exception:
            logger.exception("Failed to scrape with screenshot %s", url)
            return ""
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # DOM fingerprinting and snapshots
    # ------------------------------------------------------------------

    def _compute_dom_fingerprint(self, html: str) -> str:
        """Compute a structural fingerprint of key DOM elements.

        Extracts tag structure (ignoring text content and attributes) to detect
        when a page layout has changed — useful for alerting that selectors
        may need updating.

        Returns:
            SHA-256 hex digest of the simplified DOM structure.
        """
        import re

        # Extract just the tag names in order to create a structural fingerprint
        tags = re.findall(r"<(/?\w+)", html)
        structure = "|".join(tags)
        return hashlib.sha256(structure.encode()).hexdigest()

    def _save_html_snapshot(self, html: str, path: str | Path):
        """Save an HTML snapshot to disk for debugging or archival.

        Args:
            html: HTML content to save.
            path: File path for the snapshot.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        logger.debug("Saved HTML snapshot to %s", path)
