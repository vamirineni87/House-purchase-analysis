"""Tests for the financial analysis engine."""

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


class TestMonthlyPayment:
    def test_30yr_payment(self):
        assert calculate_monthly_payment(360_000, 0.065, 30) == pytest.approx(2275.44, abs=0.01)

    def test_15yr_higher_than_30yr(self):
        p15 = calculate_monthly_payment(360_000, 0.065, 15)
        p30 = calculate_monthly_payment(360_000, 0.065, 30)
        assert p15 > p30
        assert p15 == pytest.approx(3135.99, abs=1.0)

    def test_zero_interest(self):
        assert calculate_monthly_payment(360_000, 0.0, 30) == pytest.approx(1000.0, abs=0.01)


class TestLoanScenarios:
    def test_scenario_count(self):
        scenarios = build_loan_scenarios(450_000, [0.10, 0.20], [15, 30])
        assert len(scenarios) == 4
        for s in scenarios:
            expected_loan = 450_000 * (1 - s.down_payment_pct)
            assert s.loan_amount == pytest.approx(expected_loan, rel=1e-6)


class TestPaymentBreakdown:
    def test_pmi_with_10pct_down(self):
        s = LoanScenario(name="t", loan_amount=405_000, interest_rate=0.065, term_years=30, down_payment=45_000, down_payment_pct=0.10)
        assert calculate_payment_breakdown(s, 450_000).pmi > 0

    def test_no_pmi_with_20pct_down(self):
        s = LoanScenario(name="t", loan_amount=360_000, interest_rate=0.065, term_years=30, down_payment=90_000, down_payment_pct=0.20)
        assert calculate_payment_breakdown(s, 450_000).pmi == 0.0


class TestAmortization:
    def _s(self, loan, rate, term):
        return LoanScenario(name=f"t-{term}", loan_amount=loan, interest_rate=rate, term_years=term, down_payment=0, down_payment_pct=0)

    def test_schedule_length(self):
        assert len(generate_amortization_schedule(self._s(360_000, 0.065, 30), 450_000)) == 360
        assert len(generate_amortization_schedule(self._s(360_000, 0.065, 15), 450_000)) == 180

    def test_final_balance_zero(self):
        sched = generate_amortization_schedule(self._s(360_000, 0.065, 30), 450_000)
        assert sched[-1].remaining_balance == pytest.approx(0.0, abs=1.0)


class TestClosingCosts:
    def test_items_sum_to_total(self):
        cc = estimate_closing_costs(450_000, 360_000)
        items = cc.loan_origination + cc.appraisal_fee + cc.title_insurance + cc.escrow_fees + cc.recording_fees + cc.prepaid_taxes + cc.prepaid_insurance + cc.inspection_fees + cc.other
        assert cc.total == pytest.approx(items, rel=1e-6)


class TestFullAnalysis:
    def test_run_financial_analysis(self):
        r = run_financial_analysis(list_price=450_000, hoa_monthly=100)
        assert len(r.scenarios) == 4
        for s in r.scenarios:
            assert s.name in r.payment_breakdowns
            assert s.name in r.cash_needed_at_closing
        assert r.closing_costs.total > 0
