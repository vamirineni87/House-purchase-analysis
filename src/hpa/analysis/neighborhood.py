"""Neighborhood quality analysis combining data from multiple APIs."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from hpa.analysis.base import BaseAnalyzer
from hpa.config import AppConfig
from hpa.models.property import PropertyDetails
from hpa.models.neighborhood import (
    CrimeStats,
    Demographics,
    FloodRisk,
    NeighborhoodAnalysisResult,
    SchoolRating,
    WalkabilityScores,
)
from hpa.api.greatschools import GreatSchoolsClient
from hpa.api.fbi_crime import FBICrimeClient
from hpa.api.openfema import OpenFEMAClient
from hpa.api.walkscore import WalkScoreClient
from hpa.api.census import CensusClient

logger = logging.getLogger(__name__)

# National median household income used as a baseline for demographics scoring.
_NATIONAL_MEDIAN_INCOME = 75_000.0

# Composite score weights keyed by data category.
_WEIGHTS: dict[str, float] = {
    "schools": 0.30,
    "crime": 0.20,
    "walkability": 0.20,
    "flood": 0.15,
    "demographics": 0.15,
}

# State abbreviation -> FIPS code mapping (all 50 states + DC).
_STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}


class NeighborhoodAnalyzer(BaseAnalyzer):
    """Analyzes neighborhood quality using schools, crime, walkability,
    flood risk, and demographic data."""

    @property
    def name(self) -> str:
        return "Neighborhood Analysis"

    @property
    def requires_api(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> NeighborhoodAnalysisResult:
        """Fetch neighborhood data from all sources and compute a composite score.

        Each data fetch is wrapped in a try/except so that a single API
        failure never crashes the entire analysis.
        """
        schools = self._fetch_schools(property_details, config)
        crime = self._fetch_crime(property_details, config)
        walkability = self._fetch_walkability(property_details, config)
        flood_risk = self._fetch_flood_risk(property_details, config)
        demographics = self._fetch_demographics(property_details, config)

        composite_score, data_completeness = self._compute_composite_score(
            schools=schools,
            crime=crime,
            walkability=walkability,
            flood_risk=flood_risk,
            demographics=demographics,
        )

        return NeighborhoodAnalysisResult(
            schools=schools,
            crime=crime,
            walkability=walkability,
            flood_risk=flood_risk,
            demographics=demographics,
            composite_score=round(composite_score, 1) if composite_score is not None else None,
            data_completeness=round(data_completeness, 2),
        )

    # ------------------------------------------------------------------
    # Data fetchers
    # ------------------------------------------------------------------

    def _fetch_schools(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> list[SchoolRating]:
        """Fetch nearby school ratings from GreatSchools."""
        try:
            if not config.api_keys.greatschools:
                return []

            addr = property_details.address
            if addr.latitude is None or addr.longitude is None:
                logger.info("No lat/lon on property; skipping school lookup.")
                return []

            client = GreatSchoolsClient(api_key=config.api_keys.greatschools)
            raw_schools = asyncio.run(
                client.get_nearby_schools(lat=addr.latitude, lon=addr.longitude)
            )
            if not raw_schools:
                return []

            results: list[SchoolRating] = []
            for school in raw_schools:
                results.append(
                    SchoolRating(
                        name=school.get("name", "Unknown"),
                        type=self._classify_school_type(school),
                        rating=self._safe_int(school.get("rating", school.get("gsRating"))),
                        distance_miles=self._safe_float(school.get("distance")),
                        grades=school.get("grades", school.get("gradeRange")),
                    )
                )
            return results

        except Exception:
            logger.exception("Failed to fetch school data.")
            return []

    def _fetch_crime(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> Optional[CrimeStats]:
        """Fetch crime statistics from the FBI Crime Data Explorer."""
        try:
            state = property_details.address.state.upper()
            client = FBICrimeClient()
            raw = asyncio.run(client.get_state_crime(state_abbr=state))
            if not raw:
                return None

            # The API returns data under a "results" key or as a list.
            results_list = raw.get("results", []) if isinstance(raw, dict) else []
            if not results_list:
                return None

            # Use the most recent year's data.
            latest = results_list[-1] if results_list else {}

            violent = self._safe_float(latest.get("violent_crime"))
            property_crime = self._safe_float(latest.get("property_crime"))
            population = self._safe_float(latest.get("population")) or 1.0
            data_year = self._safe_int(latest.get("year"))

            violent_rate = (violent / population * 100_000) if violent else None
            property_rate = (property_crime / population * 100_000) if property_crime else None

            # Derive safety score (1-10): lower crime -> higher safety.
            safety_score = self._crime_rate_to_safety(violent_rate)

            return CrimeStats(
                violent_crime_rate=round(violent_rate, 1) if violent_rate else None,
                property_crime_rate=round(property_rate, 1) if property_rate else None,
                overall_safety_score=safety_score,
                data_year=data_year,
            )

        except Exception:
            logger.exception("Failed to fetch crime data.")
            return None

    def _fetch_walkability(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> Optional[WalkabilityScores]:
        """Fetch Walk Score, Transit Score, and Bike Score."""
        try:
            if not config.api_keys.walkscore:
                return None

            addr = property_details.address
            if addr.latitude is None or addr.longitude is None:
                return None

            full_address = f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}"
            client = WalkScoreClient(api_key=config.api_keys.walkscore)
            raw = asyncio.run(
                client.get_score(lat=addr.latitude, lon=addr.longitude, address=full_address)
            )
            if not raw:
                return None

            return WalkabilityScores(
                walk_score=self._safe_int(raw.get("walkscore")),
                transit_score=self._safe_int(raw.get("transit", {}).get("score") if isinstance(raw.get("transit"), dict) else raw.get("transit_score")),
                bike_score=self._safe_int(raw.get("bike", {}).get("score") if isinstance(raw.get("bike"), dict) else raw.get("bike_score")),
                description=raw.get("description"),
            )

        except Exception:
            logger.exception("Failed to fetch walkability data.")
            return None

    def _fetch_flood_risk(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> Optional[FloodRisk]:
        """Fetch flood risk data from OpenFEMA."""
        try:
            zip_code = property_details.address.zip_code
            client = OpenFEMAClient()
            raw = asyncio.run(client.get_flood_risk(zip_code=zip_code))
            if not raw:
                return None

            declarations = []
            if isinstance(raw, dict):
                declarations = raw.get("DisasterDeclarationsSummaries", [])
            elif isinstance(raw, list):
                declarations = raw

            recent_disasters = len(declarations)

            # Determine risk level based on number of recent flood disasters.
            if recent_disasters == 0:
                risk_level = "low"
            elif recent_disasters <= 3:
                risk_level = "moderate"
            else:
                risk_level = "high"

            in_floodplain = recent_disasters > 0
            flood_insurance_required = risk_level == "high"

            return FloodRisk(
                flood_zone=None,  # Not available from FEMA declarations endpoint
                in_floodplain=in_floodplain,
                flood_insurance_required=flood_insurance_required,
                recent_disasters=recent_disasters,
                risk_level=risk_level,
            )

        except Exception:
            logger.exception("Failed to fetch flood risk data.")
            return None

    def _fetch_demographics(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> Optional[Demographics]:
        """Fetch demographic data from the US Census Bureau."""
        try:
            if not config.api_keys.census:
                return None

            state_abbr = property_details.address.state.upper()
            state_fips = _STATE_FIPS.get(state_abbr)
            if not state_fips:
                logger.warning("Unknown state abbreviation: %s", state_abbr)
                return None

            client = CensusClient(api_key=config.api_keys.census)
            raw = asyncio.run(client.get_demographics(state_fips=state_fips))
            if not raw:
                return None

            return Demographics(
                total_population=self._safe_int(raw.get("B01001_001E")),
                median_household_income=self._safe_float(raw.get("B19013_001E")),
                median_home_value=self._safe_float(raw.get("B25077_001E")),
                population_density=None,  # Not directly available from this endpoint
            )

        except Exception:
            logger.exception("Failed to fetch demographics data.")
            return None

    # ------------------------------------------------------------------
    # Composite score calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_composite_score(
        schools: list[SchoolRating],
        crime: Optional[CrimeStats],
        walkability: Optional[WalkabilityScores],
        flood_risk: Optional[FloodRisk],
        demographics: Optional[Demographics],
    ) -> tuple[Optional[float], float]:
        """Compute a weighted composite neighborhood score (0-100).

        Only factors with available data are included; weights are
        re-normalized proportionally.

        Returns:
            (composite_score, data_completeness) where data_completeness
            is the fraction of the 5 data categories that returned data.
        """
        total_sources = 5
        available_count = 0
        weighted_scores: dict[str, float] = {}

        # --- Schools ---
        rated_schools = [s for s in schools if s.rating is not None]
        if rated_schools:
            avg_rating = sum(s.rating for s in rated_schools) / len(rated_schools)
            weighted_scores["schools"] = (avg_rating / 10.0) * 100.0
            available_count += 1

        # --- Crime ---
        if crime and crime.overall_safety_score is not None:
            weighted_scores["crime"] = (crime.overall_safety_score / 10.0) * 100.0
            available_count += 1

        # --- Walkability ---
        if walkability and walkability.walk_score is not None:
            weighted_scores["walkability"] = float(walkability.walk_score)
            available_count += 1

        # --- Flood risk ---
        if flood_risk and flood_risk.risk_level != "unknown":
            flood_score_map = {"low": 100.0, "moderate": 50.0, "high": 20.0}
            weighted_scores["flood"] = flood_score_map.get(flood_risk.risk_level, 50.0)
            available_count += 1

        # --- Demographics ---
        if demographics and demographics.median_household_income is not None:
            income_ratio = demographics.median_household_income / _NATIONAL_MEDIAN_INCOME
            # Cap the score at 100 to keep it on the 0-100 scale.
            demo_score = min(income_ratio * 100.0, 100.0)
            weighted_scores["demographics"] = demo_score
            available_count += 1

        data_completeness = available_count / total_sources

        if not weighted_scores:
            return None, data_completeness

        # Re-normalize weights to sum to 1.0 for the available categories.
        active_weights = {k: _WEIGHTS[k] for k in weighted_scores}
        weight_sum = sum(active_weights.values())

        composite = sum(
            (active_weights[k] / weight_sum) * weighted_scores[k]
            for k in weighted_scores
        )

        return composite, data_completeness

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_school_type(school: dict) -> str:
        """Classify a school as elementary, middle, or high."""
        school_type = school.get("type", school.get("schoolType", "")).lower()
        if "elem" in school_type or "primary" in school_type:
            return "elementary"
        if "mid" in school_type or "junior" in school_type:
            return "middle"
        if "high" in school_type or "senior" in school_type:
            return "high"

        # Fallback: try to infer from grade range.
        grades = school.get("grades", school.get("gradeRange", ""))
        if grades:
            grades_lower = str(grades).lower()
            if "pk" in grades_lower or "kg" in grades_lower or "k" in grades_lower:
                return "elementary"
            if "6" in grades_lower or "7" in grades_lower or "8" in grades_lower:
                return "middle"
        return "high"

    @staticmethod
    def _crime_rate_to_safety(violent_rate: Optional[float]) -> Optional[int]:
        """Convert a violent crime rate (per 100k) to a 1-10 safety score.

        National average is roughly 380 per 100k. Lower rate -> higher score.
        """
        if violent_rate is None:
            return None
        # Scale: 0 violent crimes = 10, 800+ = 1
        score = max(1, min(10, round(10 - (violent_rate / 100.0))))
        return score

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        """Convert a value to int, returning None on failure."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Convert a value to float, returning None on failure."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
