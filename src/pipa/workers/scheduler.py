"""APScheduler setup with SQLite job store.

Single-writer design: only one scheduler process runs at a time.
Uses a file lock to prevent concurrent scheduler instances.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

logger = logging.getLogger(__name__)

# Module-level singleton
_scheduler: AsyncIOScheduler | None = None
_lock_path = Path(tempfile.gettempdir()) / "pipa_scheduler.lock"


def _acquire_lock() -> bool:
    """Try to acquire a file-based lock so only one scheduler runs."""
    try:
        # On Windows, os.open with O_CREAT|O_EXCL fails if file exists
        # On restart, stale locks are cleaned up by checking PID
        if _lock_path.exists():
            try:
                stored_pid = int(_lock_path.read_text().strip())
                # Check if the process is still alive
                try:
                    os.kill(stored_pid, 0)
                    # Process is alive — another scheduler is running
                    return False
                except (OSError, ProcessLookupError):
                    # Stale lock from a dead process — remove it
                    _lock_path.unlink(missing_ok=True)
            except (ValueError, OSError):
                _lock_path.unlink(missing_ok=True)

        _lock_path.write_text(str(os.getpid()))
        return True
    except Exception:
        logger.exception("Failed to acquire scheduler lock")
        return False


def _release_lock():
    """Release the scheduler file lock."""
    try:
        if _lock_path.exists():
            stored_pid = int(_lock_path.read_text().strip())
            if stored_pid == os.getpid():
                _lock_path.unlink(missing_ok=True)
    except Exception:
        logger.exception("Failed to release scheduler lock")


def create_scheduler(database_url: str = "sqlite:///./pipa.db") -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Args:
        database_url: Synchronous SQLAlchemy URL for the job store.
                      Note: APScheduler 3.x uses sync engines internally.
    """
    # Strip the async driver prefix if present
    sync_url = database_url.replace("sqlite+aiosqlite", "sqlite")

    jobstores = {
        "default": SQLAlchemyJobStore(url=sync_url, tablename="apscheduler_jobs"),
    }

    executors = {
        "default": AsyncIOExecutor(),
    }

    job_defaults = {
        "coalesce": True,           # Collapse missed runs into one
        "max_instances": 1,         # Single writer — never overlap
        "misfire_grace_time": 3600, # Allow up to 1 hour late
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
    )

    return scheduler


def register_jobs(scheduler: AsyncIOScheduler):
    """Register all recurring background jobs.

    Jobs are added with replace_existing=True so restarts don't create duplicates.
    """
    from pipa.workers.county_refresh import refresh_watched_properties
    from pipa.workers.listing_monitor import check_listing_changes
    from pipa.workers.alert_evaluator import evaluate_alerts
    from pipa.workers.source_health_checker import check_all_sources

    # County data refresh — once daily at 3 AM
    scheduler.add_job(
        refresh_watched_properties,
        trigger="cron",
        hour=3,
        minute=0,
        id="county_refresh",
        name="Refresh county data for watched properties",
        replace_existing=True,
    )

    # Listing monitor — every 4 hours
    scheduler.add_job(
        check_listing_changes,
        trigger="interval",
        hours=4,
        id="listing_monitor",
        name="Check for listing price/status changes",
        replace_existing=True,
    )

    # Alert evaluator — every 15 minutes
    scheduler.add_job(
        evaluate_alerts,
        trigger="interval",
        minutes=15,
        id="alert_evaluator",
        name="Evaluate alert subscription conditions",
        replace_existing=True,
    )

    # Source health check — every 6 hours
    scheduler.add_job(
        check_all_sources,
        trigger="interval",
        hours=6,
        id="source_health_check",
        name="Check data source health and availability",
        replace_existing=True,
    )

    logger.info(
        "Registered %d scheduled jobs: %s",
        len(list(scheduler.get_jobs())),
        [j.id for j in scheduler.get_jobs()],
    )


async def start_scheduler():
    """Start the background scheduler (call from CLI or FastAPI lifespan).

    Returns the scheduler instance, or None if another process holds the lock.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running in this process")
        return _scheduler

    if not _acquire_lock():
        logger.warning("Another scheduler process is already running — skipping")
        return None

    from pipa.core.dependencies import get_config

    config = get_config()
    _scheduler = create_scheduler(config.database_url)
    register_jobs(_scheduler)
    _scheduler.start()
    logger.info("Background scheduler started (PID=%d)", os.getpid())
    return _scheduler


async def stop_scheduler():
    """Gracefully stop the scheduler and release the lock."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Background scheduler stopped")

    _release_lock()
    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the current scheduler instance (may be None)."""
    return _scheduler
