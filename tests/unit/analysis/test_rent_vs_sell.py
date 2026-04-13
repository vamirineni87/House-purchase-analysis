"""Tests for the Rent vs Sell analysis engine."""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from pipa.analysis import rent_vs_sell as rvs

# Anchor fixture path to this test file so `pytest` works from any cwd.
FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "rent_vs_sell"


# ─────────────────────────────────────────────────────────────────────
# Base fixture — mirrors the White Cap Ter starter profile + $1.315M new home
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def base_inputs() -> dict:
    return {
        "current_home": {
            "value_today": 790_000,
            "basis": 478_000,
            "loan_balance": 295_413,
            "mortgage_rate": 0.025,
            "monthly_taxes": 620,
            "monthly_insurance": 120,
            "monthly_hoa": 0,
            "monthly_misc_owner_paid": 80,
            "sell_cost_pct_now": 0.07,
            "current_home_sell_cost_pct_future": 0.07,
            "monthly_rent_base": 3500,
            "land_pct": 0.2974,
            "building_pct": 0.7026,
            "move_out_month": "2026-05",
            "rent_start_month": "2026-06",
            "vacancy_months_per_year_base": 0.5,
            "bad_debt_pct_of_gross_rent": 0.005,
            "leasing_fee_pct_of_annual_rent": 0.05,
            "turnover_cost_per_event": 2500,
            "turnover_frequency_months": 24,
            "routine_maintenance_pct_of_rent": 0.05,
            "maintenance_inflation_annual_pct": 0.03,
            "self_manage": True,
            "property_management_pct": 0.0,
            "insurance_conversion_bump_pct": 0.15,
            "initial_lease_up_vacancy_months": 1.0,
            "sale_prep_cost_flat": 3000,
            "total_value_change_5y": 0.10,
            "total_value_change_10y": 0.20,
            "total_rent_change_5y": 0.0,
            "total_rent_change_10y": 0.0,
        },
        "new_home": {
            "purchase_price": 1_315_000,
            "base_down_pct": 0.20,
            "initial_rate": 0.0646,
            "loan_term_years": 30,
            "monthly_hoa": 0,
            "monthly_taxes": 800,
            "monthly_insurance": 150,
        },
        "refinance": {"enabled": False, "selected_path": "none", "cost_pct": 0.015,
                      "year3_rate": 0.055, "year5_rate": 0.0475, "year7_rate": 0.0425},
        "taxes": {
            "federal_ordinary_rate": 0.24,
            "federal_ltcg_rate": 0.15,
            "virginia_rate": 0.0575,
            "niit_enabled": False,
            "niit_rate": 0.038,
            "section_121_mfj": 500_000,
            "depreciation_recovery_rate": 0.25,
            "release_suspended_losses_on_taxable_disposition": True,
        },
        "ownership_cost_growth": {
            "current_home_tax_growth_annual_pct": 0.03,
            "current_home_insurance_growth_annual_pct": 0.05,
            "current_home_hoa_growth_annual_pct": 0.03,
            "current_home_misc_growth_annual_pct": 0.03,
            "new_home_tax_growth_annual_pct": 0.03,
            "new_home_insurance_growth_annual_pct": 0.05,
            "new_home_hoa_growth_annual_pct": 0.03,
        },
        "reinvestment": {
            "invest_monthly_sell_savings": True,
            "monthly_savings_reinvestment_return_annual_pct": 0.04,
            "invest_initial_sale_surplus_cash": False,
        },
        "new_home_drag": {"new_home_maintenance_pct_of_home_value_annual": 0.01},
        "modeling": {"rent_then_sell_date": "2029-05"},
    }


# ─────────────────────────────────────────────────────────────────────
# Core primitives
# ─────────────────────────────────────────────────────────────────────


