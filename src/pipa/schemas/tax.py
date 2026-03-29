"""Pydantic v2 schemas for tax analysis."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CapitalGainsAnalysis(BaseModel):
    """Analysis of selling the current (first) home."""

    purchase_price: float
    estimated_sale_price: float
    selling_costs: float
    cost_basis: float  # purchase_price + capital_improvements
    gross_gain: float
    exclusion_amount: float  # $250k single / $500k married
    taxable_gain: float
    estimated_federal_tax: float
    meets_primary_residence_test: bool
    years_owned: float
    years_as_primary: float
    net_proceeds: float  # sale_price - selling_costs - remaining_mortgage - tax


class RentalIncomeAnalysis(BaseModel):
    """Analysis of renting out the first home."""

    monthly_rent: float
    monthly_mortgage: float
    monthly_taxes: float
    monthly_insurance: float
    monthly_maintenance: float
    vacancy_loss_monthly: float
    monthly_cash_flow: float
    annual_cash_flow: float
    annual_depreciation: float  # cost_basis / 27.5
    annual_tax_benefit_from_depreciation: float
    net_annual_return: float
    cap_rate: float


class FirstHomeStrategy(BaseModel):
    """Recommendation on whether to sell or rent the first home."""

    sell_analysis: Optional[CapitalGainsAnalysis] = None
    rent_analysis: Optional[RentalIncomeAnalysis] = None
    recommendation: str  # "sell", "rent", "either"
    recommendation_reason: str
    sell_net_proceeds: float = 0.0
    rent_annual_net: float = 0.0


class MortgageInterestDeduction(BaseModel):
    """Tax deduction from mortgage interest payments."""

    annual_interest_paid: float
    deductible_amount: float  # capped at interest on $750k loan
    tax_savings: float
    marginal_tax_rate: float


class PropertyTaxDeduction(BaseModel):
    """Tax deduction from property tax payments."""

    annual_property_tax: float
    deductible_amount: float  # capped at $10k SALT
    tax_savings: float
    salt_cap_hit: bool


class TaxAnalysisResult(BaseModel):
    """Aggregated tax analysis results."""

    first_home_strategy: Optional[FirstHomeStrategy] = None
    mortgage_interest_deduction: MortgageInterestDeduction
    property_tax_deduction: PropertyTaxDeduction
    total_annual_tax_benefit: float
    effective_monthly_cost_reduction: float


class TaxAnalysisRequest(BaseModel):
    """Request body for the tax analysis endpoint."""

    # Current (first) home details — optional when buyer doesn't own
    current_home_purchase_price: Optional[float] = None
    current_home_estimated_value: Optional[float] = None
    current_home_remaining_mortgage: Optional[float] = None
    years_as_primary: Optional[float] = None
    estimated_monthly_rent: Optional[float] = None

    # Buyer profile
    filing_status: str = "married"  # "married" | "single"
    marginal_tax_rate: float = 0.24

    # New home purchase
    list_price: float
    loan_amount: float
