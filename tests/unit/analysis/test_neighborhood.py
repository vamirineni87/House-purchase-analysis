"""Tests for the neighborhood analysis engine."""

from __future__ import annotations

import pytest

from pipa.analysis.neighborhood import (
    compute_composite_score,
    crime_rate_to_safety,
    run_neighborhood_analysis,
)
from pipa.schemas.neighborhood import (
    CrimeStats,
    Demographics,
    FloodRisk,
    SchoolRating,
    WalkabilityScores,
)


class TestCompositeScoreCalculation:
    def test_all_data_present(self):
        """Composite score should be a weighted average when all data is available."""
        schools = [
            SchoolRating(name="Great ES", type="elementary", rating=9),
            SchoolRating(name="Good MS", type="middle", rating=7),
        ]
        crime = CrimeStats(overall_safety_score=8.0)
        walk = WalkabilityScores(walk_score=72)
        flood = FloodRisk(risk_level="low")
        demo = Demographics(median_household_income=90_000)

        score, completeness = compute_composite_score(schools, crime, walk, flood, demo)

        assert score is not None
        assert 0.0 <= score <= 100.0
        assert completeness == 1.0  # all 5 categories present

    def test_high_quality_neighborhood(self):
        """Excellent data should produce a high composite score."""
        schools = [SchoolRating(name="Top School", type="elementary", rating=10)]
        crime = CrimeStats(overall_safety_score=10.0)
        walk = WalkabilityScores(walk_score=95)
        flood = FloodRisk(risk_level="low")
        demo = Demographics(median_household_income=120_000)

        score, _ = compute_composite_score(schools, crime, walk, flood, demo)

        assert score is not None
        assert score >= 85.0

    def test_low_quality_neighborhood(self):
        """Poor data should produce a low composite score."""
        schools = [SchoolRating(name="Struggling School", type="elementary", rating=2)]
        crime = CrimeStats(overall_safety_score=2.0)
        walk = WalkabilityScores(walk_score=10)
        flood = FloodRisk(risk_level="high")
        demo = Demographics(median_household_income=25_000)

        score, _ = compute_composite_score(schools, crime, walk, flood, demo)

        assert score is not None
        assert score <= 35.0

    def test_no_data_returns_none(self):
        """No data should return None composite and 0 completeness."""
        score, completeness = compute_composite_score([], None, None, None, None)
        assert score is None
        assert completeness == 0.0


class TestCrimeToSafetyConversion:
    def test_zero_violent_crime(self):
        """Zero violent crime should produce a high safety score."""
        safety = crime_rate_to_safety(0.0)
        assert safety is not None
        assert safety == 10.0

    def test_high_violent_crime(self):
        """Very high violent crime should produce a low safety score."""
        safety = crime_rate_to_safety(800.0)
        assert safety is not None
        assert safety <= 2.0

    def test_national_average_crime(self):
        """National average (~380) should produce a moderate score."""
        safety = crime_rate_to_safety(380.0)
        assert safety is not None
        assert 4.0 <= safety <= 8.0

    def test_none_returns_none(self):
        """None violent rate should return None."""
        assert crime_rate_to_safety(None) is None

    def test_property_crime_nudges_score(self):
        """Property crime rate should adjust the base score."""
        base = crime_rate_to_safety(200.0, property_rate=None)
        with_low_prop = crime_rate_to_safety(200.0, property_rate=500.0)
        with_high_prop = crime_rate_to_safety(200.0, property_rate=4000.0)

        assert base is not None
        assert with_low_prop is not None
        assert with_high_prop is not None
        # Low property crime should boost, high should penalise
        assert with_low_prop >= base
        assert with_high_prop <= base


class TestPartialDataScoring:
    def test_schools_only(self):
        """With only schools data, score should still be computed."""
        schools = [SchoolRating(name="Good ES", type="elementary", rating=8)]
        score, completeness = compute_composite_score(schools, None, None, None, None)

        assert score is not None
        assert 0.0 < score <= 100.0
        assert completeness == 0.2  # 1 out of 5 categories

    def test_crime_only(self):
        """With only crime data, score should reflect safety."""
        crime = CrimeStats(overall_safety_score=7.5)
        score, completeness = compute_composite_score([], crime, None, None, None)

        assert score is not None
        assert completeness == 0.2

    def test_two_sources(self):
        """With two data sources, completeness should be 0.4."""
        schools = [SchoolRating(name="OK School", type="elementary", rating=6)]
        walk = WalkabilityScores(walk_score=55)
        score, completeness = compute_composite_score(schools, None, walk, None, None)

        assert score is not None
        assert completeness == 0.4

    def test_unrated_schools_ignored(self):
        """Schools without ratings should not count as data."""
        schools = [SchoolRating(name="Unrated", type="elementary", rating=None)]
        score, completeness = compute_composite_score(schools, None, None, None, None)

        # No usable school data
        assert score is None
        assert completeness == 0.0

    def test_run_neighborhood_analysis_auto_computes_safety(self):
        """When crime rates are given but no safety score, it should be auto-computed."""
        result = run_neighborhood_analysis(
            crime_stats=CrimeStats(violent_crime_rate=200.0, property_crime_rate=1000.0),
        )
        # Safety score should have been populated
        assert result.crime is not None
        assert result.crime.overall_safety_score is not None
        assert result.crime.overall_safety_score > 0
        # Composite should exist (one data source)
        assert result.composite_score is not None
