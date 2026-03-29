"""ArcGIS REST API base client with pagination and geometry support."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from ..base import BaseClient

logger = logging.getLogger(__name__)

# ArcGIS REST default page size before exceededTransferLimit kicks in
_DEFAULT_RESULT_OFFSET = 0
_MAX_PAGE_SIZE = 2000


class ArcGISClient(BaseClient):
    """Base client for ArcGIS REST MapServer / FeatureServer endpoints.

    Handles:
    - Automatic pagination when exceededTransferLimit is returned
    - Standard query, identify, and get-by-ID operations
    - Response parsing into a consistent list-of-feature format
    """

    source_name: str = "arcgis"

    def __init__(
        self,
        base_url: str = "",
        rate_limit: float = 5.0,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 24,
        raw_payload_dir: Path | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        super().__init__(
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl_hours,
            raw_payload_dir=raw_payload_dir,
            max_retries=max_retries,
            timeout=timeout,
        )
        if base_url:
            self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Core query with pagination
    # ------------------------------------------------------------------

    async def query(
        self,
        layer_id: int,
        where: str = "1=1",
        out_fields: str = "*",
        geometry: dict | None = None,
        spatial_rel: str | None = None,
        return_geometry: bool = True,
        out_sr: int = 4326,
    ) -> list[dict]:
        """Query a MapServer/FeatureServer layer with automatic pagination.

        Args:
            layer_id: Layer index in the service.
            where: SQL WHERE clause for attribute filtering.
            out_fields: Comma-separated field names, or ``"*"`` for all.
            geometry: Optional geometry dict for spatial queries (JSON envelope/point/polygon).
            spatial_rel: Spatial relationship (e.g. ``"esriSpatialRelIntersects"``).
            return_geometry: Whether to include feature geometries in results.
            out_sr: Output spatial reference WKID (default WGS 84).

        Returns:
            Flat list of feature dicts, each with ``"attributes"`` and optionally ``"geometry"``.
        """
        all_features: list[dict] = []
        result_offset = _DEFAULT_RESULT_OFFSET

        while True:
            params: dict[str, Any] = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": str(return_geometry).lower(),
                "outSR": out_sr,
                "f": "json",
                "resultOffset": result_offset,
                "resultRecordCount": _MAX_PAGE_SIZE,
            }
            if geometry is not None:
                import json as _json

                params["geometry"] = _json.dumps(geometry) if isinstance(geometry, dict) else geometry
                params["geometryType"] = self._infer_geometry_type(geometry)
                params["inSR"] = out_sr
            if spatial_rel:
                params["spatialRel"] = spatial_rel

            url = f"/{layer_id}/query"
            data = await self.get(url, params=params)

            if data is None:
                logger.warning("ArcGIS query returned None for layer %d", layer_id)
                break

            if "error" in data:
                logger.error("ArcGIS query error: %s", data["error"])
                break

            features = data.get("features", [])
            all_features.extend(features)

            # Check for pagination
            if data.get("exceededTransferLimit", False) and len(features) > 0:
                result_offset += len(features)
                logger.debug(
                    "Paginating ArcGIS query: offset=%d, total so far=%d",
                    result_offset,
                    len(all_features),
                )
            else:
                break

        return all_features

    # ------------------------------------------------------------------
    # Identify
    # ------------------------------------------------------------------

    async def identify(
        self,
        geometry: dict,
        layer_ids: str = "all",
        tolerance: int = 5,
        map_extent: dict | None = None,
    ) -> list[dict]:
        """Identify features at a given geometry across one or more layers.

        Args:
            geometry: Point/envelope geometry dict.
            layer_ids: Comma-separated layer IDs, ``"all"``, ``"top"``, or ``"visible"``.
            tolerance: Pixel tolerance for the identify hit-test.
            map_extent: Current map extent dict. Defaults to a small envelope around the geometry.

        Returns:
            List of result dicts from the identify operation.
        """
        import json as _json

        if map_extent is None:
            # Build a small default extent around the geometry
            map_extent = self._default_extent(geometry)

        params: dict[str, Any] = {
            "geometry": _json.dumps(geometry) if isinstance(geometry, dict) else geometry,
            "geometryType": self._infer_geometry_type(geometry),
            "sr": 4326,
            "layers": f"all:{layer_ids}" if layer_ids != "all" else "all",
            "tolerance": tolerance,
            "mapExtent": _json.dumps(map_extent) if isinstance(map_extent, dict) else map_extent,
            "imageDisplay": "600,550,96",
            "returnGeometry": "true",
            "f": "json",
        }

        data = await self.get("/identify", params=params)
        if data is None:
            return []
        return data.get("results", [])

    # ------------------------------------------------------------------
    # Single feature by object ID
    # ------------------------------------------------------------------

    async def get_feature_by_id(self, layer_id: int, object_id: int) -> dict | None:
        """Fetch a single feature by its object ID.

        Args:
            layer_id: Layer index in the service.
            object_id: The feature's OBJECTID value.

        Returns:
            Feature dict with ``"attributes"`` and ``"geometry"``, or ``None``.
        """
        features = await self.query(
            layer_id=layer_id,
            where=f"OBJECTID={object_id}",
            out_fields="*",
            return_geometry=True,
        )
        return features[0] if features else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_geometry_type(geometry: Any) -> str:
        """Infer the ArcGIS geometry type string from a geometry dict."""
        if isinstance(geometry, dict):
            if "rings" in geometry:
                return "esriGeometryPolygon"
            if "paths" in geometry:
                return "esriGeometryPolyline"
            if "x" in geometry and "y" in geometry:
                return "esriGeometryPoint"
            if "xmin" in geometry:
                return "esriGeometryEnvelope"
        return "esriGeometryPoint"

    @staticmethod
    def _default_extent(geometry: dict) -> dict:
        """Build a small bounding box around a geometry for identify calls."""
        if "x" in geometry and "y" in geometry:
            x, y = geometry["x"], geometry["y"]
            delta = 0.005  # ~500m
            return {"xmin": x - delta, "ymin": y - delta, "xmax": x + delta, "ymax": y + delta}
        if "xmin" in geometry:
            return geometry
        # Fallback: whole CONUS
        return {"xmin": -125, "ymin": 24, "xmax": -66, "ymax": 50}
