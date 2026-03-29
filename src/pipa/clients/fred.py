"""FRED (Federal Reserve Economic Data) API client for mortgage rates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)

_SERIES_MAP = {
    30: "MORTGAGE30US",
    15: "MORTGAGE15US",
}


class FREDClient(BaseClient):
    """Client for the FRED API — primarily for current mortgage rates.

    API docs: https://fred.stlouisfed.org/docs/api/fred/
    """

    source_name = "fred"
    base_url = "https://api.stlouisfed.org/fred"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 6,  # rates change weekly, but keep cache short
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    async def get_current_rate(self, term_years: int = 30) -> float | None:
        """Return the latest mortgage rate as a decimal (e.g. 0.065 for 6.5%).

        Args:
            term_years: 30 for 30-year fixed, 15 for 15-year fixed.

        Returns:
            The latest mortgage rate as a decimal, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        series_id = _SERIES_MAP.get(term_years)
        if series_id is None:
            return None

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }

        data = await self.get("/series/observations", params=params)
        if data is None:
            return None

        try:
            observations = data.get("observations", [])
            if not observations:
                return None
            value = float(observations[0]["value"])
            return value / 100.0
        except (KeyError, ValueError, IndexError, TypeError):
            return None

    async def get_rate_history(
        self, term_years: int = 30, limit: int = 52
    ) -> list[dict] | None:
        """Return recent mortgage rate observations.

        Args:
            term_years: 30 or 15.
            limit: Number of weekly observations to return.

        Returns:
            List of ``{"date": str, "value": float}`` dicts, or ``None``.
        """
        if not self.api_key:
            return None

        series_id = _SERIES_MAP.get(term_years)
        if series_id is None:
            return None

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }

        data = await self.get("/series/observations", params=params)
        if data is None:
            return None

        try:
            observations = data.get("observations", [])
            result = []
            for obs in observations:
                try:
                    result.append({
                        "date": obs["date"],
                        "value": float(obs["value"]) / 100.0,
                    })
                except (KeyError, ValueError):
                    continue
            return result
        except (TypeError, AttributeError):
            return None
