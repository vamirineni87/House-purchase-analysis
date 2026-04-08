"""Structured logging setup.

Wires application loggers (pipa.*) AND uvicorn HTTP access logs into a
single backend.log file plus stderr. Adds a SQLAlchemy slow-query event
listener so any query taking >100ms is flagged with its SQL text.

Without this, server.log goes stale and we have no visibility into
which API requests are slow or hanging — exactly the visibility we need
when the page is "stuck loading" while the background pipeline runs.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path


# Threshold for "slow query" warnings (milliseconds).
SLOW_QUERY_MS = 100


def setup_logging(level: str = "INFO"):
    """Configure structured logging for the application.

    Producers wired into backend.log + stderr:
        - pipa.* (application code)
        - uvicorn (server lifecycle)
        - uvicorn.access (one line per HTTP request)
        - uvicorn.error
        - sqlalchemy slow queries (via event listener attached separately)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- Handlers ----
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "backend.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)

    handlers = [stderr_handler, file_handler]

    # ---- Application loggers ----
    root = logging.getLogger("pipa")
    root.setLevel(log_level)
    # Avoid duplicate handlers on hot reload
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)
    root.propagate = False

    # ---- Uvicorn loggers (server lifecycle + HTTP access) ----
    # uvicorn writes its own access lines like:
    #     INFO:     127.0.0.1:54422 - "GET /api/v1/properties HTTP/1.1" 200 OK
    # We capture them by attaching our handlers to its named loggers.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ulog = logging.getLogger(name)
        ulog.setLevel(log_level)
        ulog.handlers.clear()
        for h in handlers:
            ulog.addHandler(h)
        ulog.propagate = False

    # ---- Verbose modules for troubleshooting ----
    logging.getLogger("pipa.services.comp_service").setLevel(logging.DEBUG)
    logging.getLogger("pipa.clients.scrapers").setLevel(logging.DEBUG)
    logging.getLogger("pipa.services.listing_ingest").setLevel(logging.DEBUG)
    logging.getLogger("pipa.services.pipeline_orchestrator").setLevel(logging.DEBUG)
    logging.getLogger("pipa.api").setLevel(logging.DEBUG)
    logging.getLogger("pipa.core.middleware").setLevel(logging.DEBUG)

    # ---- Quiet noisy third-party libraries ----
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    return root


def install_sqlalchemy_slow_query_listener(engine):
    """Attach a before/after-cursor listener to flag slow SQL queries.

    SQLAlchemy already raises ``ExecutionError`` for failures. This adds
    a *timing* probe: any individual query that takes longer than
    SLOW_QUERY_MS (default 100ms) is logged at WARNING with the SQL
    text and parameters. Useful for finding the queries that block
    the API while the background pipeline holds the write lock.

    Pass either an async engine (we attach to ``engine.sync_engine``)
    or a sync engine.
    """
    from sqlalchemy import event

    log = logging.getLogger("pipa.core.database.slow_query")
    target = getattr(engine, "sync_engine", engine)

    @event.listens_for(target, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        context._pipa_query_start = time.monotonic()

    @event.listens_for(target, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        start = getattr(context, "_pipa_query_start", None)
        if start is None:
            return
        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms >= SLOW_QUERY_MS:
            sql_summary = " ".join(statement.split())[:300]
            log.warning(
                "SLOW QUERY %.0fms: %s | params=%r",
                elapsed_ms, sql_summary, parameters if not executemany else "[batch]",
            )

    log.info("SQLAlchemy slow-query listener installed (threshold=%dms)", SLOW_QUERY_MS)
