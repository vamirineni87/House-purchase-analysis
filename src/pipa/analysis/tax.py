"""Tax analysis — pure functions, no I/O.

Ported from archive/cli-v1 with BaseAnalyzer/AppConfig dependency removed.
All config values are passed as explicit parameters.

Focuses on 2nd home purchase scenarios: sell-vs-rent strategy for the
current home, mortgage interest deductions, property tax deductions
(with SALT cap), and overall annual tax benefits.
"""

from __future__ import annotations

from typing import Optional

from pipa.schemas.tax import (
    CapitalGainsAnalysis,
    FirstHomeStrategy,
    MortgageInterestDeduction,
    PropertyTaxDeduction,
    RentalIncomeAnalysis,
    TaxAnalysisResult,
)

# IRS limits (2024+)
SALT_CAP = 10_000.0
MORTGAGE_INTEREST_LOAN_CAP = 750_000.0
CAPITAL_GAINS_EXCLUSION_MARRIED = 500_000.0
CAPITAL_GAINS_EXCLUSION_SINGLE = 250_000.0
LONG_TERM_CAPITAL_GAINS_RATE = 0.15
SELLING_COST_PCT = 0.08  # 6 % agent + 2 % closing
RESIDENTIAL_STRUCTURE_PCT = 0.85  # land ~15 % of property value
RESIDENTIAL_DEPRECIATION_YEARS = 27.5
PRIMARY_RESIDENCE_YEARS_REQUIRED = 2.0
RENT_COMPARISON_YEARS = 10


# ------------------------------------------------------------------
# Capital gains (selling the current home)
# ------------------------------------------------------------------


def analyze_capital_gains(
    purchase_price: float,
    estimated_current_value: float,
    remaining_mortgage_balance: float,
    years_as_primary_residence: float,
    filing_status: str = "married",
    capital_improvements: float = 0.0,
    selling_cost_pct: float = SELLING_COST_PCT,
) -> CapitalGainsAnalysis:
    """Estimate capital-gains tax and net proceeds from selling the current home."""

    sale_price = estimated_current_value
    selling_costs = round(sale_price * selling_cost_pct, 2)
    cost_basis = round(purchase_price + capital_improvements, 2)
    gross_gain = round(sale_price - cost_basis, 2)

    meets_test = years_as_primary_residence >= PRIMARY_RESIDENCE_YEARS_REQUIRED

    if meets_test:
        if filing_status == "married":
            exclusion = CAPITAL_GAINS_EXCLUSION_MARRIED
        else:
            exclusion = CAPITAL_GAINS_EXCLUSION_SINGLE
    else:
        exclusion = 0.0

    taxable_gain = round(max(0.0, gross_gain - exclusion), 2)
    estimated_tax = round(taxable_gain * LONG_TERM_CAPITAL_GAINS_RATE, 2)
    net_proceeds = round(
        sale_price - selling_costs - remaining_mortgage_balance - estimated_tax,
        2,
    )

    return CapitalGainsAnalysis(
        purchase_price=purchase_price,
        estimated_sale_price=sale_price,
        selling_costs=selling_costs,
        cost_basis=cost_basis,
        gross_gain=gross_gain,
        exclusion_amount=exclusion,
        taxable_gain=taxable_gain,
        estimated_federal_tax=estimated_tax,
        meets_primary_residence_test=meets_test,
        years_owned=years_as_primary_residence,
        years_as_primary=years_as_primary_residence,
        net_proceeds=net_proceeds,
    )


# ------------------------------------------------------------------
# Rental income (renting out the current home)
# ------------------------------------------------------------------


