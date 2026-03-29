"""NOAA Climate Data Online (CDO) API client."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import BaseClient

logger = logging.getLogger(__name__)


class NOAAClient(BaseClient):
    """Client for the NOAA Climate Data Online (CDO) Web Services v2.

    API docs: https://www.ncei.noaa.gov/cdo-web/webservices/v2
    Requires a free API token from https://www.ncdc.noaa.gov/cdo-web/token

    Provides climate normals, historical weather data, and station lookup
    for property risk/comfort assessment.
    """

    source_name = "noaa_cdo"
    base_url = "https://www.ncei.noaa.gov/cdo-web/api/v2"

    def __init__(
        self,
        api_key: str = "",
        rate_limit: float = 5.0,  # NOAA allows 5 req/sec with token
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 720,  # 30 days — climate normals are static
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            api_key=api_key,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    def _default_headers(self) -> dict[str, str]:
        headers = super()._default_headers()
        if self.api_key:
            headers["token"] = self.api_key
        return headers

    # ------------------------------------------------------------------
    # Station lookup
    # ------------------------------------------------------------------

    async def find_nearest_station(
        self,
        lat: float,
        lon: float,
        dataset_id: str = "NORMAL_ANN",
        limit: int = 5,
    ) -> dict | None:
        """Find the nearest weather station to a given coordinate.

        Args:
            lat: Latitude.
            lon: Longitude.
            dataset_id: NOAA dataset to filter stations by. Default is
                annual climate normals (``NORMAL_ANN``).
            limit: Maximum number of stations to return.

        Returns:
            Dict with station info (id, name, latitude, longitude, etc.),
            or ``None`` on failure. Returns the single nearest station.
        """
        if not self.api_key:
            return None

        # Build a small bounding box around the point (~50km)
        delta = 0.5  # roughly 50km at mid-latitudes
        extent = f"{lat - delta},{lon - delta},{lat + delta},{lon + delta}"

        params = {
            "datasetid": dataset_id,
            "extent": extent,
            "limit": limit,
            "sortfield": "name",
            "sortorder": "asc",
        }

        data = await self.get("/stations", params=params)
        if data is None:
            return None

        results = data.get("results", [])
        if not results:
            return None

        # Find the nearest by simple Euclidean distance
        def _dist(station: dict) -> float:
            slat = station.get("latitude", 0)
            slon = station.get("longitude", 0)
            return (slat - lat) ** 2 + (slon - lon) ** 2

        nearest = min(results, key=_dist)
        return nearest

    # ------------------------------------------------------------------
    # Climate normals
    # ------------------------------------------------------------------

    async def get_climate_normals(
        self,
        station_id: str,
        datatype_ids: list[str] | None = None,
    ) -> dict | None:
        """Fetch climate normals (30-year averages) for a station.

        Args:
            station_id: NOAA station ID (e.g. ``"GHCND:USW00093738"``
                for Washington Dulles).
            datatype_ids: List of specific datatype IDs to retrieve.
                If ``None``, fetches common normals:
                - ``ANN-TAVG-NORMAL`` — annual average temperature
                - ``ANN-PRCP-NORMAL`` — annual average precipitation
                - ``ANN-SNOW-NORMAL`` — annual average snowfall
                - ``ANN-HTDD-NORMAL`` — heating degree days
                - ``ANN-CLDD-NORMAL`` — cooling degree days

        Returns:
            Dict mapping datatype IDs to their values, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        if datatype_ids is None:
            datatype_ids = [
                "ANN-TAVG-NORMAL",
                "ANN-PRCP-NORMAL",
                "ANN-SNOW-NORMAL",
                "ANN-HTDD-NORMAL",
                "ANN-CLDD-NORMAL",
            ]

        params = {
            "datasetid": "NORMAL_ANN",
            "stationid": station_id,
            "datatypeid": ",".join(datatype_ids),
            "limit": 100,
        }

        data = await self.get("/data", params=params)
        if data is None:
            return None

        results = data.get("results", [])
        normals: dict = {}
        for record in results:
            dtype = record.get("datatype")
            value = record.get("value")
            if dtype and value is not None:
                normals[dtype] = value

        return normals if normals else None

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    async def get_historical_data(
        self,
        station_id: str,
        datatype_id: str,
        start_date: str,
        end_date: str,
        limit: int = 1000,
    ) -> list[dict] | None:
        """Fetch historical weather observations for a station.

        Args:
            station_id: NOAA station ID.
            datatype_id: Data type (e.g. ``"TMAX"``, ``"PRCP"``).
            start_date: Start date in ``YYYY-MM-DD`` format.
            end_date: End date in ``YYYY-MM-DD`` format.
            limit: Maximum records per request.

        Returns:
            List of observation dicts, or ``None`` on failure.
        """
        if not self.api_key:
            return None

        params = {
            "datasetid": "GHCND",
            "stationid": station_id,
            "datatypeid": datatype_id,
            "startdate": start_date,
            "enddate": end_date,
            "limit": limit,
            "units": "standard",
        }

        data = await self.get("/data", params=params)
        if data is None:
            return None

        return data.get("results", [])
