"""Smoke tests for all analysis engines.

Each test verifies that the function runs without error and returns
expected types/keys.  These are not exhaustive correctness tests —
they ensure the API contract holds and nothing blows up with
representative inputs.
"""

import pytest

from pipa.analysis.tax import run_tax_analysis
from pipa.analysis.investment import run_investment_analysis
from pipa.analysis.condition import score_property_condition, calculate_capex_forecast
from pipa.analysis.offer import calculate_max_bid, analyze_appraisal_gap
from pipa.analysis.stress_testing import run_stress_tests
from pipa.analysis.hoa import analyze_fee_trend, score_reserve_health, score_hoa_risk
from pipa.analysis.surrounding import analyze_surrounding


# ------------------------------------------------------------------
# Sample data shared across tests
# ------------------------------------------------------------------

SAMPLE_COMPONENTS = [
    {"type": "roof_asphalt_shingle", "install_year": 2010},
    {"type": "hvac_furnace", "install_year": 2015},
    {"type": "water_heater_tank", "install_year": 2018},
    {"type": "electrical_panel", "install_year": 2000},
    {"type": "windows", "install_year": 2005},
    {"type": "appliances", "install_year": 2019},
]

SAMPLE_FEE_HISTORY = [
    {"year": 2019, "monthly_fee": 250.0},
    {"year": 2020, "monthly_fee": 260.0},
    {"year": 2021, "monthly_fee": 275.0},
    {"year": 2022, "monthly_fee": 290.0},
    {"year": 2023, "monthly_fee": 310.0},
]


# ------------------------------------------------------------------
# Tax analysis
# ------------------------------------------------------------------


class TestTaxAnalysis:
    def test_tax_analysis_runs(self):
        result = run_tax_analysis(
            list_price=650_000,
            loan_amount=520_000,
            interest_rate=0.065,
            term_years=30,
            marginal_tax_rate=0.24,
            property_tax_rate=0.0115,
        )
        # Should return a TaxAnalysisResult with expected fields
        assert result.mortgage_interest_deduction is not None
        assert result.property_tax_deduction is not None
        assert result.total_annual_tax_benefit > 0
        assert result.effective_monthly_cost_reduction > 0
        # No current-home data provided, so strategy should be None
        assert result.first_home_strategy is None

    def test_tax_analysis_with_current_home(self):
        result = run_tax_analysis(
            list_price=650_000,
            loan_amount=520_000,
            interest_rate=0.065,
            current_home_purchase_price=350_000,
            current_home_estimated_value=500_000,
            current_home_remaining_mortgage=200_000,
            years_as_primary=8.0,
            estimated_monthly_rent=2_800,
            current_home_monthly_payment=1_800,
            current_home_annual_property_tax=4_200,
            current_home_annual_insurance=1_500,
        )
        assert result.first_home_strategy is not None
        assert result.first_home_strategy.recommendation in ("sell", "rent", "either")


# ------------------------------------------------------------------
# Investment analysis
# ------------------------------------------------------------------


class TestInvestmentAnalysis:
    def test_investment_analysis_runs(self):
        result = run_investment_analysis(
            list_price=650_000,
            hoa_monthly=150.0,
            appreciation_rate=0.03,
        )
        assert result.appreciation_rate == 0.03
        assert len(result.yearly_projections) == 30
        assert result.rent_vs_buy is not None
        assert result.rent_vs_buy.recommendation in ("buy", "rent", "marginal")
        assert result.net_worth_impact_5yr != 0.0 or result.net_worth_impact_10yr != 0.0

    def test_investment_with_explicit_loan(self):
        result = run_investment_analysis(
            list_price=500_000,
            loan_amount=400_000,
            interest_rate=0.07,
            term_years=30,
        )
        assert len(result.yearly_projections) == 30
        assert 5 in result.total_equity_at_year
        assert 10 in result.total_equity_at_year


# ------------------------------------------------------------------
# Condition scoring
# ------------------------------------------------------------------