def analyze_rental_income(
    purchase_price: float,
    estimated_current_value: float,
    monthly_rent: float,
    monthly_mortgage_payment: float,
    annual_property_tax: float,
    annual_insurance: float,
    marginal_tax_rate: float = 0.24,
    maintenance_annual_pct: float = 0.01,
    vacancy_rate: float = 0.05,
) -> RentalIncomeAnalysis:
    """Project cash flow and tax benefits from renting out the current home."""

    monthly_taxes = round(annual_property_tax / 12.0, 2)
    monthly_insurance = round(annual_insurance / 12.0, 2)
    monthly_maintenance = round(
        (estimated_current_value * maintenance_annual_pct) / 12.0, 2
    )
    vacancy_loss = round(monthly_rent * vacancy_rate, 2)

    monthly_cash_flow = round(
        monthly_rent
        - monthly_mortgage_payment
        - monthly_taxes
        - monthly_insurance
        - monthly_maintenance
        - vacancy_loss,
        2,
    )
    annual_cash_flow = round(monthly_cash_flow * 12.0, 2)

    # Depreciation: structure value (85 % of purchase price) over 27.5 years.
    annual_depreciation = round(
        (purchase_price * RESIDENTIAL_STRUCTURE_PCT)
        / RESIDENTIAL_DEPRECIATION_YEARS,
        2,
    )
    annual_tax_benefit = round(annual_depreciation * marginal_tax_rate, 2)

    net_annual_return = round(annual_cash_flow + annual_tax_benefit, 2)

    if estimated_current_value > 0:
        cap_rate = round(net_annual_return / estimated_current_value, 4)
    else:
        cap_rate = 0.0

    return RentalIncomeAnalysis(
        monthly_rent=monthly_rent,
        monthly_mortgage=monthly_mortgage_payment,
        monthly_taxes=monthly_taxes,
        monthly_insurance=monthly_insurance,
        monthly_maintenance=monthly_maintenance,
        vacancy_loss_monthly=vacancy_loss,
        monthly_cash_flow=monthly_cash_flow,
        annual_cash_flow=annual_cash_flow,
        annual_depreciation=annual_depreciation,
        annual_tax_benefit_from_depreciation=annual_tax_benefit,
        net_annual_return=net_annual_return,
        cap_rate=cap_rate,
    )


# ------------------------------------------------------------------
# Strategy recommendation
# ------------------------------------------------------------------


def recommend_first_home_strategy(
    sell: CapitalGainsAnalysis,
    rent: RentalIncomeAnalysis,
    comparison_years: int = RENT_COMPARISON_YEARS,
) -> FirstHomeStrategy:
    """Compare selling vs. renting the current home and return a recommendation."""

    sell_net = sell.net_proceeds
    rent_10yr_net = round(
        rent.annual_cash_flow * comparison_years
        + rent.annual_tax_benefit_from_depreciation * comparison_years,
        2,
    )

    if sell_net > rent_10yr_net:
        recommendation = "sell"
        reason = (
            f"Selling yields ${sell_net:,.0f} in net proceeds, which "
            f"exceeds the estimated {comparison_years}-year rental net of "
            f"${rent_10yr_net:,.0f}. Selling provides immediate "
            f"liquidity for the new purchase."
        )
    elif rent_10yr_net > sell_net * 1.2:
        # Renting must be meaningfully better (>20 %) to recommend
        # it over the simplicity of selling.
        recommendation = "rent"
        reason = (
            f"Renting out the home is projected to return "
            f"${rent_10yr_net:,.0f} over {comparison_years} years, "
            f"significantly more than the ${sell_net:,.0f} net from selling. "
            f"Monthly cash flow of ${rent.monthly_cash_flow:,.0f} provides "
            f"ongoing income."
        )
    else:
        recommendation = "either"
        reason = (
            f"Both options are viable. Selling nets ${sell_net:,.0f} "
            f"immediately, while renting projects ${rent_10yr_net:,.0f} "
            f"over {comparison_years} years. Consider your risk tolerance, "
            f"desire for landlord responsibilities, and liquidity needs."
        )

    return FirstHomeStrategy(
        sell_analysis=sell,
        rent_analysis=rent,
        recommendation=recommendation,
        recommendation_reason=reason,
        sell_net_proceeds=sell_net,
        rent_annual_net=rent.net_annual_return,
    )


# ------------------------------------------------------------------
# Mortgage interest deduction (new home)
# ------------------------------------------------------------------


def calculate_mortgage_interest_deduction(
    loan_amount: float,
    interest_rate: float,
    term_years: int,
    marginal_tax_rate: float = 0.24,
    mortgage_interest_loan_cap: float = MORTGAGE_INTEREST_LOAN_CAP,
) -> MortgageInterestDeduction:
    """Calculate the first-year mortgage interest deduction.

    For loans exceeding $750k, only the portion of interest attributable
    to the first $750k of principal is deductible.
    """
    rate = interest_rate
    loan = loan_amount
    term_months = term_years * 12

    # Calculate total interest paid in Year 1 via amortization.
    monthly_rate = rate / 12.0
    if rate <= 0 or loan <= 0:
        annual_interest = 0.0
    else:
        factor = (1 + monthly_rate) ** term_months
        monthly_payment = loan * (monthly_rate * factor) / (factor - 1)

        balance = loan
        annual_interest = 0.0
        for _ in range(12):
            interest = balance * monthly_rate
            principal = monthly_payment - interest
            annual_interest += interest
            balance -= principal

    annual_interest = round(annual_interest, 2)

    # Pro-rate if loan exceeds the IRS cap.
    if loan > mortgage_interest_loan_cap:
        deductible_ratio = mortgage_interest_loan_cap / loan
        deductible_amount = round(annual_interest * deductible_ratio, 2)
    else:
        deductible_amount = annual_interest

    tax_savings = round(deductible_amount * marginal_tax_rate, 2)

    return MortgageInterestDeduction(
        annual_interest_paid=annual_interest,
        deductible_amount=deductible_amount,
        tax_savings=tax_savings,
        marginal_tax_rate=marginal_tax_rate,
    )


