"""Tests for the financial analyzer."""

from __future__ import annotations

import pytest

from hpa.analysis.financial import FinancialAnalyzer
from hpa.models.financial import (
    AmortizationEntry,
    ClosingCosts,
    FinancialAnalysisResult,
    LoanScenario,
    MonthlyPaymentBreakdown,
)


@pytest.fixture()
def analyzer():
    """Create a FinancialAnalyzer."""
    return FinancialAnalyzer()


# ---------------------------------------------------------------------------
# Monthly payment calculations
# ---------------------------------------------------------------------------


class TestMonthlyPayment:
    """Tests for the core monthly mortgage payment formula."""

    def test_monthly_payment_calculation(self, analyzer):
        """A $360,000 loan at 6.5% for 30 years should be ~$2,275.29/month."""
        payment = analyzer.calculate_monthly_payment(
            principal=360_000, annual_rate=0.065, term_years=30
        )
        assert payment == pytest.approx(2275.44, abs=0.01)

    def test_monthly_payment_15yr(self, analyzer):
        """A $360,000 loan at 6.5% for 15 years should be higher than 30-year."""
        payment_15 = analyzer.calculate_monthly_payment(
            principal=360_000, annual_rate=0.065, term_years=15
        )
        payment_30 = analyzer.calculate_monthly_payment(
            principal=360_000, annual_rate=0.065, term_years=30
        )
        assert payment_15 > payment_30
        assert payment_15 == pytest.approx(3135.99, abs=1.0)

    def test_zero_interest_rate(self, analyzer):
        """0% interest should simply divide the loan evenly across months."""
        payment = analyzer.calculate_monthly_payment(
            principal=360_000, annual_rate=0.0, term_years=30
        )
        expected = 360_000 / (30 * 12)
        assert payment == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Loan scenarios
# ---------------------------------------------------------------------------


class TestLoanScenarios:
    """Tests for building loan scenario combinations."""

    def test_build_loan_scenarios(self, analyzer, sample_property, sample_config):
        """2 down-payment percentages x 2 term lengths = 4 scenarios."""
        scenarios = analyzer.build_loan_scenarios(
            property_details=sample_property,
            config=sample_config,
            down_payment_pcts=[0.10, 0.20],
            term_years=[15, 30],
        )
        assert len(scenarios) == 4
        assert all(isinstance(s, LoanScenario) for s in scenarios)
        for s in scenarios:
            expected_loan = sample_property.list_price * (1 - s.down_payment_pct)
            assert s.loan_amount == pytest.approx(expected_loan, rel=1e-6)


# ---------------------------------------------------------------------------
# Payment breakdowns (PMI logic)
# ---------------------------------------------------------------------------


class TestPaymentBreakdown:
    """Tests for the full monthly payment breakdown including PMI."""

    def test_payment_breakdown_includes_pmi(self, analyzer, sample_property, sample_config):
        """PMI should be included when the down payment is less than 20%."""
        scenario = LoanScenario(
            name="10pct-down-30yr",
            loan_amount=sample_property.list_price * 0.90,
            interest_rate=0.065,
            term_years=30,
            down_payment=sample_property.list_price * 0.10,
            down_payment_pct=0.10,
        )
        breakdown = analyzer.calculate_payment_breakdown(
            scenario=scenario,
            property_details=sample_property,
            config=sample_config,
        )
        assert isinstance(breakdown, MonthlyPaymentBreakdown)
        assert breakdown.pmi > 0

    def test_payment_breakdown_no_pmi(self, analyzer, sample_property, sample_config):
        """PMI should be zero when the down payment is >= 20%."""
        scenario = LoanScenario(
            name="20pct-down-30yr",
            loan_amount=sample_property.list_price * 0.80,
            interest_rate=0.065,
            term_years=30,
            down_payment=sample_property.list_price * 0.20,
            down_payment_pct=0.20,
        )
        breakdown = analyzer.calculate_payment_breakdown(
            scenario=scenario,
            property_details=sample_property,
            config=sample_config,
        )
        assert breakdown.pmi == 0.0


# ---------------------------------------------------------------------------
# Amortization schedule
# ---------------------------------------------------------------------------


class TestAmortizationSchedule:
    """Tests for the amortization schedule generation."""

    def _make_scenario(self, loan_amount, annual_rate, term_years):
        return LoanScenario(
            name=f"test-{term_years}yr",
            loan_amount=loan_amount,
            interest_rate=annual_rate,
            term_years=term_years,
            down_payment=0,
            down_payment_pct=0,
        )

    def test_amortization_schedule_length(self, analyzer, sample_property):
        """30-year schedule should have 360 entries; 15-year should have 180."""
        s30 = self._make_scenario(360_000, 0.065, 30)
        s15 = self._make_scenario(360_000, 0.065, 15)
        sched_30 = analyzer.generate_amortization_schedule(s30, sample_property)
        sched_15 = analyzer.generate_amortization_schedule(s15, sample_property)
        assert len(sched_30) == 360
        assert len(sched_15) == 180
        assert all(isinstance(e, AmortizationEntry) for e in sched_30)

    def test_amortization_final_balance_near_zero(self, analyzer, sample_property):
        """The remaining balance after the final payment should be ~$0."""
        s = self._make_scenario(360_000, 0.065, 30)
        schedule = analyzer.generate_amortization_schedule(s, sample_property)
        final = schedule[-1]
        assert final.remaining_balance == pytest.approx(0.0, abs=1.0)


# ---------------------------------------------------------------------------
# Closing costs
# ---------------------------------------------------------------------------


class TestClosingCosts:
    """Tests for the closing cost estimation."""

    def test_closing_costs_total(self, analyzer, sample_property, sample_config):
        """The individual line items should sum to the total field."""
        scenario = LoanScenario(
            name="test",
            loan_amount=sample_property.list_price * 0.80,
            interest_rate=0.065,
            term_years=30,
            down_payment=sample_property.list_price * 0.20,
            down_payment_pct=0.20,
        )
        costs = analyzer.estimate_closing_costs(
            property_details=sample_property,
            scenario=scenario,
            config=sample_config,
        )
        assert isinstance(costs, ClosingCosts)
        item_sum = (
            costs.loan_origination
            + costs.appraisal_fee
            + costs.title_insurance
            + costs.escrow_fees
            + costs.recording_fees
            + costs.prepaid_taxes
            + costs.prepaid_insurance
            + costs.inspection_fees
            + costs.other
        )
        assert costs.total == pytest.approx(item_sum, rel=1e-6)


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    """Tests for the top-level analyze() entry point."""

    def test_full_analysis(self, analyzer, sample_property, sample_config):
        """Running analyze() should return a well-formed FinancialAnalysisResult."""
        result = analyzer.analyze(
            property_details=sample_property,
            config=sample_config,
        )
        assert isinstance(result, FinancialAnalysisResult)
        assert len(result.scenarios) > 0
        for scenario in result.scenarios:
            assert scenario.name in result.payment_breakdowns
        for scenario in result.scenarios:
            assert scenario.name in result.amortization_schedules
        assert result.closing_costs.total > 0