class TestConditionScoring:
    def test_score_property_condition(self):
        score = score_property_condition(
            SAMPLE_COMPONENTS,
            current_year=2026,
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_new_home_scores_high(self):
        new_components = [
            {"type": "roof_asphalt_shingle", "install_year": 2025},
            {"type": "hvac_furnace", "install_year": 2025},
            {"type": "water_heater_tank", "install_year": 2025},
        ]
        score = score_property_condition(new_components, current_year=2026)
        assert score >= 90.0

    def test_old_home_scores_low(self):
        old_components = [
            {"type": "roof_asphalt_shingle", "install_year": 1990},
            {"type": "hvac_furnace", "install_year": 1995},
            {"type": "water_heater_tank", "install_year": 2000},
        ]
        score = score_property_condition(old_components, current_year=2026)
        assert score < 30.0

    def test_empty_components_returns_100(self):
        score = score_property_condition([], current_year=2026)
        assert score == 100.0


# ------------------------------------------------------------------
# CapEx forecast
# ------------------------------------------------------------------


class TestCapexForecast:
    def test_capex_forecast(self):
        forecast = calculate_capex_forecast(
            SAMPLE_COMPONENTS,
            current_year=2026,
            horizons=[1, 3, 5, 10],
        )
        assert isinstance(forecast, dict)
        assert set(forecast.keys()) == {1, 3, 5, 10}
        # Each horizon cost should be >= 0 and non-decreasing
        for h in [1, 3, 5, 10]:
            assert forecast[h] >= 0.0
        assert forecast[10] >= forecast[5] >= forecast[3] >= forecast[1]

    def test_new_home_no_near_term_capex(self):
        new_components = [
            {"type": "roof_asphalt_shingle", "install_year": 2025},
            {"type": "hvac_furnace", "install_year": 2025},
        ]
        forecast = calculate_capex_forecast(
            new_components, current_year=2026, horizons=[1, 3, 5]
        )
        assert forecast[1] == 0.0
        assert forecast[3] == 0.0


# ------------------------------------------------------------------
# Offer analysis
# ------------------------------------------------------------------


class TestOfferMaxBid:
    def test_calculate_max_bid(self):
        result = calculate_max_bid(
            appraisal_value=600_000,
            max_monthly_payment=4_500,
            max_cash_at_closing=150_000,
            interest_rate=0.065,
            term_years=30,
            down_payment_pct=0.20,
        )
        assert isinstance(result, dict)
        assert "max_price" in result
        assert "limiting_factor" in result
        assert "price_by_constraint" in result
        assert result["limiting_factor"] in ("payment", "cash", "appraisal")
        assert result["max_price"] > 0


class TestAppraisalGap:
    def test_analyze_appraisal_gap_no_gap(self):
        result = analyze_appraisal_gap(
            offer_price=580_000,
            estimated_appraisal=600_000,
            cash_reserves=100_000,
        )
        assert result["gap_amount"] == 0.0
        assert result["risk_level"] == "none"
        assert result["can_cover"] is True

    def test_analyze_appraisal_gap_with_gap(self):
        result = analyze_appraisal_gap(
            offer_price=650_000,
            estimated_appraisal=600_000,
            cash_reserves=30_000,
        )
        assert result["gap_amount"] == 50_000.0
        assert result["risk_level"] == "high"
        assert result["can_cover"] is False

    def test_analyze_appraisal_gap_small_gap(self):
        result = analyze_appraisal_gap(
            offer_price=610_000,
            estimated_appraisal=600_000,
            cash_reserves=50_000,
        )
        assert result["gap_amount"] == 10_000.0
        assert result["risk_level"] == "low"
        assert result["can_cover"] is True
        assert "gap_pct" in result


# ------------------------------------------------------------------
# Stress testing
# ------------------------------------------------------------------


class TestStressTests:
    def test_run_stress_tests(self):
        result = run_stress_tests(
            list_price=650_000,
            loan_amount=520_000,
            interest_rate=0.065,
            term_years=30,
            annual_insurance=2_400,
        )
        assert isinstance(result, dict)
        assert "rate_shock" in result
        assert "insurance_inflation" in result
        assert "downside_sale" in result

        # Rate shock has entries per delta
        rate_shock = result["rate_shock"]
        assert len(rate_shock) >= 1
        for delta, data in rate_shock.items():
            assert "new_payment" in data
            assert "payment_increase" in data
            assert data["payment_increase"] >= 0

        # Downside sale has entries per depreciation pct
        downside = result["downside_sale"]
        assert len(downside) >= 1
        for pct, data in downside.items():
            assert "sale_price" in data
            assert "net_proceeds" in data
            assert "underwater" in data

    def test_stress_tests_custom_params(self):
        result = run_stress_tests(
            list_price=500_000,
            loan_amount=400_000,
            interest_rate=0.07,
            rate_deltas=[0.01, 0.02],
            depreciation_pcts=[0.10, 0.30],
        )
        assert len(result["rate_shock"]) == 2
        assert len(result["downside_sale"]) == 2


# ------------------------------------------------------------------
# HOA risk
# ------------------------------------------------------------------


class TestHoaRisk:
    def test_score_hoa_risk_low(self):
        fee_trend = analyze_fee_trend(SAMPLE_FEE_HISTORY)
        reserve_health = score_reserve_health(
            reserve_balance=500_000,
            annual_expenses=400_000,
        )
        risk = score_hoa_risk(
            fee_trend=fee_trend,
            reserve_health=reserve_health,
        )
        assert isinstance(risk, int)
        assert 1 <= risk <= 10
        # Healthy reserves + moderate fee increase = low risk
        assert risk <= 5

    def test_score_hoa_risk_high(self):
        bad_trend = {
            "annual_increase_rate": 0.12,
            "projected_5yr_fee": 600.0,
            "total_increase_pct": 0.80,
            "years_of_data": 5,
        }
        risk = score_hoa_risk(
            fee_trend=bad_trend,
            reserve_health=15.0,  # critically low reserves
            special_assessments=[
                {"year": 2023, "amount": 5_000},
                {"year": 2024, "amount": 8_000},
            ],
            litigation_flags=["Pending lawsuit against developer"],
        )
        assert risk >= 7

    def test_score_hoa_risk_returns_int_in_range(self):
        fee_trend = {"annual_increase_rate": 0.0}
        risk = score_hoa_risk(fee_trend=fee_trend, reserve_health=100.0)
        assert isinstance(risk, int)
        assert 1 <= risk <= 10


# ------------------------------------------------------------------
# Surrounding / neighborhood analysis
# ------------------------------------------------------------------


class TestSurroundingAnalysis:
    def test_analyze_surrounding(self):
        nearby_properties = [
            {"address": "101 Oak St", "owner_occupied": True},
            {"address": "102 Oak St", "owner_occupied": True},
            {"address": "103 Oak St", "owner_occupied": False},
            {"address": "104 Oak St", "owner_occupied": True},
            {"address": "105 Oak St", "owner_occupied": False},
            {"address": "106 Oak St", "owner_occupied": True},
            {"address": "107 Oak St", "owner_occupied": True},
            {"address": "108 Oak St", "owner_occupied": True},
            {"address": "109 Oak St", "owner_occupied": True},
            {"address": "110 Oak St", "owner_occupied": True},
        ]
        nearby_sales = [
            {"address": "101 Oak St", "sale_date": "2024-06-15"},
            {"address": "103 Oak St", "sale_date": "2025-01-10"},
            {"address": "105 Oak St", "sale_date": "2025-03-01"},
            {"address": "105 Oak St", "sale_date": "2025-11-01"},  # flip
        ]

        result = analyze_surrounding(
            nearby_properties=nearby_properties,
            nearby_sales=nearby_sales,
        )
        assert isinstance(result, dict)
        assert "investor_share" in result
        assert "turnover_rate" in result
        assert "flip_count" in result
        assert "stability_score" in result
        assert "total_nearby" in result

        assert 0.0 <= result["investor_share"] <= 1.0
        assert 0.0 <= result["stability_score"] <= 100.0
        assert result["total_nearby"] == 10

    def test_analyze_surrounding_empty(self):
        result = analyze_surrounding(
            nearby_properties=[],
            nearby_sales=[],
        )
        assert result["investor_share"] == 0.0
        assert result["total_nearby"] == 0
        assert result["stability_score"] >= 0.0

    def test_high_investor_share_lowers_stability(self):
        # All investor-owned — investor component is 0/33.3 but
        # turnover and flip components are still full (no sales = stable).
        # Net effect: score drops relative to an all-owner-occupied set.
        props = [{"address": f"{i} St", "owner_occupied": False} for i in range(10)]
        result = analyze_surrounding(
            nearby_properties=props,
            nearby_sales=[],
        )
        assert result["investor_share"] == 1.0
        # Compare against a baseline with all owner-occupied
        baseline = analyze_surrounding(
            nearby_properties=[{"address": f"{i} St", "owner_occupied": True} for i in range(10)],
            nearby_sales=[],
        )
        assert result["stability_score"] < baseline["stability_score"]
