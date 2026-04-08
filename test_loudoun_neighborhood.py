"""One-off test: scrape Loudoun "Neighborhood Sales" tab.

Prints the full nav-link inventory + raw rows so we can see the actual
shape of the Neighborhood Sales table and write a parser for it.

Run:
    python test_loudoun_neighborhood.py

Delete this file after we've extracted what we need.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# ---------- DEBUG LOGGING SETUP (before scraper kicks off) ----------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
# Quiet noisy third parties
for noisy in ("playwright", "asyncio", "urllib3", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("loudoun_test")


async def main():
    # Import after logging is configured so the scraper inherits the level
    from pipa.clients.scrapers.loudoun_parcel import LoudounParcelScraper

    target = ("22817", "PORTICO", "PL")
    logger.info("=" * 70)
    logger.info("Loudoun Neighborhood Sales test")
    logger.info("Target address: %s %s %s", *target)
    logger.info("Tabs requested: ['Neighborhood Sales']")
    logger.info("Browser: headless=False so we can watch")
    logger.info("=" * 70)

    scraper = LoudounParcelScraper(headless=False)
    try:
        result = await scraper.scrape_property(
            target[0], target[1], target[2],
            tabs=["Neighborhood Sales"],
        )
    finally:
        await scraper.close()

    logger.info("=" * 70)
    logger.info("Scrape complete. Top-level result keys: %s", list(result.keys()))

    if result.get("_error"):
        logger.error("Scrape failed with error: %s", result["_error"])
        return

    ns = result.get("Neighborhood Sales") or {}
    logger.info("Neighborhood Sales tab status: %s", ns.get("_status", "ok"))
    logger.info("Neighborhood Sales row count: %d", ns.get("_row_count", 0))

    rows = ns.get("_rows") or []
    logger.info("First 15 rows:")
    for i, row in enumerate(rows[:15]):
        logger.info("  [%2d] %r", i, row)

    out_path = Path("loudoun_neighborhood_test.json")
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote raw scrape result to %s", out_path.resolve())
    logger.info("=" * 70)


if __name__ == "__main__":
    if sys.platform == "win32":
        # Playwright needs ProactorEventLoop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
