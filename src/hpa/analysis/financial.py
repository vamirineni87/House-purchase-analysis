"""Core financial analysis module for home purchase evaluation."""

from __future__ import annotations

from hpa.analysis.base import BaseAnalyzer
from hpa.config import AppConfig
from hpa.models.financial import (
    AmortizationEntry,
    ClosingCosts,
    FinancialAnalysisResult,
    LoanScenario,
    MonthlyPaymentBreakdown,
)
from hpa.models.property import PropertyDetails

# ---------------------------------------------------------------------------
# Default rate assumptions keyed by loan term (years).
# ---------------------------------------------------------------------------
_DEFAULT_RATES: dict[int, float] = {
    30: 0.065,
    15: 0.059,
}

# Default scenario grid
_DEFAULT_DOWN_PAYMENT_PCTS: list[float] = [0.10, 0.20]
_DEFAULT_TERM_YEARS: list[int] = [15, 30]

# Cost-of-ownership horizons (years)
_OWNERSHIP_HORIZONS: list[int] = [1, 3, 5, 7, 10, 15, 30]


class FinancialAnalyzer(BaseAnalyzer):
    """Performs comprehensive mortgage and cost-of-ownership analysis."""

    # ------------------------------------------------------------------
    # BaseAnalyzer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Financial Analysis"

    def analyze(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> FinancialAnalysisResult:
        """Run end-to-end financial analysis for *property_details*."""

        scenarios = self.build_loan_scenarios(property_details, config)

        payment_breakdowns: dict[str, MonthlyPaymentBreakdown] = {}
        amortization_schedules: dict[str, list[AmortizationEntry]] = {}
        total_cost_of_ownership: dict[str, dict[int, float]] = {}
        cash_needed_at_closing: dict[str, float] = {}

        # Use the first scenario's closing costs as the representative estimate.
        closing_costs: ClosingCosts | None = None

        for scenario in scenarios:
            breakdown = self.calculate_payment_breakdown(
                scenario, property_details, config
            )
            payment_breakdowns[scenario.name] = breakdown

            schedule = self.generate_amortization_schedule(
                scenario, property_details
            )
            amortization_schedules[scenario.name] = schedule

            if closing_costs is None:
                closing_costs = self.estimate_closing_costs(
                    property_details, scenario, config
                )

            tco = self.calculate_total_cost_of_ownership(
                scenario, breakdown, closing_costs, config
            )
            total_cost_of_ownership[scenario.name] = tco

            cash_needed_at_closing[scenario.name] = round(
                scenario.down_payment + closing_costs.total, 2
            )

        # closing_costs is guaranteed to be set because scenarios is non-empty.
        assert closing_costs is not None

        return FinancialAnalysisResult(
            scenarios=scenarios,
            payment_breakdowns=payment_breakdowns,
            amortization_schedules=amortization_schedules,
            closing_costs=closing_costs,
            total_cost_of_ownership=total_cost_of_ownership,
            cash_needed_at_closing=cash_needed_at_closing,
        )

    # ------------------------------------------------------------------
    # Core calculations
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_monthly_payment(
        principal: float,
        annual_rate: float,
        term_years: int,
    ) -> float:
        """Return the fixed monthly payment using standard amortization.

        Formula: M = P * [r(1+r)^n] / [(1+r)^n - 1]
        where r = monthly rate, n = total number of months.
        """
        if principal <= 0:
            return 0.0
        if annual_rate <= 0:
            # Zero-interest edge case: simple division.
            return round(principal / (term_years * 12), 2)

        r = annual_rate / 12.0
        n = term_years * 12
        factor = (1 + r) ** n
        payment = principal * (r * factor) / (factor - 1)
        return round(payment, 2)

    # ------------------------------------------------------------------
    # Scenario construction
    # ------------------------------------------------------------------

    def build_loan_scenarios(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
        down_payment_pcts: list[float] | None = None,
        term_years: list[int] | None = None,
        rate_override: float | None = None,
    ) -> list[LoanScenario]:
        """Generate a list of :class:`LoanScenario` for every combination of
        *down_payment_pcts* and *term_years*.
        """
        if down_payment_pcts is None:
            down_payment_pcts = _DEFAULT_DOWN_PAYMENT_PCTS
        if term_years is None:
            term_years = _DEFAULT_TERM_YEARS

        price = property_details.list_price
        scenarios: list[LoanScenario] = []

        for term in term_years:
            for pct in down_payment_pcts:
                down = round(price * pct, 2)
                loan = round(price - down, 2)
                rate = rate_override if rate_override is not None else _DEFAULT_RATES.get(term, 0.065)
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

    # ------------------------------------------------------------------
    # Payment breakdown
    # ------------------------------------------------------------------

    def calculate_payment_breakdown(
        self,
        scenario: LoanScenario,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> MonthlyPaymentBreakdown:
        """Return a full PITI + PMI + HOA monthly breakdown."""

        monthly_payment = self.calculate_monthly_payment(
            scenario.loan_amount, scenario.interest_rate, scenario.term_years
        )

        # First-month interest/principal split
        monthly_rate = scenario.interest_rate / 12.0
        first_month_interest = round(scenario.loan_amount * monthly_rate, 2)
        first_month_principal = round(monthly_payment - first_month_interest, 2)

        price = property_details.list_price
        property_tax = round(
            (price * config.defaults.property_tax_rate) / 12.0, 2
        )
        homeowners_insurance = round(
            (price * config.defaults.homeowners_insurance_annual_pct) / 12.0, 2
        )

        # PMI required when LTV > 80 %
        ltv = scenario.loan_amount / price if price > 0 else 0.0
        if ltv > config.defaults.pmi_ltv_threshold:
            pmi = round(
                (scenario.loan_amount * config.defaults.pmi_annual_pct) / 12.0, 2
            )
        else:
            pmi = 0.0

        hoa = property_details.hoa_monthly

        total = round(
            monthly_payment + property_tax + homeowners_insurance + pmi + hoa, 2
        )

        return MonthlyPaymentBreakdown(
            principal=first_month_principal,
            interest=first_month_interest,
            property_tax=property_tax,
            homeowners_insurance=homeowners_insurance,
            pmi=pmi,
            hoa=hoa,
            total=total,
        )

    # ------------------------------------------------------------------
    # Amortization schedule
    # ------------------------------------------------------------------

    def generate_amortization_schedule(
        self,
        scenario: LoanScenario,
        property_details: PropertyDetails,
    ) -> list[AmortizationEntry]:
        """Build a month-by-month amortization table."""

        monthly_payment = self.calculate_monthly_payment(
            scenario.loan_amount, scenario.interest_rate, scenario.term_years
        )
        monthly_rate = scenario.interest_rate / 12.0
        n = scenario.term_years * 12
        balance = scenario.loan_amount
        cumulative_interest = 0.0
        cumulative_principal = 0.0
        price = property_details.list_price
        schedule: list[AmortizationEntry] = []

        for month in range(1, n + 1):
            interest = round(balance * monthly_rate, 2)
            principal = round(monthly_payment - interest, 2)

            # Ensure the last payment zeroes out the balance exactly.
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

            equity_pct = round(
                1.0 - (balance / price) if price > 0 else 0.0, 4
            )

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

    # ------------------------------------------------------------------
    # Closing costs
    # ------------------------------------------------------------------

    def estimate_closing_costs(
        self,
        property_details: PropertyDetails,
        scenario: LoanScenario,
        config: AppConfig,
    ) -> ClosingCosts:
        """Return an itemised estimate of closing costs."""

        price = property_details.list_price
        loan = scenario.loan_amount

        loan_origination = round(loan * 0.005, 2)
        appraisal_fee = 500.0
        title_insurance = round(price * 0.005, 2)
        escrow_fees = 1500.0
        recording_fees = 300.0

        monthly_tax = (price * config.defaults.property_tax_rate) / 12.0
        prepaid_taxes = round(monthly_tax * 3, 2)

        monthly_insurance = (
            price * config.defaults.homeowners_insurance_annual_pct
        ) / 12.0
        prepaid_insurance = round(monthly_insurance * 14, 2)

        inspection_fees = 500.0
        other = 500.0

        total = round(
            loan_origination
            + appraisal_fee
            + title_insurance
            + escrow_fees
            + recording_fees
            + prepaid_taxes
            + prepaid_insurance
            + inspection_fees
            + other,
            2,
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

    # ------------------------------------------------------------------
    # Total cost of ownership
    # ------------------------------------------------------------------

    def calculate_total_cost_of_ownership(
        self,
        scenario: LoanScenario,
        payment_breakdown: MonthlyPaymentBreakdown,
        closing_costs: ClosingCosts,
        config: AppConfig,
        years: list[int] | None = None,
    ) -> dict[int, float]:
        """Cumulative cost of ownership at each year horizon.

        Includes mortgage payments, closing costs (year 1), annual
        maintenance, and a rough estimate of mortgage-interest tax
        deduction savings.
        """
        if years is None:
            years = _OWNERSHIP_HORIZONS

        monthly_payment = self.calculate_monthly_payment(
            scenario.loan_amount, scenario.interest_rate, scenario.term_years
        )
        monthly_rate = scenario.interest_rate / 12.0
        total_months = scenario.term_years * 12
        price = scenario.loan_amount + scenario.down_payment  # purchase price

        result: dict[int, float] = {}

        for yr in years:
            months = min(yr * 12, total_months)

            # Total mortgage payments over the period
            mortgage_total = round(monthly_payment * months, 2)

            # Closing costs apply once (in year 1)
            cc = closing_costs.total

            # Annual maintenance
            maintenance = round(
                config.defaults.maintenance_annual_pct * price * yr, 2
            )

            # Estimate cumulative interest paid for tax-benefit calculation
            balance = scenario.loan_amount
            cumulative_interest = 0.0
            for _m in range(1, months + 1):
                interest = balance * monthly_rate
                principal = monthly_payment - interest
                balance -= principal
                cumulative_interest += interest

            # Estimated annual tax benefit from mortgage interest deduction
            tax_benefit = round(
                cumulative_interest * config.defaults.marginal_tax_rate, 2
            )

            total = round(mortgage_total + cc + maintenance - tax_benefit, 2)
            result[yr] = total

        return result
