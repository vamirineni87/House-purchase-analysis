"""Tests for the financial analysis engine (ported from archive/cli-v1)."""

from __future__ import annotations

import pytest

from pipa.analysis.financial import (
    build_loan_scenarios,
    calculate_monthly_payment,
    calculate_payment_breakdown,
    estimate_closing_costs,
    generate_amortization_schedule,
    run_financial_analysis,
)
from pipa.schemas.financial import LoanScenario


# --- Monthly payment calculations ---

class TestMonthlyPayment:
    def test_30yr_payment(self):
        payment = calculate_monthly_payment(principal=360_000, annual_rate=0.065, term_years=30)
        assert payment == pytest.approx(2275.44, abs=0.01)

    def test_15yr_higher_than_30yr(self):
        p15 = calculate_monthly_payment(360_000, 0.065, 15)
        p30 = calculate_monthly_payment(360_000, 0.065, 30)
        assert p15 > p30
        assert p15 == pytest.approx(3135.99, abs=1.0)

    def test_zero_interest(self):
        payment = calculate_monthly_payment(360_000, 0.0, 30)
        assert payment == pytest.approx(360_000 / 360, abs=0.01)


# --- Loan scenarios ---

class TestLoanScenarios:
    def test_scenario_count(self):
        scenarios = build_loan_scenarios(450_000, [0.10, 0.20], [15, 30])
        assert len(scenarios) == 4
        for s in scenarios:
            expected_loan = 450_000 * (1 - s.down_payment_pct)
            assert s.loan_amount == pytest.approx(expected_loan, rel=1e-6)


# --- Payment breakdown (PMI logic) ---

class TestPaymentBreakdown:
    def test_pmi_with_10pct_down(self):
        scenario = LoanScenario(
            name="test", loan_amount=405_000, interest_rate=0.065,
            term_years=30, down_payment=45_000, down_payment_pct=0.10,
        )
        bd = calculate_payment_breakdown(scenario, 450_000)
        assert bd.pmi > 0

    def test_no_pmi_with_20pct_down(self):
        scenario = LoanScenario(
            name="test", loan_amount=360_000, interest_rate=0.065,
            term_years=30, down_payment=90_000, down_payment_pct=0.20,
        )
        bd = calculate_payment_breakdown(scenario, 450_000)
        assert bd.pmi == 0.0


# --- Amortization ---

class TestAmortization:
    def _make(self, loan, rate, term):
        return LoanScenario(
            name=f"test-{term}", loan_amount=loan, interest_rate=rate,
            term_years=term, down_payment=0, down_payment_pct=0,
        )

    def test_schedule_length(self):
        assert len(generate_amortization_schedule(self._make(360_000, 0.065, 30), 450_000)) == 360
        assert len(generate_amortization_schedule(self._make(360_000, 0.065, 15), 450_000)) == 180

    def test_final_balance_zero(self):
        schedule = generate_amortization_schedule(self._make(360_000, 0.065, 30), 450_000)
        assert schedule[-1].remaining_balance == pytest.approx(0.0, abs=1.0)


# --- Closing costs ---

class TestClosingCosts:
    def test_items_sum_to_total(self):
        costs = estimate_closing_costs(450_000, 360_000)
        item_sum = (
            costs.loan_origination + costs.appraisal_fee + costs.title_insurance
            + costs.escrow_fees + costs.recording_fees + costs.prepaid_taxes
            + costs.prepaid_insurance + costs.inspection_fees + costs.other
        )
        assert costs.total == pytest.approx(item_sum, rel=1e-6)


# --- Full analysis ---

class TestFullAnalysis:
    def test_run_financial_analysis(self):
        result = run_financial_analysis(list_price=450_000, hoa_monthly=100)
        assert len(result.scenarios) == 4
        for s in result.scenarios:
            assert s.name in result.payment_breakdowns
            assert s.name in result.amortization_schedules
            assert s.name in result.cash_needed_at_closing
        assert result.closing_costs.total > 0
