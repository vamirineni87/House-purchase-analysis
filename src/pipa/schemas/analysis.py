"""Pydantic v2 schemas for extended analysis endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# --- Offer analysis ---


class OfferAnalysisRequest(BaseModel):
    """Request body for offer strategy analysis."""

    appraisal_value: float
    max_monthly_payment: float
    max_cash_at_closing: float
    interest_rate: float = 0.065
    term_years: int = 30
    down_payment_pct: float = 0.20
    property_tax_rate: float = 0.012
    insurance_rate: float = 0.0035
    hoa_monthly: float = 0.0
    closing_cost_pct: float = 0.03
    # Walk-away
    list_price: float = 0.0
    inspection_cost_threshold: float = 20_000.0
    # Escalation
    escalation_base: Optional[float] = None
    escalation_increment: float = 5_000.0
    escalation_cap: Optional[float] = None
    competing_bids: list[float] = []
    # Appraisal gap
    offer_price: Optional[float] = None
    cash_reserves: float = 0.0


class OfferAnalysisResult(BaseModel):
    """Result of offer strategy analysis."""

    max_bid: dict
    walk_away_price: float
    escalation_outcomes: list[dict] = []
    appraisal_gap: dict = {}


# --- Stress testing ---


class StressTestRequest(BaseModel):
    """Request body for stress test analysis."""

    list_price: float
    loan_amount: float
    interest_rate: float = 0.065
    term_years: int = 30
    annual_insurance: float = 0.0
    rate_deltas: Optional[list[float]] = None
    insurance_inflation_rates: Optional[list[float]] = None
    insurance_projection_years: int = 10
    depreciation_pcts: Optional[list[float]] = None
    downside_years_held: int = 5
    selling_costs_pct: float = 0.08


class StressTestResult(BaseModel):
    """Result of stress test analysis."""

    rate_shock: dict
    insurance_inflation: dict
    downside_sale: dict


# --- Condition analysis ---
#
# ConditionAnalysisResult and ConditionComponent were removed when the
# divergent AnalysisService.run_condition path was deleted. Condition
# data now flows through the pipeline orchestrator's _task_condition,
# whose output is a free-form dict (score, capex_forecast, components,
# noted_improvements, summary) and is read via the analysis-results
# endpoint rather than a typed schema.

# --- Full analysis ---


class FullAnalysisRequest(BaseModel):
    """Request body for running all analyses at once."""

    list_price: float
    hoa_monthly: float = 0.0
    down_payment_pct: float = 0.20
    term_years: int = 30
    rate_override: Optional[float] = None
    property_tax_rate: Optional[float] = None
    insurance_rate: float = 0.0035
    marginal_tax_rate: float = 0.24
    appreciation_rate: float = 0.03
    # Tax-specific
    loan_amount: Optional[float] = None
    filing_status: str = "married"
    # Current home (optional)
    current_home_purchase_price: Optional[float] = None
    current_home_estimated_value: Optional[float] = None
    current_home_remaining_mortgage: Optional[float] = None
    years_as_primary: Optional[float] = None
    estimated_monthly_rent: Optional[float] = None


class FullAnalysisResult(BaseModel):
    """Aggregated result of all analyses.

    Condition is intentionally absent — it's produced by the pipeline
    orchestrator's _task_condition (which reads resolver-merged AI/county
    canonical data) and read via /properties/{id}/analysis-results.
    """

    financial: dict
    tax: dict
    investment: dict
