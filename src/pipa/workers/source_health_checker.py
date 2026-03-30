"""Source health monitoring worker.

Pings each registered data source, records health status,
and compares DOM fingerprints for scraper targets to detect
site changes that might break scrapers.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from pipa.core.dependencies import get_config, get_session_factory
from pipa.models.alert import AlertEvent
from pipa.models.source import SourceHealth, SourceRegistry

logger = logging.getLogger(__name__)

# Known source endpoints to probe
# source_name -> { url, type, expected_status }
SOURCE_PROBES: dict[str, dict] = {
    "fairfax_gis": {
        "url": "https://www.fairfaxcounty.gov/euclid/rest/services/GIS/Property/MapServer?f=json",
        "type": "public_arcgis",
        "expected_status": 200,
    },
    "loudoun_gis": {
        "url": "https://logis.loudoun.gov/arcgis/rest/services?f=json",
        "type": "public_arcgis",
        "expected_status": 200,
    },
    "fairfax_icare": {
        "url": "https://icare.fairfaxcounty.gov/",
        "type": "public_site_scrape",
        "expected_status": 200,
    },
    "fairfax_plus": {
        "url": "https://plus.fairfaxcounty.gov/",
        "type": "public_site_scrape",
        "expected_status": 200,
    },
    "loudoun_parcel_db": {
        "url": "https://reparcelasmt.loudoun.gov/pt/search/commonsearch.aspx?mode=address",
        "type": "public_site_scrape",
        "expected_status": 200,
    },
    "loudoun_landmarc": {
        "url": "https://www.loudoun.gov/5823/LandMARC-Land-Management-Applications-Re",
        "type": "public_site_scrape",
        "expected_status": 200,
    },
    "fred_api": {
        "url": "https://api.stlouisfed.org/fred/series?series_id=MORTGAGE30US&api_key=DEMO&file_type=json",
        "type": "official_api",
        "expected_status": 200,
    },
    "census_api": {
        "url": "https://api.census.gov/data.html",
        "type": "official_api",
        "expected_status": 200,
    },
}

# Timeout for health probes (seconds)
PROBE_TIMEOUT = 15.0


async def check_all_sources():
    """Main entry point: check health of all registered data sources.

    Called by APScheduler every 6 hours.
    """
    logger.info("Starting source health check")
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            # Merge probes with any dynamically registered sources
            probes = dict(SOURCE_PROBES)
            result = await session.execute(select(SourceRegistry))
            for registry in result.scalars().all():
                if registry.source_name not in probes:
                    probes[registry.source_name] = {
                        "url": None,
                        "type": registry.source_type,
                        "expected_status": 200,
                    }

            healthy = 0
            degraded = 0
            broken = 0

            async with httpx.AsyncClient(
                timeout=PROBE_TIMEOUT,
                follow_redirects=True,
            ) as client:
                for source_name, probe_info in probes.items():
                    try:
                        health = await _check_source(client, source_name, probe_info)
                        session.add(health)

                        if health.status == "healthy":
                            healthy += 1
                        elif health.status == "degraded":
                            degraded += 1
                        else:
                            broken += 1

                        # Create alert for broken sources
                        if health.status in ("broken", "structure_changed"):
                            alert = AlertEvent(
                                property_id=None,
                                alert_type="source_degraded",
                                title=f"Data source '{source_name}' is {health.status}",
                                description=health.error_summary or f"Source {source_name} health check failed.",
                                severity="critical" if health.status == "broken" else "warning",
                                data={
                                    "source_name": source_name,
                                    "status": health.status,
                                    "latency_ms": health.latency_ms,
                                    "error": health.error_summary,
                                },
                                triggered_at=datetime.now(timezone.utc),
                            )
                            session.add(alert)

                    except Exception:
                        logger.exception("Error checking source %s", source_name)

            await session.commit()
            logger.info(
                "Source health check complete: %d healthy, %d degraded, %d broken",
                healthy,
                degraded,
                broken,
            )

        except Exception:
            logger.exception("Source health check job failed")
            await session.rollback()


async def _check_source(
    client: httpx.AsyncClient,
    source_name: str,
    probe_info: dict,
) -> SourceHealth:
    """Probe a single data source and return a SourceHealth record."""
    now = datetime.now(timezone.utc)
    url = probe_info.get("url")
    source_type = probe_info.get("type", "unknown")
    expected_status = probe_info.get("expected_status", 200)

    if url is None:
        return SourceHealth(
            source_name=source_name,
            checked_at=now,
            status="degraded",
            error_summary="No probe URL configured",
        )

    start = time.monotonic()
    try:
        response = await client.get(url)
        latency_ms = int((time.monotonic() - start) * 1000)

        # Compute fingerprint for scraper targets (DOM structure hash)
        fingerprint = None
        if source_type == "public_site_scrape" and response.status_code == 200:
            fingerprint = _compute_dom_fingerprint(response.text)

        # Check if status matches expected
        if response.status_code != expected_status:
            return SourceHealth(
                source_name=source_name,
                checked_at=now,
                status="degraded",
                latency_ms=latency_ms,
                error_summary=f"Expected HTTP {expected_status}, got {response.status_code}",
                fingerprint_hash=fingerprint,
            )

        # Check for high latency (> 10 seconds)
        if latency_ms > 10000:
            return SourceHealth(
                source_name=source_name,
                checked_at=now,
                status="degraded",
                latency_ms=latency_ms,
                error_summary=f"High latency: {latency_ms}ms",
                fingerprint_hash=fingerprint,
            )

        # Check fingerprint against previous for change detection
        if fingerprint:
            changed = await _check_fingerprint_changed(
                source_name, fingerprint
            )
            if changed:
                return SourceHealth(
                    source_name=source_name,
                    checked_at=now,
                    status="structure_changed",
                    latency_ms=latency_ms,
                    error_summary="DOM structure changed — scraper may need update",
                    fingerprint_hash=fingerprint,
                )

        return SourceHealth(
            source_name=source_name,
            checked_at=now,
            status="healthy",
            latency_ms=latency_ms,
            fingerprint_hash=fingerprint,
        )

    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - start) * 1000)
        return SourceHealth(
            source_name=source_name,
            checked_at=now,
            status="broken",
            latency_ms=latency_ms,
            error_summary=f"Connection timed out after {PROBE_TIMEOUT}s",
        )

    except httpx.ConnectError as e:
        return SourceHealth(
            source_name=source_name,
            checked_at=now,
            status="broken",
            error_summary=f"Connection failed: {str(e)[:200]}",
        )

    except Exception as e:
        return SourceHealth(
            source_name=source_name,
            checked_at=now,
            status="broken",
            error_summary=f"Unexpected error: {str(e)[:200]}",
        )


def _compute_dom_fingerprint(html: str) -> str:
    """Compute a structural fingerprint of an HTML page.

    Strips dynamic content (numbers, dates, session tokens) and hashes
    the structural skeleton so we detect layout changes but not data changes.
    """
    import re

    # Remove script/style content
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Remove tag content (keep structure)
    cleaned = re.sub(r">([^<]+)<", "><", cleaned)

    # Remove attributes that change (ids with numbers, session tokens, etc.)
    cleaned = re.sub(r'\s(id|value|name|action)="[^"]*"', "", cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return hashlib.sha256(cleaned.encode()).hexdigest()


async def _check_fingerprint_changed(source_name: str, new_fingerprint: str) -> bool:
    """Compare new fingerprint against the most recent stored one."""
    session_factory = get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(SourceHealth)
            .where(
                SourceHealth.source_name == source_name,
                SourceHealth.fingerprint_hash.isnot(None),
                SourceHealth.status.in_(["healthy", "structure_changed"]),
            )
            .order_by(SourceHealth.checked_at.desc())
            .limit(1)
        )
        previous = result.scalar_one_or_none()

        if previous is None:
            # First check — no comparison possible
            return False

        return previous.fingerprint_hash != new_fingerprint
