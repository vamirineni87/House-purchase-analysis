"""Investment analysis: equity buildup, appreciation, rent-vs-buy, IRR."""

from __future__ import annotations

import logging
from typing import Optional

from hpa.analysis.base import BaseAnalyzer
from hpa.analysis.financial import FinancialAnalyzer
from hpa.config import AppConfig
from hpa.models.financial import ClosingCosts, LoanScenario, MonthlyPaymentBreakdown
from hpa.models.investment import (
    InvestmentAnalysisResult,
    RentVsBuyComparison,
    YearlyProjection,
)
from hpa.models.property import PropertyDetails

logger = logging.getLogger(__name__)

# Rough rent-to-value monthly ratio (0.4 % of home value per month).
_DEFAULT_RENT_TO_VALUE_MONTHLY = 0.004

# Projection horizon in years.
_MAX_PROJECTION_YEARS = 30

# Key equity-snapshot years.
_EQUITY_SNAPSHOT_YEARS = (5, 10, 15, 30)

# Default mortgage rate for fallback scenario.
_DEFAULT_RATE_30YR = 0.065
_DEFAULT_DOWN_PCT = 0.20


class InvestmentAnalyzer(BaseAnalyzer):
    """Evaluates long-term investment characteristics of a home purchase."""

    # ------------------------------------------------------------------
    # BaseAnalyzer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Investment Analysis"

    def analyze(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
        scenario: LoanScenario | None = None,
        payment_breakdown: MonthlyPaymentBreakdown | None = None,
        closing_costs: ClosingCosts | None = None,
    ) -> InvestmentAnalysisResult:
        """Run the full investment analysis for *property_details*.

        If *scenario*, *payment_breakdown*, or *closing_costs* are not
        supplied they are computed from sensible defaults using
        :class:`FinancialAnalyzer`.
        """
        financial = FinancialAnalyzer()
        price = property_details.list_price

        # ----- Build defaults when caller doesn't supply them -----
        if scenario is None:
            down = round(price * _DEFAULT_DOWN_PCT, 2)
            scenario = LoanScenario(
                name="30yr-20pct-down",
                loan_amount=round(price - down, 2),
                interest_rate=_DEFAULT_RATE_30YR,
                term_years=30,
                down_payment=down,
                down_payment_pct=_DEFAULT_DOWN_PCT,
            )

        if payment_breakdown is None:
            payment_breakdown = financial.calculate_payment_breakdown(
                scenario, property_details, config
            )

        if closing_costs is None:
            closing_costs = financial.estimate_closing_costs(
                property_details, scenario, config
            )

        appreciation_rate = config.defaults.appreciation_rate

        # 1. Yearly projections
        yearly_projections = self.generate_yearly_projections(
            property_details, config, scenario, payment_breakdown, closing_costs
        )

        # 2. Equity snapshots at key years
        projection_map = {yp.year: yp for yp in yearly_projections}
        total_equity_at_year: dict[int, float] = {}
        for yr in _EQUITY_SNAPSHOT_YEARS:
            if yr in projection_map:
                total_equity_at_year[yr] = projection_map[yr].equity

        # 3. IRR on down payment
        irr_value = self.calculate_irr(
            down_payment=scenario.down_payment,
            closing_costs_total=closing_costs.total,
            monthly_payment=payment_breakdown.total,
            property_price=price,
            appreciation_rate=appreciation_rate,
            loan_amount=scenario.loan_amount,
            interest_rate=scenario.interest_rate,
            term_years=scenario.term_years,
            years=10,
        )

        # 4. Rent-vs-buy
        rent_vs_buy = self.rent_vs_buy_analysis(
            property_details, config, scenario, payment_breakdown, closing_costs
        )

        # 5. Net-worth impact at 5 and 10 years
        net_worth_5 = projection_map[5].net_position if 5 in projection_map else 0.0
        net_worth_10 = projection_map[10].net_position if 10 in projection_map else 0.0

        return InvestmentAnalysisResult(
            appreciation_rate=appreciation_rate,
            yearly_projections=yearly_projections,
            total_equity_at_year=total_equity_at_year,
            irr_on_down_payment=irr_value,
            rent_vs_buy=rent_vs_buy,
            net_worth_impact_5yr=net_worth_5,
            net_worth_impact_10yr=net_worth_10,
        )

    # ------------------------------------------------------------------
    # Yearly projections
    # ------------------------------------------------------------------

    def generate_yearly_projections(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
        scenario: LoanScenario,
        payment_breakdown: MonthlyPaymentBreakdown,
        closing_costs: ClosingCosts,
    ) -> list[YearlyProjection]:
        """Project financial position for each year of a 30-year horizon."""

        price = property_details.list_price
        appreciation = config.defaults.appreciation_rate
        maintenance_pct = config.defaults.maintenance_annual_pct
        marginal_tax = config.defaults.marginal_tax_rate

        monthly_pi = FinancialAnalyzer.calculate_monthly_payment(
            scenario.loan_amount, scenario.interest_rate, scenario.term_years
        )
        monthly_rate = scenario.interest_rate / 12.0
        total_months = scenario.term_years * 12

        # Pre-compute remaining balances & cumulative interest by year.
        balance = scenario.loan_amount
        cumulative_interest = 0.0
        balances_by_year: dict[int, float] = {}
        cum_interest_by_year: dict[int, float] = {}

        for month in range(1, total_months + 1):
            interest = balance * monthly_rate
            principal = monthly_pi - interest
            balance -= principal
            cumulative_interest += interest

            if month % 12 == 0:
                year = month // 12
                balances_by_year[year] = max(round(balance, 2), 0.0)
                cum_interest_by_year[year] = round(cumulative_interest, 2)

        projections: list[YearlyProjection] = []

        for year in range(1, _MAX_PROJECTION_YEARS + 1):
            home_value = round(price * (1 + appreciation) ** year, 2)
            remaining = balances_by_year.get(year, 0.0)
            equity = round(home_value - remaining, 2)

            months_elapsed = min(year * 12, total_months)
            cumulative_cost = round(
                (payment_breakdown.total * months_elapsed)
                + closing_costs.total
                + (maintenance_pct * price * year),
                2,
            )

            cum_interest = cum_interest_by_year.get(year, cumulative_interest)
            cumulative_tax_benefit = round(cum_interest * marginal_tax, 2)

            net_position = round(
                equity + cumulative_tax_benefit - cumulative_cost, 2
            )

            projections.append(
                YearlyProjection(
                    year=year,
                    home_value=home_value,
                    equity=equity,
                    cumulative_cost=cumulative_cost,
                    cumulative_tax_benefit=cumulative_tax_benefit,
                    net_position=net_position,
                )
            )

        return projections

    # ------------------------------------------------------------------
    # Internal rate of return
    # ------------------------------------------------------------------

    def calculate_irr(
        self,
        down_payment: float,
        closing_costs_total: float,
        monthly_payment: float,
        property_price: float,
        appreciation_rate: float,
        loan_amount: float,
        interest_rate: float,
        term_years: int,
        years: int = 10,
    ) -> Optional[float]:
        """Estimate annualised IRR on the buyer's cash invested.

        Returns ``None`` when *numpy_financial* is not available.

        Cash-flow model (monthly):
        - Month 0: outflow of down-payment + closing costs
        - Months 1 .. N: outflow of monthly payment (PITI + HOA)
        - Month N: inflow of appreciated home value minus remaining balance
        """
        try:
            import numpy_financial as npf  # type: ignore[import-untyped]
        except ImportError:
            logger.debug(
                "numpy_financial not installed; skipping IRR calculation"
            )
            return None

        months = years * 12
        total_months = term_years * 12

        # Terminal home value
        home_value_at_exit = property_price * (1 + appreciation_rate) ** years

        # Remaining mortgage balance after *months* payments
        monthly_rate = interest_rate / 12.0
        balance = loan_amount
        for _ in range(min(months, total_months)):
            interest = balance * monthly_rate
            principal = FinancialAnalyzer.calculate_monthly_payment(
                loan_amount, interest_rate, term_years
            ) - interest
            balance -= principal
        remaining_balance = max(balance, 0.0)

        terminal_inflow = home_value_at_exit - remaining_balance

        # Build cash-flow array
        cash_flows: list[float] = [-(down_payment + closing_costs_total)]
        for _ in range(months - 1):
            cash_flows.append(-monthly_payment)
        # Last month: outflow of payment + inflow from sale
        cash_flows.append(-monthly_payment + terminal_inflow)

        monthly_irr = npf.irr(cash_flows)

        if monthly_irr is None or monthly_irr != monthly_irr:
            # irr returned NaN or None
            return None

        annual_irr = round((1 + float(monthly_irr)) ** 12 - 1, 6)
        return annual_irr

    # ------------------------------------------------------------------
    # Rent-vs-buy analysis
    # ------------------------------------------------------------------

    def rent_vs_buy_analysis(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
        scenario: LoanScenario,
        payment_breakdown: MonthlyPaymentBreakdown,
        closing_costs: ClosingCosts,
    ) -> RentVsBuyComparison:
        """Compare the cumulative cost of renting versus buying."""

        price = property_details.list_price
        appreciation = config.defaults.appreciation_rate
        maintenance_pct = config.defaults.maintenance_annual_pct
        marginal_tax = config.defaults.marginal_tax_rate
        inflation = config.defaults.inflation_rate

        monthly_rent = round(price * _DEFAULT_RENT_TO_VALUE_MONTHLY, 2)
        annual_rent_increase = inflation

        monthly_pi = FinancialAnalyzer.calculate_monthly_payment(
            scenario.loan_amount, scenario.interest_rate, scenario.term_years
        )
        monthly_rate = scenario.interest_rate / 12.0
        total_months = scenario.term_years * 12

        # Pre-compute remaining balances & cumulative interest by year.
        balance = scenario.loan_amount
        cumulative_interest = 0.0
        balances_by_year: dict[int, float] = {}
        cum_interest_by_year: dict[int, float] = {}

        for month in range(1, total_months + 1):
            interest = balance * monthly_rate
            principal = monthly_pi - interest
            balance -= principal
            cumulative_interest += interest

            if month % 12 == 0:
                yr = month // 12
                balances_by_year[yr] = max(round(balance, 2), 0.0)
                cum_interest_by_year[yr] = round(cumulative_interest, 2)

        rent_total_cost: dict[int, float] = {}
        buy_total_cost: dict[int, float] = {}
        buy_break_even_year: int | None = None

        cumulative_rent = 0.0

        for year in range(1, _MAX_PROJECTION_YEARS + 1):
            # ---- Rent side ----
            annual_rent = monthly_rent * 12 * (1 + annual_rent_increase) ** (year - 1)
            cumulative_rent += annual_rent
            rent_total_cost[year] = round(cumulative_rent, 2)

            # ---- Buy side ----
            months_elapsed = min(year * 12, total_months)
            cumulative_payments = payment_breakdown.total * months_elapsed
            maintenance = maintenance_pct * price * year

            # Equity gained (home value minus remaining loan)
            home_value = price * (1 + appreciation) ** year
            remaining = balances_by_year.get(year, 0.0)
            equity = home_value - remaining

            # Tax benefit
            cum_int = cum_interest_by_year.get(year, cumulative_interest)
            tax_benefit = cum_int * marginal_tax

            net_buy_cost = round(
                cumulative_payments
                + closing_costs.total
                + maintenance
                - equity
                - tax_benefit,
                2,
            )
            buy_total_cost[year] = net_buy_cost

            # Detect first break-even
            if buy_break_even_year is None and net_buy_cost < rent_total_cost[year]:
                buy_break_even_year = year

        # Recommendation
        if buy_break_even_year is not None and buy_break_even_year <= 5:
            recommendation = "buy"
        elif buy_break_even_year is None or buy_break_even_year > 15:
            recommendation = "rent"
        else:
            recommendation = "marginal"

        return RentVsBuyComparison(
            monthly_rent_equivalent=monthly_rent,
            annual_rent_increase_pct=round(annual_rent_increase * 100, 2),
            buy_break_even_year=buy_break_even_year,
            rent_total_cost=rent_total_cost,
            buy_total_cost=buy_total_cost,
            recommendation=recommendation,
        )
