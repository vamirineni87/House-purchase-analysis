"""Core financial analysis — pure functions, no I/O.

Ported from archive/cli-v1 with AppConfig dependency removed.
All config values are passed as explicit parameters.
"""

from __future__ import annotations

from pipa.schemas.financial import (
    AmortizationEntry,
    ClosingCosts,
    FinancialAnalysisResult,
    LoanScenario,
    MonthlyPaymentBreakdown,
)

# Default rate assumptions keyed by loan term (years).
DEFAULT_RATES: dict[int, float] = {30: 0.065, 15: 0.059}

# Default scenario grid
DEFAULT_DOWN_PAYMENT_PCTS: list[float] = [0.10, 0.20]
DEFAULT_TERM_YEARS: list[int] = [15, 30]

# Cost-of-ownership horizons (years)
OWNERSHIP_HORIZONS: list[int] = [1, 3, 5, 7, 10, 15, 30]


def calculate_monthly_payment(
    principal: float,
    annual_rate: float,
    term_years: int,
) -> float:
    """Return the fixed monthly payment using standard amortization.

    Formula: M = P * [r(1+r)^n] / [(1+r)^n - 1]
    """
    if principal <= 0:
        return 0.0
    if annual_rate <= 0:
        return round(principal / (term_years * 12), 2)

    r = annual_rate / 12.0
    n = term_years * 12
    factor = (1 + r) ** n
    payment = principal * (r * factor) / (factor - 1)
    return round(payment, 2)


def build_loan_scenarios(
    list_price: float,
    down_payment_pcts: list[float] | None = None,
    term_years: list[int] | None = None,
    rate_override: float | None = None,
) -> list[LoanScenario]:
    """Generate loan scenarios for every combination of down payment % and term."""
    if down_payment_pcts is None:
        down_payment_pcts = DEFAULT_DOWN_PAYMENT_PCTS
    if term_years is None:
        term_years = DEFAULT_TERM_YEARS

    scenarios: list[LoanScenario] = []
    for term in term_years:
        for pct in down_payment_pcts:
            down = round(list_price * pct, 2)
            loan = round(list_price - down, 2)
            rate = rate_override if rate_override is not None else DEFAULT_RATES.get(term, 0.065)
            pct_label = int(pct * 100)
            name = f"{term}yr-{pct_label}pct-down"
            scenarios.append(
                LoanScenario(
                    name=name,
                    loan_amount=loan,
                    interest_rate=rate,
                    term_years=term,
                    down_payment=down,
                    down_payment_pct=pct,
                )
            )
    return scenarios


def calculate_payment_breakdown(
    scenario: LoanScenario,
    list_price: float,
    hoa_monthly: float = 0.0,
    property_tax_rate: float = 0.012,
    insurance_rate: float = 0.0035,
    pmi_rate: float = 0.005,
    pmi_threshold: float = 0.80,
) -> MonthlyPaymentBreakdown:
    """Return a full PITI + PMI + HOA monthly breakdown."""
    monthly_payment = calculate_monthly_payment(
        scenario.loan_amount, scenario.interest_rate, scenario.term_years
    )

    monthly_rate = scenario.interest_rate / 12.0
    first_month_interest = round(scenario.loan_amount * monthly_rate, 2)
    first_month_principal = round(monthly_payment - first_month_interest, 2)

    property_tax = round((list_price * property_tax_rate) / 12.0, 2)
    homeowners_insurance = round((list_price * insurance_rate) / 12.0, 2)

    ltv = scenario.loan_amount / list_price if list_price > 0 else 0.0
    pmi = round((scenario.loan_amount * pmi_rate) / 12.0, 2) if ltv > pmi_threshold else 0.0

    total = round(
        monthly_payment + property_tax + homeowners_insurance + pmi + hoa_monthly, 2
    )

    return MonthlyPaymentBreakdown(
        principal=first_month_principal,
        interest=first_month_interest,
        property_tax=property_tax,
        homeowners_insurance=homeowners_insurance,
        pmi=pmi,
        hoa=hoa_monthly,
        total=total,
    )


def generate_amortization_schedule(
    scenario: LoanScenario,
    list_price: float,
) -> list[AmortizationEntry]:
    """Build a month-by-month amortization table."""
    monthly_payment = calculate_monthly_payment(
        scenario.loan_amount, scenario.interest_rate, scenario.term_years
    )
    monthly_rate = scenario.interest_rate / 12.0
    n = scenario.term_years * 12
    balance = scenario.loan_amount
    cumulative_interest = 0.0
    cumulative_principal = 0.0
    schedule: list[AmortizationEntry] = []

    for month in range(1, n + 1):
        interest = round(balance * monthly_rate, 2)
        principal = round(monthly_payment - interest, 2)

        if month == n:
            principal = round(balance, 2)
            payment = round(principal + interest, 2)
        else:
            payment = monthly_payment

        balance = round(balance - principal, 2)
        if balance < 0:
            balance = 0.0

        cumulative_interest = round(cumulative_interest + interest, 2)
        cumulative_principal = round(cumulative_principal + principal, 2)
        equity_pct = round(1.0 - (balance / list_price) if list_price > 0 else 0.0, 4)

        schedule.append(
            AmortizationEntry(
                month=month,
                payment=payment,
                principal=principal,
                interest=interest,
                remaining_balance=balance,
                cumulative_interest=cumulative_interest,
                cumulative_principal=cumulative_principal,
                equity_pct=equity_pct,
            )
        )
    return schedule


