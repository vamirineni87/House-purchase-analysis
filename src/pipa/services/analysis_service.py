"""Analysis orchestration service.

Bridges the pure-function analysis modules with the database layer,
resolving property-specific parameters (county tax rate, components, etc.)
before delegating to the analysis functions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.analysis.condition import (
    calculate_capex_forecast,
    score_property_condition,
)
from pipa.analysis.financial import run_financial_analysis
from pipa.analysis.investment import run_investment_analysis
from pipa.analysis.offer import (
    analyze_appraisal_gap,
    calculate_max_bid,
    calculate_walk_away_price,
    model_escalation_clause,
)
from pipa.analysis.stress_testing import run_stress_tests
from pipa.analysis.tax import run_tax_analysis
from pipa.models.analysis_models import AnalysisRun
from pipa.models.component import ComponentSystem
from pipa.models.property import Property
from pipa.schemas.financial import FinancialAnalysisRequest, FinancialAnalysisResult
from pipa.schemas.investment import InvestmentAnalysisRequest, InvestmentAnalysisResult
from pipa.schemas.tax import TaxAnalysisRequest, TaxAnalysisResult

logger = logging.getLogger(__name__)

# Package version — used in AnalysisRun tracking
_CODE_VERSION = "0.1.0"


def _input_hash(data: dict) -> str:
    """SHA-256 hash of serialized input for change detection."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def _get_county_tax_rate(db: AsyncSession, property_id: str) -> float:
    """Resolve county-specific tax rate from property address."""
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses))
        .where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        return 0.012

    for addr in prop.addresses:
        if addr.is_current and addr.county:
            county = addr.county.lower()
            if county == "loudoun":
                return 0.00875
            elif county == "fairfax":
                return 0.0111
    return 0.012


async def _get_components(
    db: AsyncSession,
    property_id: str,
) -> list[dict]:
    """Load component systems for a property as plain dicts."""
    result = await db.execute(
        select(ComponentSystem).where(
            ComponentSystem.property_id == property_id
        )
    )
    components = result.scalars().all()
    return [
        {
            "type": c.component_type,
            "install_year": c.estimated_install_year or datetime.now().year,
            "cost_override": c.estimated_replacement_cost,
        }
        for c in components
    ]