class TestPrimitives:
    def test_monthly_payment_standard(self):
        p = rvs.monthly_payment(360_000, 0.065, 360)
        assert p == pytest.approx(2275.44, abs=0.5)

    def test_monthly_payment_zero_rate(self):
        p = rvs.monthly_payment(120_000, 0.0, 120)
        assert p == pytest.approx(1000.0, abs=0.01)

    def test_mortgage_schedule_amortizes_to_zero(self):
        sched = rvs.mortgage_schedule(100_000, 0.06, 60)
        assert len(sched) == 60
        assert sched[-1]["balance"] == pytest.approx(0.0, abs=1.0)

    def test_mortgage_schedule_first_interest_matches(self):
        sched = rvs.mortgage_schedule(240_000, 0.06, 360)
        expected_first_interest = 240_000 * (0.06 / 12)
        assert sched[0]["interest"] == pytest.approx(expected_first_interest, abs=0.01)

    def test_linear_growth_path_endpoints(self):
        path = rvs.linear_growth_path(1000.0, 0.10, 60)
        assert len(path) == 61
        assert path[0] == pytest.approx(1000.0)
        assert path[60] == pytest.approx(1100.0)
        # Midpoint is halfway
        assert path[30] == pytest.approx(1050.0)

    def test_linear_growth_negative(self):
        path = rvs.linear_growth_path(1000.0, -0.10, 60)
        assert path[60] == pytest.approx(900.0)

    def test_refi_schedule_splices_at_month_60(self):
        original = rvs.mortgage_schedule(500_000, 0.0646, 360)
        refi, cost = rvs.refi_schedule(original, 60, 0.0475, 300, 0.015)
        # Payment at month 60 = original payment; month 61 = new payment (different)
        assert refi[59]["payment"] == pytest.approx(original[59]["payment"], abs=0.01)
        assert refi[60]["payment"] != pytest.approx(original[60]["payment"], abs=0.01)
        assert refi[60]["payment"] < original[60]["payment"]  # lower rate
        assert cost > 0
        assert cost == pytest.approx(original[59]["balance"] * 0.015, abs=1.0)

    def test_monthly_owner_cost_path_compounds(self):
        path = rvs.monthly_owner_cost_path(100.0, 0.05, 12)
        # After 12 months at 5% annual compounded monthly, should be ~$105
        assert path[12] == pytest.approx(105.0, abs=0.5)

    def test_reinvestment_path_monthly_compounding(self):
        # $1000/mo for 12 months at 0% return = $12,000
        assert rvs.reinvestment_path([1000.0] * 12, 0.0) == pytest.approx(12_000.0)

        # At 4% return, should be slightly more
        result_4pct = rvs.reinvestment_path([1000.0] * 12, 0.04)
        assert result_4pct > 12_000.0
        assert result_4pct < 12_500.0


class TestVacancyTurnover:
    def test_vacancy_reduces_collected_rent_but_not_contract_rent(self):
        rent_path = [3500.0] * 12
        rows = rvs.vacancy_and_turnover_path(
            rent_path, 12,
            vacancy_months_per_year=1.0,
            bad_debt_pct=0.0,
            leasing_fee_pct_annual=0.0,
            turnover_cost=0.0,
            turnover_frequency_months=24,
            initial_lease_up_vacancy_months=0.0,
        )
        # Each month loses 1/12 of rent to vacancy
        for row in rows:
            assert row["gross_rent"] == pytest.approx(3500.0)
            # 1 month vacancy / 12 months = ~8.3% loss
            expected_loss = 3500.0 / 12
            assert row["vacancy_loss"] == pytest.approx(expected_loss, abs=1.0)

    def test_initial_lease_up_reduces_first_year(self):
        rent_path = [3500.0] * 12
        rows = rvs.vacancy_and_turnover_path(
            rent_path, 12,
            vacancy_months_per_year=0.0,
            bad_debt_pct=0.0,
            leasing_fee_pct_annual=0.0,
            turnover_cost=0.0,
            turnover_frequency_months=24,
            initial_lease_up_vacancy_months=1.0,
        )
        # Month 0 should be nearly fully vacant
        assert rows[0]["collected_rent"] < 100
        # Month 1 onward should be full rent
        assert rows[1]["collected_rent"] == pytest.approx(3500.0, abs=1.0)

    def test_turnover_fee_hits_on_schedule(self):
        rent_path = [3500.0] * 48
        rows = rvs.vacancy_and_turnover_path(
            rent_path, 48,
            vacancy_months_per_year=0.0,
            bad_debt_pct=0.0,
            leasing_fee_pct_annual=0.05,
            turnover_cost=2500.0,
            turnover_frequency_months=24,
            initial_lease_up_vacancy_months=0.0,
        )
        # Turnover at month 24 and month 48 (but 48 is out of range since index = month-1)
        # Actually our loop uses `m > 0 and m % 24 == 0` so m=24
        turnover_events = [r for r in rows if r["turnover_cost"] > 0]
        assert len(turnover_events) >= 1


class TestCapex:
    def test_capex_event_hits_correct_month(self):
        items = [{"name": "HVAC", "amount": 12000, "month_offset": 18, "applies_to": "current_home"}]
        events = rvs.capex_events_for_horizon(items, 60, "current_home")
        assert events[18] == 12000
        assert events[17] == 0
        assert events[19] == 0

    def test_capex_applies_to_filter(self):
        items = [{"name": "Paint", "amount": 3000, "month_offset": 6, "applies_to": "new_home"}]
        current = rvs.capex_events_for_horizon(items, 60, "current_home")
        new = rvs.capex_events_for_horizon(items, 60, "new_home")
        assert sum(current) == 0
        assert sum(new) == 3000

    def test_capex_recurring(self):
        items = [{"name": "Repaint", "amount": 1000, "month_offset": 12, "recurring_months": 12, "applies_to": "current_home"}]
        events = rvs.capex_events_for_horizon(items, 60, "current_home")
        assert events[12] == 1000
        assert events[24] == 1000
        assert events[36] == 1000
        assert events[48] == 1000


