"""Tax analysis with special focus on 2nd home purchase scenarios.

Analyzes both sell and rent strategies for the current (first) home,
mortgage interest deductions, property tax deductions (with SALT cap),
and overall annual tax benefits.
"""

from __future__ import annotations

import logging
from typing import Optional

from hpa.analysis.base import BaseAnalyzer
from hpa.config import AppConfig, CurrentHomeConfig
from hpa.models.financial import LoanScenario
from hpa.models.property import PropertyDetails
from hpa.models.tax import (
    CapitalGainsAnalysis,
    FirstHomeStrategy,
    MortgageInterestDeduction,
    PropertyTaxDeduction,
    RentalIncomeAnalysis,
    TaxAnalysisResult,
)

logger = logging.getLogger(__name__)

# IRS limits (2024+)
_SALT_CAP = 10_000.0
_MORTGAGE_INTEREST_LOAN_CAP = 750_000.0
_CAPITAL_GAINS_EXCLUSION_MARRIED = 500_000.0
_CAPITAL_GAINS_EXCLUSION_SINGLE = 250_000.0
_LONG_TERM_CAPITAL_GAINS_RATE = 0.15
_SELLING_COST_PCT = 0.08  # 6% agent + 2% closing
_RESIDENTIAL_STRUCTURE_PCT = 0.85  # land ~15% of property value
_RESIDENTIAL_DEPRECIATION_YEARS = 27.5
_PRIMARY_RESIDENCE_YEARS_REQUIRED = 2.0
_RENT_COMPARISON_YEARS = 10