class AnalysisService:
    """Orchestrates analysis runs, resolves property context, records results."""

    # ------------------------------------------------------------------
    # Financial
    # ------------------------------------------------------------------

    @staticmethod
    async def run_financial(
        db: AsyncSession,
        property_id: str,
        params: FinancialAnalysisRequest,
    ) -> FinancialAnalysisResult:
        """Run financial analysis for a property."""
        tax_rate = params.property_tax_rate
        if tax_rate is None:
            tax_rate = await _get_county_tax_rate(db, property_id)

        analysis = run_financial_analysis(
            list_price=params.list_price,
            hoa_monthly=params.hoa_monthly,
            down_payment_pcts=params.down_payment_pcts,
            term_years=params.term_years,
            rate_override=params.rate_override,
            property_tax_rate=tax_rate,
        )

        # Record the run
        run = AnalysisRun(
            property_id=property_id,
            analysis_type="financial",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(params.model_dump()),
            output_json=analysis.model_dump(),
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)

        return analysis

    # ------------------------------------------------------------------
    # Tax
    # ------------------------------------------------------------------

    @staticmethod
    async def run_tax(
        db: AsyncSession,
        property_id: str,
        params: TaxAnalysisRequest,
    ) -> TaxAnalysisResult:
        """Run tax analysis for a property."""
        tax_rate = await _get_county_tax_rate(db, property_id)

        analysis = run_tax_analysis(
            list_price=params.list_price,
            loan_amount=params.loan_amount,
            marginal_tax_rate=params.marginal_tax_rate,
            filing_status=params.filing_status,
            property_tax_rate=tax_rate,
            current_home_purchase_price=params.current_home_purchase_price,
            current_home_estimated_value=params.current_home_estimated_value,
            current_home_remaining_mortgage=params.current_home_remaining_mortgage,
            years_as_primary=params.years_as_primary,
            estimated_monthly_rent=params.estimated_monthly_rent,
        )

        run = AnalysisRun(
            property_id=property_id,
            analysis_type="tax",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(params.model_dump()),
            output_json=analysis.model_dump(),
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)

        return analysis

    # ------------------------------------------------------------------
    # Investment
    # ------------------------------------------------------------------

    @staticmethod
    async def run_investment(
        db: AsyncSession,
        property_id: str,
        params: InvestmentAnalysisRequest,
    ) -> InvestmentAnalysisResult:
        """Run investment analysis for a property."""
        analysis = run_investment_analysis(
            list_price=params.list_price,
            loan_amount=params.loan_amount,
            interest_rate=params.interest_rate,
            term_years=params.term_years,
            down_payment_pct=params.down_payment_pct,
            hoa_monthly=params.hoa_monthly,
            property_tax_rate=params.property_tax_rate,
            insurance_rate=params.insurance_rate,
            appreciation_rate=params.appreciation_rate,
            maintenance_rate=params.maintenance_rate,
            marginal_tax_rate=params.marginal_tax_rate,
            inflation_rate=params.inflation_rate,
        )

        run = AnalysisRun(
            property_id=property_id,
            analysis_type="investment",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(params.model_dump()),
            output_json=analysis.model_dump(),
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)

        return analysis

    # ------------------------------------------------------------------
    # Condition
    # ------------------------------------------------------------------

    @staticmethod
    async def run_condition(
        db: AsyncSession,
        property_id: str,
    ) -> dict:
        """Run condition analysis using stored component data."""
        components = await _get_components(db, property_id)

        if not components:
            return {
                "condition_score": 100.0,
                "capex_forecast": {},
                "components_analyzed": 0,
            }

        score = score_property_condition(components)
        forecast = calculate_capex_forecast(components)

        result = {
            "condition_score": score,
            "capex_forecast": forecast,
            "components_analyzed": len(components),
        }

        run = AnalysisRun(
            property_id=property_id,
            analysis_type="condition",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash({"components": components}),
            output_json=result,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)

        return result

    # ------------------------------------------------------------------
    # Offer strategy
    # ------------------------------------------------------------------

    @staticmethod
    async def run_offer(
        db: AsyncSession,
        property_id: str,
        params: dict,
    ) -> dict:
        """Run offer strategy analysis."""
        max_bid = calculate_max_bid(
            appraisal_value=params["appraisal_value"],
            max_monthly_payment=params["max_monthly_payment"],
            max_cash_at_closing=params["max_cash_at_closing"],
            interest_rate=params.get("interest_rate", 0.065),
            term_years=params.get("term_years", 30),
            down_payment_pct=params.get("down_payment_pct", 0.20),
            property_tax_rate=params.get("property_tax_rate", 0.012),
            insurance_rate=params.get("insurance_rate", 0.0035),
            hoa_monthly=params.get("hoa_monthly", 0.0),
            closing_cost_pct=params.get("closing_cost_pct", 0.03),
        )

        walk_away = calculate_walk_away_price(
            list_price=params.get("list_price", params["appraisal_value"]),
            inspection_cost_threshold=params.get("inspection_cost_threshold", 20_000.0),
        )

        escalation_outcomes: list[dict] = []
        if params.get("competing_bids"):
            escalation_outcomes = model_escalation_clause(
                base_price=params.get("escalation_base", max_bid["max_price"]),
                increment=params.get("escalation_increment", 5_000.0),
                cap=params.get("escalation_cap", max_bid["max_price"]),
                competing_bids=params["competing_bids"],
            )

        appraisal_gap: dict = {}
        offer_price = params.get("offer_price")
        if offer_price is not None:
            appraisal_gap = analyze_appraisal_gap(
                offer_price=offer_price,
                estimated_appraisal=params["appraisal_value"],
                cash_reserves=params.get("cash_reserves", 0.0),
            )

        result = {
            "max_bid": max_bid,
            "walk_away_price": walk_away,
            "escalation_outcomes": escalation_outcomes,
            "appraisal_gap": appraisal_gap,
        }

        run = AnalysisRun(
            property_id=property_id,
            analysis_type="offer",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(params),
            output_json=result,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)

        return result

    # ------------------------------------------------------------------
    # Stress testing
    # ------------------------------------------------------------------

    @staticmethod
    async def run_stress(
        db: AsyncSession,
        property_id: str,
        params: dict,
    ) -> dict:
        """Run stress test scenarios."""
        result = run_stress_tests(
            list_price=params["list_price"],
            loan_amount=params["loan_amount"],
            interest_rate=params.get("interest_rate", 0.065),
            term_years=params.get("term_years", 30),
            annual_insurance=params.get("annual_insurance", 0.0),
            rate_deltas=params.get("rate_deltas"),
            insurance_inflation_rates=params.get("insurance_inflation_rates"),
            insurance_projection_years=params.get("insurance_projection_years", 10),
            depreciation_pcts=params.get("depreciation_pcts"),
            downside_years_held=params.get("downside_years_held", 5),
            selling_costs_pct=params.get("selling_costs_pct", 0.08),
        )

        run = AnalysisRun(
            property_id=property_id,
            analysis_type="stress",
            ruleset_version="1.0.0",
            code_version=_CODE_VERSION,
            input_snapshot_hash=_input_hash(params),
            output_json=result,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(run)

        return result

    # ------------------------------------------------------------------
    # Run all
    # ------------------------------------------------------------------

    @staticmethod
    async def run_all(
        db: AsyncSession,
        property_id: str,
        params: dict,
    ) -> dict:
        """Run financial, tax, investment, and condition analyses."""
        tax_rate = params.get("property_tax_rate")
        if tax_rate is None:
            tax_rate = await _get_county_tax_rate(db, property_id)

        list_price = params["list_price"]
        down_pct = params.get("down_payment_pct", 0.20)
        term = params.get("term_years", 30)
        loan_amount = params.get("loan_amount") or round(list_price * (1 - down_pct), 2)

        # Financial
        financial_params = FinancialAnalysisRequest(
            list_price=list_price,
            hoa_monthly=params.get("hoa_monthly", 0.0),
            down_payment_pcts=[down_pct],
            term_years=[term],
            rate_override=params.get("rate_override"),
            property_tax_rate=tax_rate,
        )
        financial = await AnalysisService.run_financial(db, property_id, financial_params)

        # Tax
        tax_params = TaxAnalysisRequest(
            list_price=list_price,
            loan_amount=loan_amount,
            marginal_tax_rate=params.get("marginal_tax_rate", 0.24),
            filing_status=params.get("filing_status", "married"),
            current_home_purchase_price=params.get("current_home_purchase_price"),
            current_home_estimated_value=params.get("current_home_estimated_value"),
            current_home_remaining_mortgage=params.get("current_home_remaining_mortgage"),
            years_as_primary=params.get("years_as_primary"),
            estimated_monthly_rent=params.get("estimated_monthly_rent"),
        )
        tax = await AnalysisService.run_tax(db, property_id, tax_params)

        # Investment
        inv_params = InvestmentAnalysisRequest(
            list_price=list_price,
            loan_amount=loan_amount,
            term_years=term,
            down_payment_pct=down_pct,
            hoa_monthly=params.get("hoa_monthly", 0.0),
            property_tax_rate=tax_rate,
            insurance_rate=params.get("insurance_rate", 0.0035),
            appreciation_rate=params.get("appreciation_rate", 0.03),
            marginal_tax_rate=params.get("marginal_tax_rate", 0.24),
        )
        investment = await AnalysisService.run_investment(db, property_id, inv_params)

        # Condition
        condition = await AnalysisService.run_condition(db, property_id)

        return {
            "financial": financial.model_dump(),
            "tax": tax.model_dump(),
            "investment": investment.model_dump(),
            "condition": condition,
        }
