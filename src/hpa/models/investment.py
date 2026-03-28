"""Investment analysis Pydantic v2 models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class YearlyProjection(BaseModel):
    """Projected financial position for a single year of ownership."""

    year: int
    home_value: float
    equity: float
    cumulative_cost: float
    cumulative_tax_benefit: float
    net_position: float  # equity + tax_benefit - cumulative_cost


class RentVsBuyComparison(BaseModel):
    """Comparison of renting versus buying over time."""

    monthly_rent_equivalent: float
    annual_rent_increase_pct: float
    buy_break_even_year: Optional[int] = None  # year when buying becomes cheaper
    rent_total_cost: dict[int, float] = {}  # year -> cumulative rent
    buy_total_cost: dict[int, float] = {}  # year -> cumulative net buy cost
    recommendation: str  # "buy", "rent", "marginal"


class InvestmentAnalysisResult(BaseModel):
    """Aggregated investment analysis results."""

    appreciation_rate: float
    yearly_projections: list[YearlyProjection]
    total_equity_at_year: dict[int, float]  # 5, 10, 15, 30 year equity
    irr_on_down_payment: Optional[float] = None
    rent_vs_buy: Optional[RentVsBuyComparison] = None
    net_worth_impact_5yr: float = 0.0
    net_worth_impact_10yr: float = 0.0