# ------------------------------------------------------------------
# Property tax deduction (SALT cap)
# ------------------------------------------------------------------


def calculate_property_tax_deduction(
    list_price: float,
    property_tax_rate: float = 0.012,
    marginal_tax_rate: float = 0.24,
    salt_cap: float = SALT_CAP,
) -> PropertyTaxDeduction:
    """Calculate property tax deduction subject to the $10k SALT cap."""

    annual_property_tax = round(list_price * property_tax_rate, 2)
    deductible_amount = min(annual_property_tax, salt_cap)
    salt_cap_hit = annual_property_tax > salt_cap
    tax_savings = round(deductible_amount * marginal_tax_rate, 2)

    return PropertyTaxDeduction(
        annual_property_tax=annual_property_tax,
        deductible_amount=deductible_amount,
        tax_savings=tax_savings,
        salt_cap_hit=salt_cap_hit,
    )


# ------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------


def run_tax_analysis(
    list_price: float,
    loan_amount: float,
    interest_rate: float = 0.065,
    term_years: int = 30,
    marginal_tax_rate: float = 0.24,
    filing_status: str = "married",
    property_tax_rate: float = 0.012,
    # Current (first) home — pass all or none
    current_home_purchase_price: Optional[float] = None,
    current_home_estimated_value: Optional[float] = None,
    current_home_remaining_mortgage: Optional[float] = None,
    years_as_primary: Optional[float] = None,
    estimated_monthly_rent: Optional[float] = None,
    current_home_monthly_payment: float = 0.0,
    current_home_annual_property_tax: float = 0.0,
    current_home_annual_insurance: float = 0.0,
    current_home_capital_improvements: float = 0.0,
    maintenance_annual_pct: float = 0.01,
    vacancy_rate: float = 0.05,
) -> TaxAnalysisResult:
    """Run full tax analysis. Single entry point.

    When current-home fields are provided the sell-vs-rent strategy is
    included; otherwise that section is omitted.
    """
    first_home_strategy: Optional[FirstHomeStrategy] = None

    has_current_home = all(
        v is not None
        for v in [
            current_home_purchase_price,
            current_home_estimated_value,
            current_home_remaining_mortgage,
            years_as_primary,
            estimated_monthly_rent,
        ]
    )

    if has_current_home:
        assert current_home_purchase_price is not None
        assert current_home_estimated_value is not None
        assert current_home_remaining_mortgage is not None
        assert years_as_primary is not None
        assert estimated_monthly_rent is not None

        sell_analysis = analyze_capital_gains(
            purchase_price=current_home_purchase_price,
            estimated_current_value=current_home_estimated_value,
            remaining_mortgage_balance=current_home_remaining_mortgage,
            years_as_primary_residence=years_as_primary,
            filing_status=filing_status,
            capital_improvements=current_home_capital_improvements,
        )
        rent_analysis = analyze_rental_income(
            purchase_price=current_home_purchase_price,
            estimated_current_value=current_home_estimated_value,
            monthly_rent=estimated_monthly_rent,
            monthly_mortgage_payment=current_home_monthly_payment,
            annual_property_tax=current_home_annual_property_tax,
            annual_insurance=current_home_annual_insurance,
            marginal_tax_rate=marginal_tax_rate,
            maintenance_annual_pct=maintenance_annual_pct,
            vacancy_rate=vacancy_rate,
        )
        first_home_strategy = recommend_first_home_strategy(
            sell_analysis, rent_analysis
        )

    mortgage_deduction = calculate_mortgage_interest_deduction(
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        term_years=term_years,
        marginal_tax_rate=marginal_tax_rate,
    )

    property_tax_deduction = calculate_property_tax_deduction(
        list_price=list_price,
        property_tax_rate=property_tax_rate,
        marginal_tax_rate=marginal_tax_rate,
    )

    total_annual_benefit = round(
        mortgage_deduction.tax_savings + property_tax_deduction.tax_savings,
        2,
    )

    return TaxAnalysisResult(
        first_home_strategy=first_home_strategy,
        mortgage_interest_deduction=mortgage_deduction,
        property_tax_deduction=property_tax_deduction,
        total_annual_tax_benefit=total_annual_benefit,
        effective_monthly_cost_reduction=round(total_annual_benefit / 12.0, 2),
    )
