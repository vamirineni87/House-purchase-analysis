"""Data models for the Home Purchase Analysis tool."""

from hpa.models.appraisal import AppraisalResult, ComparableSale
from hpa.models.financial import (
    AmortizationEntry,
    ClosingCosts,
    FinancialAnalysisResult,
    LoanScenario,
    MonthlyPaymentBreakdown,
)
from hpa.models.insurance import (
    FloodInsuranceEstimate,
    HomeownersInsuranceEstimate,
    InsuranceAnalysisResult,
    NaturalDisasterRisk,
)
from hpa.models.investment import (
    InvestmentAnalysisResult,
    RentVsBuyComparison,
    YearlyProjection,
)
from hpa.models.neighborhood import (
    CrimeStats,
    Demographics,
    FloodRisk,
    NeighborhoodAnalysisResult,
    SchoolRating,
    WalkabilityScores,
)
from hpa.models.property import Address, PropertyDetails
from hpa.models.tax import (
    CapitalGainsAnalysis,
    FirstHomeStrategy,
    MortgageInterestDeduction,
    PropertyTaxDeduction,
    RentalIncomeAnalysis,
    TaxAnalysisResult,
)

__all__ = [
    # property
    "Address",
    "PropertyDetails",
    # financial
    "LoanScenario",
    "MonthlyPaymentBreakdown",
    "AmortizationEntry",
    "ClosingCosts",
    "FinancialAnalysisResult",
    # appraisal
    "ComparableSale",
    "AppraisalResult",
    # neighborhood
    "SchoolRating",
    "CrimeStats",
    "WalkabilityScores",
    "FloodRisk",
    "Demographics",
    "NeighborhoodAnalysisResult",
    # investment
    "YearlyProjection",
    "RentVsBuyComparison",
    "InvestmentAnalysisResult",
    # tax
    "CapitalGainsAnalysis",
    "RentalIncomeAnalysis",
    "FirstHomeStrategy",
    "MortgageInterestDeduction",
    "PropertyTaxDeduction",
    "TaxAnalysisResult",
    # insurance
    "FloodInsuranceEstimate",
    "NaturalDisasterRisk",
    "HomeownersInsuranceEstimate",
    "InsuranceAnalysisResult",
]