class TaxAnalyzer(BaseAnalyzer):
    """Performs tax analysis for a home purchase, including first-home
    sell-vs-rent strategy when the buyer already owns a property."""

    @property
    def name(self) -> str:
        return "Tax Analysis"

    def analyze(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
        primary_scenario: Optional[LoanScenario] = None,
    ) -> TaxAnalysisResult:
        """Run full tax analysis for the prospective purchase.

        Parameters
        ----------
        property_details:
            The new property being evaluated.
        config:
            Application configuration including current home info and defaults.
        primary_scenario:
            The primary loan scenario to use for mortgage interest deduction
            calculations.  When *None*, a simple scenario is synthesised from
            the property price and a 20% down payment at 6.5%.
        """
        first_home_strategy: Optional[FirstHomeStrategy] = None

        # --- First-home strategy (sell vs. rent) ---
        if config.current_home is not None:
            sell_analysis = self.analyze_capital_gains(
                config.current_home, config
            )
            rent_analysis = self.analyze_rental_income(
                config.current_home, config
            )
            first_home_strategy = self.recommend_strategy(
                sell_analysis, rent_analysis
            )

        # --- Mortgage interest deduction on the new home ---
        if primary_scenario is None:
            # Synthesise a default 20%-down / 30-yr scenario.
            price = property_details.list_price
            down = round(price * 0.20, 2)
            primary_scenario = LoanScenario(
                name="default-20pct-30yr",
                loan_amount=round(price - down, 2),
                interest_rate=0.065,
                term_years=30,
                down_payment=down,
                down_payment_pct=0.20,
            )

        mortgage_deduction = self.calculate_mortgage_interest_deduction(
            primary_scenario, config
        )

        # --- Property tax deduction (SALT-capped) ---
        property_tax_deduction = self.calculate_property_tax_deduction(
            property_details, config
        )

        # --- Aggregate ---
        total_annual_benefit = round(
            mortgage_deduction.tax_savings
            + property_tax_deduction.tax_savings,
            2,
        )

        return TaxAnalysisResult(
            first_home_strategy=first_home_strategy,
            mortgage_interest_deduction=mortgage_deduction,
            property_tax_deduction=property_tax_deduction,
            total_annual_tax_benefit=total_annual_benefit,
            effective_monthly_cost_reduction=round(
                total_annual_benefit / 12.0, 2
            ),
        )

    # ------------------------------------------------------------------
    # Capital gains (selling the current home)
    # ------------------------------------------------------------------

    def analyze_capital_gains(
        self,
        current_home: CurrentHomeConfig,
        config: AppConfig,
    ) -> CapitalGainsAnalysis:
        """Estimate capital gains tax and net proceeds from selling the
        current home."""

        sale_price = current_home.estimated_current_value
        selling_costs = round(sale_price * _SELLING_COST_PCT, 2)
        cost_basis = round(
            current_home.purchase_price + current_home.capital_improvements, 2
        )
        gross_gain = round(sale_price - cost_basis, 2)

        meets_test = (
            current_home.years_as_primary_residence
            >= _PRIMARY_RESIDENCE_YEARS_REQUIRED
        )

        if meets_test:
            if config.defaults.filing_status == "married":
                exclusion = _CAPITAL_GAINS_EXCLUSION_MARRIED
            else:
                exclusion = _CAPITAL_GAINS_EXCLUSION_SINGLE
        else:
            exclusion = 0.0

        taxable_gain = round(max(0.0, gross_gain - exclusion), 2)
        estimated_tax = round(
            taxable_gain * _LONG_TERM_CAPITAL_GAINS_RATE, 2
        )
        net_proceeds = round(
            sale_price
            - selling_costs
            - current_home.remaining_mortgage_balance
            - estimated_tax,
            2,
        )

        return CapitalGainsAnalysis(
            purchase_price=current_home.purchase_price,
            estimated_sale_price=sale_price,
            selling_costs=selling_costs,
            cost_basis=cost_basis,
            gross_gain=gross_gain,
            exclusion_amount=exclusion,
            taxable_gain=taxable_gain,
            estimated_federal_tax=estimated_tax,
            meets_primary_residence_test=meets_test,
            years_owned=current_home.years_as_primary_residence,
            years_as_primary=current_home.years_as_primary_residence,
            net_proceeds=net_proceeds,
        )

    # ------------------------------------------------------------------
    # Rental income (renting out the current home)
    # ------------------------------------------------------------------

    def analyze_rental_income(
        self,
        current_home: CurrentHomeConfig,
        config: AppConfig,
    ) -> RentalIncomeAnalysis:
        """Project cash flow and tax benefits from renting out the current
        home instead of selling it."""

        monthly_rent = current_home.estimated_monthly_rent
        monthly_mortgage = current_home.monthly_payment
        monthly_taxes = round(current_home.annual_property_tax / 12.0, 2)
        monthly_insurance = round(current_home.annual_insurance / 12.0, 2)
        monthly_maintenance = round(
            (
                current_home.estimated_current_value
                * config.defaults.maintenance_annual_pct
            )
            / 12.0,
            2,
        )
        vacancy_loss = round(
            monthly_rent * config.defaults.vacancy_rate, 2
        )

        monthly_cash_flow = round(
            monthly_rent
            - monthly_mortgage
            - monthly_taxes
            - monthly_insurance
            - monthly_maintenance
            - vacancy_loss,
            2,
        )
        annual_cash_flow = round(monthly_cash_flow * 12.0, 2)

        # Depreciation: structure value (85% of purchase price) over 27.5 years.
        annual_depreciation = round(
            (current_home.purchase_price * _RESIDENTIAL_STRUCTURE_PCT)
            / _RESIDENTIAL_DEPRECIATION_YEARS,
            2,
        )
        annual_tax_benefit = round(
            annual_depreciation * config.defaults.marginal_tax_rate, 2
        )

        net_annual_return = round(annual_cash_flow + annual_tax_benefit, 2)

        # Cap rate: (annual cash flow + depreciation benefit) / property value
        if current_home.estimated_current_value > 0:
            cap_rate = round(
                net_annual_return / current_home.estimated_current_value, 4
            )
        else:
            cap_rate = 0.0

        return RentalIncomeAnalysis(
            monthly_rent=monthly_rent,
            monthly_mortgage=monthly_mortgage,
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

    def recommend_strategy(
        self,
        sell: CapitalGainsAnalysis,
        rent: RentalIncomeAnalysis,
    ) -> FirstHomeStrategy:
        """Compare selling vs. renting and return a recommendation."""

        sell_net = sell.net_proceeds
        rent_10yr_net = round(
            rent.annual_cash_flow * _RENT_COMPARISON_YEARS
            + rent.annual_tax_benefit_from_depreciation
            * _RENT_COMPARISON_YEARS,
            2,
        )

        if sell_net > rent_10yr_net:
            recommendation = "sell"
            reason = (
                f"Selling yields ${sell_net:,.0f} in net proceeds, which "
                f"exceeds the estimated 10-year rental net of "
                f"${rent_10yr_net:,.0f}. Selling provides immediate "
                f"liquidity for the new purchase."
            )
        elif rent_10yr_net > sell_net * 1.2:
            # Renting must be meaningfully better (>20% more) to recommend
            # it over the simplicity of selling.
            recommendation = "rent"
            reason = (
                f"Renting out the home is projected to return "
                f"${rent_10yr_net:,.0f} over 10 years, significantly more "
                f"than the ${sell_net:,.0f} net from selling. Monthly cash "
                f"flow of ${rent.monthly_cash_flow:,.0f} provides ongoing "
                f"income."
            )
        else:
            recommendation = "either"
            reason = (
                f"Both options are viable. Selling nets ${sell_net:,.0f} "
                f"immediately, while renting projects ${rent_10yr_net:,.0f} "
                f"over 10 years. Consider your risk tolerance, desire for "
                f"landlord responsibilities, and liquidity needs."
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
        self,
        scenario: LoanScenario,
        config: AppConfig,
    ) -> MortgageInterestDeduction:
        """Calculate the first-year mortgage interest deduction.

        For loans exceeding $750k, only the portion of interest attributable
        to the first $750k of principal is deductible.
        """
        rate = scenario.interest_rate
        loan = scenario.loan_amount
        term_months = scenario.term_years * 12

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
        if loan > _MORTGAGE_INTEREST_LOAN_CAP:
            deductible_ratio = _MORTGAGE_INTEREST_LOAN_CAP / loan
            deductible_amount = round(annual_interest * deductible_ratio, 2)
        else:
            deductible_amount = annual_interest

        marginal_rate = config.defaults.marginal_tax_rate
        tax_savings = round(deductible_amount * marginal_rate, 2)

        return MortgageInterestDeduction(
            annual_interest_paid=annual_interest,
            deductible_amount=deductible_amount,
            tax_savings=tax_savings,
            marginal_tax_rate=marginal_rate,
        )

    # ------------------------------------------------------------------
    # Property tax deduction (SALT cap)
    # ------------------------------------------------------------------

    def calculate_property_tax_deduction(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> PropertyTaxDeduction:
        """Calculate property tax deduction subject to the $10k SALT cap."""

        annual_property_tax = round(
            property_details.list_price * config.defaults.property_tax_rate, 2
        )
        deductible_amount = min(annual_property_tax, _SALT_CAP)
        salt_cap_hit = annual_property_tax > _SALT_CAP
        marginal_rate = config.defaults.marginal_tax_rate
        tax_savings = round(deductible_amount * marginal_rate, 2)

        return PropertyTaxDeduction(
            annual_property_tax=annual_property_tax,
            deductible_amount=deductible_amount,
            tax_savings=tax_savings,
            salt_cap_hit=salt_cap_hit,
        )
