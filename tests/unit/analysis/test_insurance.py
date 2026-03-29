"""Tests for the insurance analysis engine."""

from __future__ import annotations

import pytest

from pipa.analysis.insurance import (
    assess_disaster_risk,
    estimate_flood_insurance,
    estimate_homeowners_insurance,
    run_insurance_analysis,
)


class TestHomeownersPremium:
    def test_default_rate(self):
        """Default rate should produce a reasonable premium."""
        result = estimate_homeowners_insurance(600_000)
        assert result.annual_premium == pytest.approx(600_000 * 0.0035, rel=1e-4)
        assert result.monthly_premium == pytest.approx(result.annual_premium / 12.0, abs=0.01)
        assert result.coverage_amount == 600_000

    def test_custom_rate(self):
        """Custom rate should override default."""
        result = estimate_homeowners_insurance(500_000, rate=0.005)
        assert result.annual_premium == pytest.approx(2_500.0, rel=1e-4)

    def test_low_value_home(self):
        """Low-value home should have proportionally lower premium."""
        low = estimate_homeowners_insurance(200_000)
        high = estimate_homeowners_insurance(800_000)
        assert low.annual_premium < high.annual_premium

    def test_monthly_is_annual_divided_by_12(self):
        result = estimate_homeowners_insurance(450_000)
        assert result.monthly_premium == pytest.approx(result.annual_premium / 12.0, abs=0.01)


class TestDisasterRiskVirginia:
    def test_virginia_low_risk(self):
        """Virginia should have a low overall disaster risk score."""
        risk = assess_disaster_risk("VA")
        assert risk.earthquake_risk == "low"
        assert risk.wildfire_risk == "low"
        assert risk.tornado_risk == "low"
        assert risk.overall_risk_score <= 3

    def test_florida_high_risk(self):
        """Florida should have elevated hurricane risk."""
        risk = assess_disaster_risk("FL")
        assert risk.hurricane_risk == "high"
        assert risk.overall_risk_score >= 3

    def test_california_earthquake_risk(self):
        """California should have high earthquake and wildfire risk."""
        risk = assess_disaster_risk("CA")
        assert risk.earthquake_risk == "high"
        assert risk.wildfire_risk == "high"
        assert risk.overall_risk_score >= 5

    def test_unknown_state_moderate(self):
        """Unknown state should get a default moderate risk."""
        risk = assess_disaster_risk("ZZ")
        # Should not crash; returns a default
        assert 1 <= risk.overall_risk_score <= 10

    def test_case_insensitive(self):
        """State lookup should be case-insensitive."""
        risk = assess_disaster_risk("va")
        assert risk.earthquake_risk == "low"


class TestFloodInsurance:
    def test_high_risk_zone_required(self):
        """High-risk flood zone (AE) should require flood insurance."""
        result = estimate_flood_insurance("AE")
        assert result is not None
        assert result.required is True
        assert result.annual_premium > 0

    def test_low_risk_zone_not_required(self):
        """Low-risk zone (X) with no declarations should not require insurance."""
        result = estimate_flood_insurance("X", flood_declarations=0)
        # Zone X with 0 declarations: no insurance needed
        assert result is None or result.required is False

    def test_coastal_zone_high_premium(self):
        """Coastal high-hazard zone (VE) should have the highest premium."""
        ve = estimate_flood_insurance("VE")
        ae = estimate_flood_insurance("AE")
        assert ve is not None and ae is not None
        assert ve.annual_premium >= ae.annual_premium

    def test_none_zone_no_declarations(self):
        """No zone and no declarations should return None."""
        result = estimate_flood_insurance(None, flood_declarations=0)
        assert result is None

    def test_declarations_infer_risk(self):
        """Multiple flood declarations without a zone should infer coverage."""
        result = estimate_flood_insurance(None, flood_declarations=3)
        assert result is not None
        assert result.required is True
        assert result.annual_premium > 0


class TestFullInsuranceAnalysis:
    def test_basic_virginia_analysis(self):
        """Full analysis for a typical Virginia property."""
        result = run_insurance_analysis(
            home_value=600_000,
            state="VA",
        )
        assert result.homeowners.annual_premium > 0
        assert result.disaster_risk.overall_risk_score <= 3
        assert result.total_annual_insurance > 0
        assert result.total_monthly_insurance > 0
        assert result.total_monthly_insurance == pytest.approx(
            result.total_annual_insurance / 12.0, abs=0.01
        )

    def test_flood_zone_increases_total(self):
        """Adding a high-risk flood zone should increase total insurance cost."""
        without_flood = run_insurance_analysis(home_value=600_000, state="VA")
        with_flood = run_insurance_analysis(
            home_value=600_000, state="VA", flood_zone="AE"
        )
        assert with_flood.total_annual_insurance > without_flood.total_annual_insurance
        assert with_flood.flood is not None
        assert with_flood.flood.required is True
