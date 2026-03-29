"""Loudoun County GIS (LOGIS) MapServer client."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import ArcGISClient

logger = logging.getLogger(__name__)

# Loudoun County LOGIS MapServer layer IDs
# Verify against: https://logis.loudoun.gov/arcgis/rest/services
LAYER_PARCELS = 0
LAYER_ZONING = 1


class LoudounGISClient(ArcGISClient):
    """Client for Loudoun County's ArcGIS-based GIS REST services.

    Service endpoint:
        https://logis.loudoun.gov/arcgis/rest/services/Parcels/MapServer
    """

    source_name = "loudoun_gis"
    base_url = "https://logis.loudoun.gov/arcgis/rest/services/Parcels/MapServer"

    def __init__(
        self,
        rate_limit: float = 3.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 168,  # 1 week
        raw_payload_dir: Path | None = None,
    ):
        super().__init__(
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
        )

    # ------------------------------------------------------------------
    # Parcel lookups
    # ------------------------------------------------------------------

    async def get_parcel_by_address(self, address: str) -> dict | None:
        """Look up a parcel feature by street address.

        Returns:
            First matching parcel feature dict, or ``None``.
        """
        safe_addr = address.replace("'", "''").upper()
        where = f"UPPER(STREET_ADDRESS) LIKE '%{safe_addr}%'"

        features = await self.query(
            layer_id=LAYER_PARCELS,
            where=where,
            out_fields="*",
            return_geometry=True,
        )
        return features[0] if features else None

    async def get_parcel_by_pin(self, pin: str) -> dict | None:
        """Look up a parcel feature by tax map PIN.

        Args:
            pin: Loudoun County parcel identification number.

        Returns:
            Matching parcel feature dict, or ``None``.
        """
        safe_pin = pin.replace("'", "''").strip()
        normalized = safe_pin.replace(" ", "").replace("-", "")
        where = (
            f"PIN = '{safe_pin}' OR "
            f"REPLACE(REPLACE(PIN, ' ', ''), '-', '') = '{normalized}'"
        )

        features = await self.query(
            layer_id=LAYER_PARCELS,
            where=where,
            out_fields="*",
            return_geometry=True,
        )
        return features[0] if features else None

    # ------------------------------------------------------------------
    # Spatial lookups using parcel geometry
    # ------------------------------------------------------------------

    async def get_zoning(self, parcel_geometry: dict) -> dict | None:
        """Fetch zoning designation that intersects the given parcel geometry.

        Args:
            parcel_geometry: Geometry dict (polygon rings) from a parcel feature.

        Returns:
            First intersecting zoning feature, or ``None``.
        """
        features = await self.query(
            layer_id=LAYER_ZONING,
            where="1=1",
            out_fields="*",
            geometry=parcel_geometry,
            spatial_rel="esriSpatialRelIntersects",
            return_geometry=False,
        )
        return features[0] if features else None
