"""Tests for the appraisal analysis engine."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pipa.analysis.appraisal import (
    adjust_comparable,
    assess_value,
    determine_confidence,
    run_appraisal_analysis,
)
from pipa.schemas.appraisal import ComparableSale


def _make_comp(
    sale_price: float = 500_000,
    sqft: int = 2000,
    beds: int = 4,
    baths: float = 2.5,
    year_built: int = 2010,
    days_ago: int = 30,
) -> ComparableSale:
    """Helper to build a ComparableSale with a recent sale date."""
    return ComparableSale(
        address="123 Comp St",
        sale_price=sale_price,
        sale_date=date.today() - timedelta(days=days_ago),
        square_feet=sqft,
        bedrooms=beds,
        bathrooms=baths,
        year_built=year_built,
        price_per_sqft=sale_price / max(sqft, 1),
    )


class TestAdjustComparable:
    def test_adjust_identical_comp(self):
        """Identical subject and comp should have near-zero adjustments (except time)."""
        comp = _make_comp(sale_price=500_000, sqft=2000, beds=4, baths=2.5, year_built=2010, days_ago=0)
        adjusted = adjust_comparable(comp, subject_sqft=2000, subject_beds=4, subject_baths=2.5, subject_year_built=2010)
        # sqft, bed, bath, year adjustments should all be 0
        assert adjusted.adjustments["sqft"] == 0.0
        assert adjusted.adjustments["bedrooms"] == 0.0
        assert adjusted.adjustments["bathrooms"] == 0.0
        assert adjusted.adjustments["year_built"] == 0.0
        # Adjusted price should be close to original
        assert adjusted.adjusted_price == pytest.approx(500_000, rel=0.01)

    def test_adjust_larger_subject(self):
        """Subject larger than comp should increase adjusted price."""
        comp = _make_comp(sale_price=500_000, sqft=1800, beds=3, baths=2.0, year_built=2010, days_ago=0)
        adjusted = adjust_comparable(comp, subject_sqft=2000, subject_beds=4, subject_baths=2.5, subject_year_built=2010)
        # 200 sqft * $100 = $20,000 upward
        assert adjusted.adjustments["sqft"] == 20_000.0
        # 1 bedroom * $10,000 = $10,000 upward
        assert adjusted.adjustments["bedrooms"] == 10_000.0
        # 0.5 bathroom * $7,500 = $3,750 upward
        assert adjusted.adjustments["bathrooms"] == 3_750.0
        assert adjusted.adjusted_price > comp.sale_price

    def test_adjust_older_comp(self):
        """Older comp year-built should get a positive year adjustment."""
        comp = _make_comp(year_built=2000, days_ago=0)
        adjusted = adjust_comparable(comp, subject_sqft=2000, subject_beds=4, subject_baths=2.5, subject_year_built=2010)
        assert adjusted.adjustments["year_built"] == 10 * 2_000.0

    def test_time_adjustment_for_older_sale(self):
        """A comp sold months ago should get a positive time adjustment."""
        comp = _make_comp(days_ago=365)
        adjusted = adjust_comparable(comp, subject_sqft=2000, subject_beds=4, subject_baths=2.5, subject_year_built=2010)
        assert adjusted.adjustments["time"] > 0


class TestValueAssessment:
    def _make_adjusted_comps(self, prices: list[float], sqft: int = 2000) -> list[ComparableSale]:
        return [
            _make_comp(sale_price=p, sqft=sqft, days_ago=0).model_copy(
                update={"adjusted_price": p}
            )
            for p in prices
        ]

    def test_below_market(self):
        """List price well below median should be 'below_market'."""
        comps = self._make_adjusted_comps([500_000, 520_000, 480_000])
        # Median ppsf ~$250/sqft, so mid ~$500k. Price $400k is < 95% of mid.
        _, _, _, assessment = assess_value(comps, list_price=400_000, sqft=2000)
        assert assessment == "below_market"

    def test_at_market(self):
        """List price near median should be 'at_market'."""
        comps = self._make_adjusted_comps([500_000, 520_000, 480_000])
        _, mid, _, assessment = assess_value(comps, list_price=500_000, sqft=2000)
        assert assessment == "at_market"

    def test_above_market(self):
        """List price well above median should be 'above_market'."""
        comps = self._make_adjusted_comps([500_000, 520_000, 480_000])
        _, _, _, assessment = assess_value(comps, list_price=600_000, sqft=2000)
        assert assessment == "above_market"


class TestEmptyComps:
    def test_empty_comps_returns_heuristic(self):
        """With no comps, run_appraisal_analysis should return a heuristic result."""
        result = run_appraisal_analysis(
            list_price=500_000,
            sqft=2000,
            beds=4,
            baths=2.5,
        )
        assert result.comparables == []
        assert result.estimated_value_mid == 500_000
        assert result.estimated_value_low < result.estimated_value_mid
        assert result.estimated_value_high > result.estimated_value_mid
        assert result.value_assessment == "at_market"
        assert result.confidence == "low"

    def test_confidence_levels(self):
        """Confidence should scale with number of comps."""
        assert determine_confidence([]) == "low"
        assert determine_confidence([_make_comp()]) == "medium"
        assert determine_confidence([_make_comp()] * 3) == "medium"
        assert determine_confidence([_make_comp()] * 4) == "high"
        assert determine_confidence([_make_comp()] * 10) == "high"