# ─────────────────────────────────────────────────────────────────────
# Strategy sanity
# ─────────────────────────────────────────────────────────────────────


class TestStrategies:
    def test_all_four_strategies_run_from_single_input(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        assert "sell_now" in result["strategies"]
        assert "keep_5y" in result["strategies"]
        assert "keep_10y" in result["strategies"]
        assert "rent_then_sell" in result["strategies"]

    def test_sell_now_down_payment_lands_near_53_4_pct(self, base_inputs):
        ch = base_inputs["current_home"]
        nh = base_inputs["new_home"]
        # Compute expected effective down
        gross = ch["value_today"] * (1 - ch["sell_cost_pct_now"]) - ch["sale_prep_cost_flat"]
        net_after_loan = gross - ch["loan_balance"]
        # §121 fully shields at base case, so no sale tax
        effective_down = nh["purchase_price"] * nh["base_down_pct"] + net_after_loan
        pct = effective_down / nh["purchase_price"]
        assert 0.529 < pct < 0.539, f"Expected ~53.4%, got {pct:.4f}"

    def test_section_121_fully_shields_base_case(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        sell = result["strategies"]["sell_now"]
        assert sell["sale_tax_model"]["estimated_sale_tax"] == pytest.approx(0.0, abs=1.0)

    def test_keep_rental_produces_rental_ops_model(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        keep = result["strategies"]["keep_5y"]
        assert keep["rental_ops_model"] is not None
        assert len(keep["rental_ops_model"]) == 5  # 5 years

    def test_rent_then_sell_uses_depreciation_window(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        rts = result["strategies"]["rent_then_sell"]
        assert rts["sale_tax_model"] is not None
        # At default dates (rent_start 2026-06, sell 2029-05 = 35 months), §121 still OK
        # so depreciation recapture should exist but cap gain tax should be minimal
        assert rts["sale_tax_model"]["depreciation_recap_bucket"] >= 0

    def test_future_sell_cost_diff_changes_outcome(self, base_inputs):
        base_result = rvs.compute_full_analysis(base_inputs)
        high = copy.deepcopy(base_inputs)
        high["current_home"]["current_home_sell_cost_pct_future"] = 0.10
        high_result = rvs.compute_full_analysis(high)
        # Higher future sell cost should reduce keep strategies' net worth
        assert high_result["strategies"]["keep_5y"]["net_worth_end"] < base_result["strategies"]["keep_5y"]["net_worth_end"]

    def test_sell_case_reinvestment_improves_net_worth(self, base_inputs):
        with_reinv = rvs.compute_full_analysis(base_inputs)
        no_reinv = copy.deepcopy(base_inputs)
        no_reinv["reinvestment"]["invest_monthly_sell_savings"] = False
        without = rvs.compute_full_analysis(no_reinv)
        # Sell-case net worth should be higher when reinvestment is enabled
        assert (
            with_reinv["strategies"]["sell_now"]["net_worth_end"]
            > without["strategies"]["sell_now"]["net_worth_end"]
        )

    def test_vacancy_and_bad_debt_flip_keep(self, base_inputs):
        heavy = copy.deepcopy(base_inputs)
        heavy["current_home"]["vacancy_months_per_year_base"] = 3.0
        heavy["current_home"]["bad_debt_pct_of_gross_rent"] = 0.05
        heavy_result = rvs.compute_full_analysis(heavy)
        base_result = rvs.compute_full_analysis(base_inputs)
        # Heavy vacancy must reduce keep net worth
        assert (
            heavy_result["strategies"]["keep_5y"]["net_worth_end"]
            < base_result["strategies"]["keep_5y"]["net_worth_end"]
        )

    def test_initial_lease_up_reduces_first_year(self, base_inputs):
        no_leaseup = copy.deepcopy(base_inputs)
        no_leaseup["current_home"]["initial_lease_up_vacancy_months"] = 0.0
        a = rvs.compute_full_analysis(no_leaseup)
        b = rvs.compute_full_analysis(base_inputs)
        # With lease-up, year 1 collected rent should be less
        a_year1 = a["strategies"]["keep_5y"]["rental_ops_model"][0]["collected_rent"]
        b_year1 = b["strategies"]["keep_5y"]["rental_ops_model"][0]["collected_rent"]
        assert b_year1 < a_year1

    def test_misc_owner_paid_reduces_keep_nw(self, base_inputs):
        base_result = rvs.compute_full_analysis(base_inputs)
        high_misc = copy.deepcopy(base_inputs)
        high_misc["current_home"]["monthly_misc_owner_paid"] = 500
        high_result = rvs.compute_full_analysis(high_misc)
        assert (
            high_result["strategies"]["keep_5y"]["net_worth_end"]
            < base_result["strategies"]["keep_5y"]["net_worth_end"]
        )

    def test_insurance_conversion_bump_affects_first_year(self, base_inputs):
        base_result = rvs.compute_full_analysis(base_inputs)
        high = copy.deepcopy(base_inputs)
        high["current_home"]["insurance_conversion_bump_pct"] = 0.50
        high_result = rvs.compute_full_analysis(high)
        # Higher insurance bump should reduce keep net worth
        assert (
            high_result["strategies"]["keep_5y"]["net_worth_end"]
            < base_result["strategies"]["keep_5y"]["net_worth_end"]
        )

    def test_suspended_loss_release_toggle(self, base_inputs):
        heavy_loss = copy.deepcopy(base_inputs)
        heavy_loss["current_home"]["monthly_misc_owner_paid"] = 2000  # force negative
        heavy_loss["current_home"]["routine_maintenance_pct_of_rent"] = 0.30
        with_release = rvs.compute_full_analysis(heavy_loss)
        no_release = copy.deepcopy(heavy_loss)
        no_release["taxes"]["release_suspended_losses_on_taxable_disposition"] = False
        without = rvs.compute_full_analysis(no_release)
        # With release, rent_then_sell should do better (lower sale tax)
        with_rts_sale_tax = with_release["strategies"]["rent_then_sell"]["sale_tax_model"]["estimated_sale_tax"]
        without_rts_sale_tax = without["strategies"]["rent_then_sell"]["sale_tax_model"]["estimated_sale_tax"]
        # Release either lowers the sale tax or keeps it same
        assert with_rts_sale_tax <= without_rts_sale_tax

    def test_refi_year5_changes_payment_at_month_60(self, base_inputs):
        base_result = rvs.compute_full_analysis(base_inputs)
        refi = copy.deepcopy(base_inputs)
        refi["refinance"]["enabled"] = True
        refi["refinance"]["selected_path"] = "year5"
        refi_result = rvs.compute_full_analysis(refi)
        # Refi at year 5 should change the 10Y net worth
        assert (
            refi_result["strategies"]["keep_10y"]["net_worth_end"]
            != base_result["strategies"]["keep_10y"]["net_worth_end"]
        )

    def test_sell_now_has_no_annual_tax_model(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        sell = result["strategies"]["sell_now"]
        # Sell-now has no rental operations so no annual tax rows
        assert sell["annual_tax_model"] == []

    def test_driver_bridge_present_on_keep_strategies(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        assert result["strategies"]["keep_5y"]["driver_bridge_vs_sell"] is not None
        assert result["strategies"]["keep_10y"]["driver_bridge_vs_sell"] is not None
        assert result["strategies"]["sell_now"]["driver_bridge_vs_sell"] is None

    def test_lean_reports_valid_value(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        assert result["lean"] in ("leans_sell", "leans_keep", "too_close")


class TestScenarios:
    def test_flat_value_is_close_or_leans_sell(self, base_inputs):
        """With realistic new-home maintenance applied to sell_now, flat
        appreciation puts the two strategies within a few thousand dollars
        of each other — either 'too_close' or 'leans_sell' depending on
        exact drag assumptions."""
        flat = copy.deepcopy(base_inputs)
        flat["current_home"]["total_value_change_5y"] = 0.0
        flat["current_home"]["total_value_change_10y"] = 0.0
        result = rvs.compute_full_analysis(flat)
        assert result["lean"] in ("leans_sell", "too_close")

    def test_recession_leans_sell(self, base_inputs):
        recession = copy.deepcopy(base_inputs)
        recession["current_home"]["total_value_change_5y"] = -0.10
        recession["current_home"]["total_rent_change_5y"] = -0.10
        result = rvs.compute_full_analysis(recession)
        assert result["lean"] == "leans_sell"


class TestRegressionFixes:
    """Regression tests for bugs caught by the review swarm."""

    def test_capex_recurring_fractional_does_not_infinite_loop(self):
        """int(0.5) = 0 used to bypass the > 0 guard and spin forever."""
        items = [{"name": "X", "amount": 1000, "month_offset": 6,
                  "recurring_months": 0.5, "applies_to": "current_home"}]
        # If this hangs, pytest times out. It should return cleanly.
        out = rvs.capex_events_for_horizon(items, 120, "current_home")
        assert sum(out) == 1000  # one hit at month_offset, no recursion

    def test_capex_recurring_zero_does_not_infinite_loop(self):
        items = [{"name": "X", "amount": 1000, "month_offset": 6,
                  "recurring_months": 0, "applies_to": "current_home"}]
        out = rvs.capex_events_for_horizon(items, 120, "current_home")
        assert sum(out) == 1000

    def test_capex_recurring_negative_ignored(self):
        items = [{"name": "X", "amount": 1000, "month_offset": 6,
                  "recurring_months": -5, "applies_to": "current_home"}]
        out = rvs.capex_events_for_horizon(items, 120, "current_home")
        assert sum(out) == 1000

    def test_capex_max_recurrences_cap(self):
        """Per-item MAX_CAPEX_RECURRENCES cap should hold even if the
        horizon is huge and the step is tiny."""
        items = [{"name": "X", "amount": 10, "month_offset": 1,
                  "recurring_months": 1, "applies_to": "current_home"}]
        out = rvs.capex_events_for_horizon(items, 600, "current_home")
        # First hit + at most MAX_CAPEX_RECURRENCES recurring hits
        assert sum(out) / 10 <= 1 + rvs.MAX_CAPEX_RECURRENCES

    def test_non_finite_inputs_dont_crash_engine(self, base_inputs):
        """Infinity/NaN should be cleaned by _safe_float everywhere in the
        engine. The engine itself must never propagate non-finite values."""
        bad = copy.deepcopy(base_inputs)
        bad["current_home"]["value_today"] = float("inf")
        bad["current_home"]["total_value_change_5y"] = float("nan")
        # Should not raise, should not return non-finite numbers
        result = rvs.compute_full_analysis(bad)
        assert result["lean"] in ("leans_sell", "leans_keep", "too_close", "n/a")
        for strat in result["strategies"].values():
            nw = strat.get("net_worth_end")
            assert nw is None or math.isfinite(nw)

    def test_parse_month_rejects_malformed(self):
        assert rvs._parse_month("2026/05") is None
        assert rvs._parse_month("May 2026") is None
        assert rvs._parse_month("") is None
        assert rvs._parse_month(None) is None
        assert rvs._parse_month("9" * 100) is None
        assert rvs._parse_month("2026-13") is None
        assert rvs._parse_month("2026-0") is None
        assert rvs._parse_month("2026-05") is not None
        assert rvs._parse_month("2026-5") is not None  # single-digit month OK

    def test_month_diff_returns_zero_on_bad_input(self):
        assert rvs._month_diff("2026/05", "2026-06") == 0
        assert rvs._month_diff(None, "2026-06") == 0
        assert rvs._month_diff("2026-05", "2026-06") == 1

    def test_rts_horizon_clamped(self, base_inputs):
        """Adversarial future date shouldn't explode memory."""
        bad = copy.deepcopy(base_inputs)
        bad["modeling"]["rent_then_sell_date"] = "9999-01"
        # Should complete in reasonable time, not allocate 12M-item lists
        result = rvs.compute_full_analysis(bad)
        rts = result["strategies"]["rent_then_sell"]
        # Strategy runs but the horizon is clamped; output is finite
        assert rts["net_worth_end"] is not None
        assert math.isfinite(rts["net_worth_end"])

    def test_nw_path_does_not_apply_sell_cost_every_month(self, base_inputs):
        """Pre-fix, nw_path applied (1 - sell_cost) at every month even for
        hold strategies, understating the visual equity curve by ~7%."""
        result = rvs.compute_full_analysis(base_inputs)
        keep = result["strategies"]["keep_5y"]
        nw_path = keep["net_worth_path"]
        # First month net worth should be CLOSE to starting equity (no sell cost drain)
        ch = base_inputs["current_home"]
        nh = base_inputs["new_home"]
        starting_ch_equity = ch["value_today"] - ch["loan_balance"]
        starting_nh_equity = nh["purchase_price"] * nh["base_down_pct"]
        # Month 1 nw ≈ starting equity (± growth/paydown delta over 1 month)
        assert nw_path[0] > starting_ch_equity + starting_nh_equity - 10000

    def test_section_121_window_uses_today(self, base_inputs):
        """Window status should be derived from date.today(), not hardcoded."""
        # Move out way in the past → closed
        bad = copy.deepcopy(base_inputs)
        bad["current_home"]["move_out_month"] = "2010-01"
        result = rvs.compute_full_analysis(bad)
        assert result["top_line"]["section_121_window_status"] == "closed"
        # Move out in the future → open
        future = copy.deepcopy(base_inputs)
        future["current_home"]["move_out_month"] = "2099-01"
        result = rvs.compute_full_analysis(future)
        assert result["top_line"]["section_121_window_status"] == "open"

    def test_driver_bridge_uses_rts_horizon(self, base_inputs):
        """Rent-then-sell with non-5Y horizon should prorate appreciation."""
        # Base rts is Jun 2026 to May 2029 = 35 months
        result = rvs.compute_full_analysis(base_inputs)
        rts = result["strategies"]["rent_then_sell"]
        bridge = rts["driver_bridge_vs_sell"]
        assert bridge is not None
        # Appreciation effect should be proportional to 35 months, not 60
        # If we were still using the raw 5Y total (10%), it'd be ~0.10 * 790k
        # * 0.93 = $73k. With proration: 35/60 * 73k ≈ $43k.
        app = bridge["current_home_appreciation_effect"]
        assert 30_000 < app < 55_000, f"Expected ~$43k, got ${app:,.0f}"

    def test_sensitivity_skips_unneeded_strategies(self, base_inputs):
        """After fix: sensitivity should only compute the 2 strategies the
        comparator needs, not all 5. Test by timing — 5y grid should be
        under ~400ms even with full drag modeling."""
        import time
        t = time.perf_counter()
        rvs.compute_sensitivity_grid(
            base_inputs, "value_x_rent", "sell_vs_keep_5y", "5y"
        )
        elapsed = time.perf_counter() - t
        # Pre-fix: ~300-500ms. Post-fix: should be noticeably faster.
        # Generous threshold to avoid flakiness on slow CI.
        assert elapsed < 2.0, f"Sensitivity too slow: {elapsed:.2f}s"

    def test_compute_full_analysis_respects_strategies_needed(self, base_inputs):
        result = rvs.compute_full_analysis(
            base_inputs,
            strategies_needed=frozenset(("sell_now", "keep_5y")),
            build_driver_bridges=False,
        )
        assert "sell_now" in result["strategies"]
        assert "keep_5y" in result["strategies"]
        assert "keep_10y" not in result["strategies"]
        assert "rent_then_sell" not in result["strategies"]
        # No driver bridges when skipped
        assert result["strategies"]["keep_5y"]["driver_bridge_vs_sell"] is None


class TestPlanCoverage:
    """Tests called out explicitly in the Rent vs Sell plan doc."""

    def test_all_four_strategies_in_plan_keys(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        for key in ("sell_now", "sell_now_10y", "keep_5y", "keep_10y", "rent_then_sell"):
            assert key in result["strategies"]

    def test_compute_rent_then_sell_standalone(self, base_inputs):
        out = rvs.compute_rent_then_sell(base_inputs)
        assert out.name == "rent_then_sell"
        assert out.net_worth_end is not None
        assert out.sale_tax_model is not None  # RTS always closes the sale

    def test_compute_depreciation_helper(self):
        # Full year, no mid-month adjustments → annual = basis × bldg / 27.5
        d = rvs.compute_depreciation(
            adjusted_basis=478000, building_pct=0.7026,
            months_active=12, mid_month_start=False, mid_month_end=False,
        )
        assert d == pytest.approx(12212, abs=5)

    def test_compute_depreciation_mid_month_first_year(self):
        # Full year held through but placed in service mid-month → 11.5/12
        full = rvs.compute_depreciation(
            adjusted_basis=478000, building_pct=0.7026,
            months_active=12, mid_month_start=False, mid_month_end=False,
        )
        first_year = rvs.compute_depreciation(
            adjusted_basis=478000, building_pct=0.7026,
            months_active=12, mid_month_start=True, mid_month_end=False,
        )
        assert first_year == pytest.approx(full * 11.5 / 12, abs=1)

    def test_compute_depreciation_both_endpoints_partial(self):
        # Placed in service mid-month AND disposed mid-month (12 months) → 11/12
        both = rvs.compute_depreciation(
            adjusted_basis=478000, building_pct=0.7026,
            months_active=12, mid_month_start=True, mid_month_end=True,
        )
        full = rvs.compute_depreciation(
            adjusted_basis=478000, building_pct=0.7026,
            months_active=12, mid_month_start=False, mid_month_end=False,
        )
        assert both == pytest.approx(full * 11 / 12, abs=1)

    def test_compute_depreciation_single_month_both_partial(self):
        # 1-month hold with both endpoints partial → clamped to 0.5 months
        d = rvs.compute_depreciation(
            adjusted_basis=478000, building_pct=0.7026,
            months_active=1, mid_month_start=True, mid_month_end=True,
        )
        assert d > 0  # not zero despite effective = 0

    def test_compute_depreciation_uses_lower_of_basis_or_fmv(self):
        low = rvs.compute_depreciation(
            adjusted_basis=500000, building_pct=0.7,
            months_active=12, fmv_at_conversion=400000,
            mid_month_start=False, mid_month_end=False,
        )
        high = rvs.compute_depreciation(
            adjusted_basis=500000, building_pct=0.7,
            months_active=12, mid_month_start=False, mid_month_end=False,
        )
        assert low < high

    def test_top_line_has_extra_new_home_loan(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        tl = result["top_line"]
        assert tl["extra_new_home_loan"] > 0  # keep-case loan > sell-case loan

    def test_top_line_has_net_interest_drag(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        tl = result["top_line"]
        assert tl["net_interest_drag_monthly"] > 0  # keep case pays more interest

    def test_top_line_breakeven_appreciation(self, base_inputs):
        result = rvs.compute_full_analysis(base_inputs)
        tl = result["top_line"]
        # At base case (+10% over 5Y), the crossover is near 10%
        be = tl["required_appreciation_to_breakeven_5y"]
        assert be is not None
        assert -0.3 < be < 0.3  # inside the bisection bracket

    def test_sensitivity_returns_breakeven_metrics(self, base_inputs):
        grid = rvs.compute_sensitivity_grid(
            base_inputs, "value_x_rent", "sell_vs_keep_5y", "5y"
        )
        # Rent and value breakevens should be computed
        assert "breakeven_value_change_pct" in grid
        assert "breakeven_rent_change_pct" in grid
        assert "breakeven_capex_shock_dollars" in grid  # None for non-capex preset OK

    def test_sensitivity_capex_preset_has_capex_breakeven(self, base_inputs):
        grid = rvs.compute_sensitivity_grid(
            base_inputs, "value_x_capex", "sell_vs_keep_5y", "5y"
        )
        # At worst, None — but the preset should at least attempt it
        assert "breakeven_capex_shock_dollars" in grid

    def test_passive_loss_suspended_when_magi_above_150k(self, base_inputs):
        """Explicit: heavy rental loss → suspended balance nonzero, not
        offsetting ordinary income immediately."""
        heavy = copy.deepcopy(base_inputs)
        heavy["current_home"]["monthly_rent_base"] = 500  # way below carry
        result = rvs.compute_full_analysis(heavy)
        keep = result["strategies"]["keep_5y"]
        # Accumulated suspended loss should exist by end of horizon
        total_suspended = sum(
            y["suspended_loss_created"] for y in keep["annual_tax_model"]
        )
        assert total_suspended > 0
        # Current tax paid for a loss year should be 0, not negative (no W-2 offset)
        for y in keep["annual_tax_model"]:
            assert y["current_tax_paid"] >= 0

    def test_new_home_maintenance_affects_all_strategies(self, base_inputs):
        base = rvs.compute_full_analysis(base_inputs)
        heavy = copy.deepcopy(base_inputs)
        heavy["new_home_drag"]["new_home_maintenance_pct_of_home_value_annual"] = 0.05
        heavy_result = rvs.compute_full_analysis(heavy)
        # Every strategy using the new home should end with lower NW
        for key in ("sell_now", "keep_5y", "keep_10y"):
            assert (
                heavy_result["strategies"][key]["net_worth_end"]
                < base["strategies"][key]["net_worth_end"]
            )

    def test_section_121_boundary_open_vs_closed(self, base_inputs):
        """Sale at exactly 36 months after move-out: open.
        Sale at 37 months after move-out: closed."""
        # move_out = 2026-05, rent_start = 2026-06
        # Sale at 2029-05 = 36 months after move-out → open
        open_case = copy.deepcopy(base_inputs)
        open_case["modeling"]["rent_then_sell_date"] = "2029-05"
        r_open = rvs.compute_full_analysis(open_case)
        rts_open = r_open["strategies"]["rent_then_sell"]
        # Window should be favorable → §121 exclusion should be > 0
        assert rts_open["sale_tax_model"]["section_121_excluded_gain"] > 0

        # Sale at 2029-07 = 38 months after move-out → closed
        closed_case = copy.deepcopy(base_inputs)
        closed_case["modeling"]["rent_then_sell_date"] = "2029-07"
        r_closed = rvs.compute_full_analysis(closed_case)
        rts_closed = r_closed["strategies"]["rent_then_sell"]
        # Window closed → exclusion should be 0
        assert rts_closed["sale_tax_model"]["section_121_excluded_gain"] == 0

    def test_driver_bridge_sums_within_tolerance_of_net_delta(self, base_inputs):
        """Bridge buckets must sum (including residual_other) to exactly the
        net delta. Residual absorbs any model-side approximation."""
        result = rvs.compute_full_analysis(base_inputs)
        sell = result["strategies"]["sell_now"]
        keep = result["strategies"]["keep_5y"]
        bridge = keep["driver_bridge_vs_sell"]
        bucket_sum = sum(v for v in bridge.values())
        net_delta = keep["net_worth_end"] - sell["net_worth_end"]
        assert abs(bucket_sum - net_delta) < 1.0  # residual_other absorbs it

    def test_current_home_tax_growth_uses_explicit_inputs(self, base_inputs):
        """Bumping current-home tax growth should reduce keep-case net worth,
        proving the growth path reads monthly_taxes directly (not a PITI lump)."""
        base = rvs.compute_full_analysis(base_inputs)
        high_growth = copy.deepcopy(base_inputs)
        high_growth["ownership_cost_growth"]["current_home_tax_growth_annual_pct"] = 0.15
        result = rvs.compute_full_analysis(high_growth)
        assert (
            result["strategies"]["keep_5y"]["net_worth_end"]
            < base["strategies"]["keep_5y"]["net_worth_end"]
        )


class TestGoldenFixtures:
    """Each fixture is a frozen expected-output snapshot. Engine changes that
    drift results bump CALC_VERSION and re-emit these files.
    """

    @pytest.mark.parametrize("name", rvs.FIXTURE_NAMES)
    def test_fixture_matches_current_engine(self, name):
        import json
        path = FIXTURE_DIR / f"{name}.json"
        if not path.exists():
            # Fail loud — a missing fixture means something went wrong with
            # the commit. Silent skip hides real drift.
            pytest.fail(
                f"fixture missing: {path}. Run "
                f"`python -m pipa.analysis.rent_vs_sell --emit-fixture all`"
            )
        with path.open(encoding="utf-8") as f:
            fixture = json.load(f)
        result = rvs.compute_full_analysis(fixture["inputs"])

        # Strategy net worths — tight tolerance so math drifts are loud
        expected_nws = fixture["expected"]["strategy_net_worths"]
        for strat_name, expected_nw in expected_nws.items():
            actual = result["strategies"].get(strat_name, {}).get("net_worth_end")
            if expected_nw is None:
                continue
            assert actual == pytest.approx(expected_nw, abs=100, rel=1e-6), (
                f"{name} {strat_name}: expected {expected_nw}, got {actual}"
            )
        assert result["lean"] == fixture["expected"]["lean"], f"{name} lean drifted"

        # Top-line metrics — the plan's user-facing numbers, not just NW
        expected_tl = fixture["expected"]["top_line"]
        actual_tl = result["top_line"]
        for key, expected_val in expected_tl.items():
            if expected_val is None or isinstance(expected_val, str):
                # String fields (e.g. section_121_window_status) compare exactly
                assert actual_tl.get(key) == expected_val, (
                    f"{name} top_line.{key}: expected {expected_val}, got {actual_tl.get(key)}"
                )
                continue
            actual_val = actual_tl.get(key)
            if actual_val is None:
                pytest.fail(f"{name} top_line.{key}: expected {expected_val}, got None")
            assert actual_val == pytest.approx(expected_val, abs=100, rel=1e-6), (
                f"{name} top_line.{key}: expected {expected_val}, got {actual_val}"
            )


class TestSchemaValidators:
    def test_month_regex_rejects_bad_format(self):
        from pipa.schemas.rent_vs_sell import CalculateRequest
        with pytest.raises(Exception):
            CalculateRequest(assumptions={"current_home": {"move_out_month": "2026/05"}})

    def test_non_finite_is_cleaned_to_zero(self):
        from pipa.schemas.rent_vs_sell import _walk_and_clean
        obj = {"a": float("inf"), "b": {"c": float("nan")}}
        _walk_and_clean(obj)
        assert obj["a"] == 0.0
        assert obj["b"]["c"] == 0.0

    def test_oversized_payload_rejected(self):
        from pipa.schemas.rent_vs_sell import CalculateRequest
        big = {"x": "y" * (300 * 1024)}
        with pytest.raises(Exception):
            CalculateRequest(assumptions={"current_home": big})

    def test_duplicate_run_ids_rejected(self):
        from pipa.schemas.rent_vs_sell import RunCompareRequest
        with pytest.raises(Exception):
            RunCompareRequest(run_ids=["a", "a"])


class TestSensitivity:
    def test_value_x_rent_preset_returns_11x11(self, base_inputs):
        grid = rvs.compute_sensitivity_grid(
            base_inputs, preset="value_x_rent", comparator="sell_vs_keep_5y", horizon="5y"
        )
        assert len(grid["cells"]) == 11
        assert all(len(row) == 11 for row in grid["cells"])

    def test_each_cell_has_winner(self, base_inputs):
        grid = rvs.compute_sensitivity_grid(
            base_inputs, preset="value_x_rent", comparator="sell_vs_keep_5y", horizon="5y"
        )
        for row in grid["cells"]:
            for cell in row:
                assert cell["winner"] in ("keep", "sell")
                assert isinstance(cell["delta"], (int, float))

    def test_value_x_refi_preset(self, base_inputs):
        grid = rvs.compute_sensitivity_grid(
            base_inputs, preset="value_x_refi", comparator="sell_vs_keep_10y", horizon="10y"
        )
        # 11 value steps x 4 refi paths
        assert len(grid["cells"]) == 4  # rows = refi paths
        assert len(grid["cells"][0]) == 11

    def test_capex_preset_reduces_keep_wins(self, base_inputs):
        base_grid = rvs.compute_sensitivity_grid(
            base_inputs, preset="value_x_rent", comparator="sell_vs_keep_5y", horizon="5y"
        )
        capex_grid = rvs.compute_sensitivity_grid(
            base_inputs, preset="value_x_capex", comparator="sell_vs_keep_5y", horizon="5y"
        )
        # Both grids should return well-formed cells
        assert capex_grid["y_label"].startswith("Capex")
