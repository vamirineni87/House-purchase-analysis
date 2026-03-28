"""Financial Pydantic v2 models for loan analysis."""

from __future__ import annotations

from pydantic import BaseModel


class LoanScenario(BaseModel):
    """A single mortgage loan scenario to evaluate."""

    name: str
    loan_amount: float
    interest_rate: float
    term_years: int
    down_payment: float
    down_payment_pct: float
    points: float = 0.0


class MonthlyPaymentBreakdown(BaseModel):
    """Itemised monthly housing payment."""

    principal: float
    interest: float
    property_tax: float
    homeowners_insurance: float
    pmi: float
    hoa: float
    total: float


class AmortizationEntry(BaseModel):
    """A single row in an amortization schedule."""

    month: int
    payment: float
    principal: float
    interest: float
    remaining_balance: float
    cumulative_interest: float
    cumulative_principal: float
    equity_pct: float


class ClosingCosts(BaseModel):
    """Itemised closing costs for a purchase."""

    loan_origination: float
    appraisal_fee: float
    title_insurance: float
    escrow_fees: float
    recording_fees: float
    prepaid_taxes: float
    prepaid_insurance: float
    inspection_fees: float
    other: float
    total: float


class FinancialAnalysisResult(BaseModel):
    """Aggregate results from a full financial analysis."""

    scenarios: list[LoanScenario]
    payment_breakdowns: dict[str, MonthlyPaymentBreakdown]
    amortization_schedules: dict[str, list[AmortizationEntry]]
    closing_costs: ClosingCosts
    total_cost_of_ownership: dict[str, dict[int, float]]
    cash_needed_at_closing: dict[str, float]
