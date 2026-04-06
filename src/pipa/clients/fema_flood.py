"""FEMA National Flood Hazard Layer (NFHL) lookup.

Free ArcGIS REST API — no API key needed.
Returns flood zone designation for a lat/lng point.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

NFHL_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

# Flood zone risk levels for buyer interpretation
ZONE_RISK = {
    "A":  {"risk": "high",   "insurance": "required", "description": "100-year floodplain — mandatory flood insurance"},
    "AE": {"risk": "high",   "insurance": "required", "description": "100-year floodplain with base flood elevation"},
    "AH": {"risk": "high",   "insurance": "required", "description": "100-year shallow flooding (1-3 ft)"},
    "AO": {"risk": "high",   "insurance": "required", "description": "100-year sheet flow flooding (1-3 ft)"},
    "AR": {"risk": "high",   "insurance": "required", "description": "Flood risk due to levee restoration"},
    "V":  {"risk": "high",   "insurance": "required", "description": "Coastal flood zone with wave action"},
    "VE": {"risk": "high",   "insurance": "required", "description": "Coastal flood zone with wave action and BFE"},
    "X":  {"risk": "minimal","insurance": "not required", "description": "Minimal flood hazard"},
    "B":  {"risk": "moderate","insurance": "recommended", "description": "500-year floodplain (moderate risk)"},
    "C":  {"risk": "minimal","insurance": "not required", "description": "Minimal flood hazard"},
    "D":  {"risk": "unknown","insurance": "unknown", "description": "Undetermined flood hazard"},
}


async def lookup_flood_zone(lat: float, lng: float) -> dict | None:
    """Query FEMA NFHL for flood zone at a point.

    Args:
        lat: Latitude (e.g. 38.98543)
        lng: Longitude (e.g. -77.52305)

    Returns:
        Dict with flood zone info, or None on failure::

            {
                "flood_zone": "X",
                "zone_subtype": "AREA OF MINIMAL FLOOD HAZARD",
                "sfha": False,  # Special Flood Hazard Area
                "risk": "minimal",
                "insurance": "not required",
                "description": "Minimal flood hazard",
                "dfirm_id": "51107C",
            }
    """
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DFIRM_ID",
        "returnGeometry": "false",
        "f": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(NFHL_URL, params=params)
            if r.status_code != 200:
                logger.warning("FEMA NFHL query failed: HTTP %d", r.status_code)
                return None

            data = r.json()
            features = data.get("features", [])
            if not features:
                return None

            attrs = features[0].get("attributes", {})
            zone = attrs.get("FLD_ZONE", "")
            zone_info = ZONE_RISK.get(zone, ZONE_RISK.get("D"))

            return {
                "flood_zone": zone,
                "zone_subtype": attrs.get("ZONE_SUBTY", ""),
                "sfha": attrs.get("SFHA_TF") == "T",
                "risk": zone_info["risk"],
                "insurance": zone_info["insurance"],
                "description": zone_info["description"],
                "base_flood_elevation": attrs.get("STATIC_BFE") if attrs.get("STATIC_BFE", -9999) != -9999 else None,
                "dfirm_id": attrs.get("DFIRM_ID", ""),
            }

    except Exception:
        logger.exception("FEMA flood zone lookup failed for %f, %f", lat, lng)
        return None
