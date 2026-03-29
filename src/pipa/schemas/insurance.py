"""Pydantic v2 schemas for insurance analysis."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class FloodInsuranceEstimate(BaseModel):
    """Estimated flood insurance costs."""

    flood_zone: str
    annual_premium: float
    required: bool
    coverage_amount: float = 250_000.0


class NaturalDisasterRisk(BaseModel):
    """Natural disaster risk assessment for a property location."""

    earthquake_risk: str = "unknown"  # "low", "moderate", "high"
    hurricane_risk: str = "unknown"
    wildfire_risk: str = "unknown"
    tornado_risk: str = "unknown"
    overall_risk_score: int = 5  # 1-10


class HomeownersInsuranceEstimate(BaseModel):
    """Estimated homeowners insurance costs."""

    annual_premium: float
    monthly_premium: float
    coverage_amount: float
    deductible: float = 1_000.0


class InsuranceAnalysisResult(BaseModel):
    """Aggregated insurance analysis results."""

    homeowners: HomeownersInsuranceEstimate
    flood: Optional[FloodInsuranceEstimate] = None
    disaster_risk: NaturalDisasterRisk
    total_annual_insurance: float
    total_monthly_insurance: float
    risk_adjusted_monthly_cost: float


class InsuranceRequest(BaseModel):
    """Request body for the insurance analysis endpoint."""

    home_value: float
    state: str  # two-letter abbreviation, e.g. "VA"
    flood_zone: Optional[str] = None  # e.g. "X", "AE", "VE"
    flood_declarations: int = 0
    homeowners_rate: float = 0.0035  # annual premium as fraction of home value
