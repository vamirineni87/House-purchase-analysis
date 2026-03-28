"""Neighborhood analysis Pydantic v2 models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SchoolRating(BaseModel):
    """Rating information for a nearby school."""

    name: str
    type: str  # "elementary", "middle", "high"
    rating: Optional[int] = None  # 1-10 scale
    distance_miles: Optional[float] = None
    grades: Optional[str] = None


class CrimeStats(BaseModel):
    """Crime statistics for a neighborhood."""

    violent_crime_rate: Optional[float] = None  # per 100k
    property_crime_rate: Optional[float] = None
    overall_safety_score: Optional[int] = None  # 1-10
    data_year: Optional[int] = None


class WalkabilityScores(BaseModel):
    """Walkability and transit scores for a location."""

    walk_score: Optional[int] = None  # 0-100
    transit_score: Optional[int] = None
    bike_score: Optional[int] = None
    description: Optional[str] = None


class FloodRisk(BaseModel):
    """Flood risk assessment for a property location."""

    flood_zone: Optional[str] = None  # e.g., "X", "AE", "VE"
    in_floodplain: bool = False
    flood_insurance_required: bool = False
    recent_disasters: int = 0
    risk_level: str = "unknown"  # "low", "moderate", "high"


class Demographics(BaseModel):
    """Demographic data for a neighborhood or ZIP code."""

    total_population: Optional[int] = None
    median_household_income: Optional[float] = None
    median_home_value: Optional[float] = None
    population_density: Optional[float] = None


class NeighborhoodAnalysisResult(BaseModel):
    """Aggregated neighborhood analysis results."""

    schools: list[SchoolRating] = []
    crime: Optional[CrimeStats] = None
    walkability: Optional[WalkabilityScores] = None
    flood_risk: Optional[FloodRisk] = None
    demographics: Optional[Demographics] = None
    composite_score: Optional[float] = None  # 0-100 weighted average
    data_completeness: float = 0.0  # 0-1, how much data we actually got
