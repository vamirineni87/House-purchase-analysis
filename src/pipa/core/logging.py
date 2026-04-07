"""Structured logging setup."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO"):
    """Configure structured logging for the application."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    # Also log to file for post-mortem debugging
    from pathlib import Path
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "backend.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger("pipa")
    root.setLevel(log_level)
    root.addHandler(handler)
    root.addHandler(file_handler)

    # Debug comp service and scrapers for troubleshooting
    logging.getLogger("pipa.services.comp_service").setLevel(logging.DEBUG)
    logging.getLogger("pipa.clients.scrapers").setLevel(logging.DEBUG)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    return root