def estimate_closing_costs(
    list_price: float,
    loan_amount: float,
    property_tax_rate: float = 0.012,
    insurance_rate: float = 0.0035,
) -> ClosingCosts:
    """Return an itemised estimate of closing costs."""
    loan_origination = round(loan_amount * 0.005, 2)
    appraisal_fee = 500.0
    title_insurance = round(list_price * 0.005, 2)
    escrow_fees = 1500.0
    recording_fees = 300.0
    prepaid_taxes = round((list_price * property_tax_rate) / 12.0 * 3, 2)
    prepaid_insurance = round((list_price * insurance_rate) / 12.0 * 14, 2)
    inspection_fees = 500.0
    other = 500.0

    total = round(
        loan_origination + appraisal_fee + title_insurance + escrow_fees
        + recording_fees + prepaid_taxes + prepaid_insurance + inspection_fees + other, 2
    )

    return ClosingCosts(
        loan_origination=loan_origination,
        appraisal_fee=appraisal_fee,
        title_insurance=title_insurance,
        escrow_fees=escrow_fees,
        recording_fees=recording_fees,
        prepaid_taxes=prepaid_taxes,
        prepaid_insurance=prepaid_insurance,
        inspection_fees=inspection_fees,
        other=other,
        total=total,
    )


def calculate_total_cost_of_ownership(
    scenario: LoanScenario,
    closing_costs: ClosingCosts,
    maintenance_rate: float = 0.01,
    marginal_tax_rate: float = 0.24,
    years: list[int] | None = None,
) -> dict[int, float]:
    """Cumulative cost of ownership at each year horizon."""
    if years is None:
        years = OWNERSHIP_HORIZONS

    monthly_payment = calculate_monthly_payment(
        scenario.loan_amount, scenario.interest_rate, scenario.term_years
    )
    monthly_rate = scenario.interest_rate / 12.0
    total_months = scenario.term_years * 12
    price = scenario.loan_amount + scenario.down_payment

    result: dict[int, float] = {}
    for yr in years:
        months = min(yr * 12, total_months)
        mortgage_total = round(monthly_payment * months, 2)
        cc = closing_costs.total
        maintenance = round(maintenance_rate * price * yr, 2)

        balance = scenario.loan_amount
        cumulative_interest = 0.0
        for _ in range(1, months + 1):
            interest = balance * monthly_rate
            principal = monthly_payment - interest
            balance -= principal
            cumulative_interest += interest

        tax_benefit = round(cumulative_interest * marginal_tax_rate, 2)
        total = round(mortgage_total + cc + maintenance - tax_benefit, 2)
        result[yr] = total

    return result


def run_financial_analysis(
    list_price: float,
    hoa_monthly: float = 0.0,
    down_payment_pcts: list[float] | None = None,
    term_years: list[int] | None = None,
    rate_override: float | None = None,
    property_tax_rate: float = 0.012,
    insurance_rate: float = 0.0035,
    pmi_rate: float = 0.005,
    pmi_threshold: float = 0.80,
    maintenance_rate: float = 0.01,
    marginal_tax_rate: float = 0.24,
) -> FinancialAnalysisResult:
    """Run end-to-end financial analysis. Single entry point."""
    scenarios = build_loan_scenarios(list_price, down_payment_pcts, term_years, rate_override)

    payment_breakdowns: dict[str, MonthlyPaymentBreakdown] = {}
    amortization_schedules: dict[str, list[AmortizationEntry]] = {}
    total_cost: dict[str, dict[int, float]] = {}
    cash_needed: dict[str, float] = {}
    closing: ClosingCosts | None = None

    for scenario in scenarios:
        breakdown = calculate_payment_breakdown(
            scenario, list_price, hoa_monthly, property_tax_rate,
            insurance_rate, pmi_rate, pmi_threshold,
        )
        payment_breakdowns[scenario.name] = breakdown

        schedule = generate_amortization_schedule(scenario, list_price)
        amortization_schedules[scenario.name] = schedule

        if closing is None:
            closing = estimate_closing_costs(
                list_price, scenario.loan_amount, property_tax_rate, insurance_rate,
            )

        tco = calculate_total_cost_of_ownership(
            scenario, closing, maintenance_rate, marginal_tax_rate,
        )
        total_cost[scenario.name] = tco
        cash_needed[scenario.name] = round(scenario.down_payment + closing.total, 2)

    assert closing is not None

    return FinancialAnalysisResult(
        scenarios=scenarios,
        payment_breakdowns=payment_breakdowns,
        amortization_schedules=amortization_schedules,
        closing_costs=closing,
        total_cost_of_ownership=total_cost,
        cash_needed_at_closing=cash_needed,
    )
