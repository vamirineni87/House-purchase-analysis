"""Insurance cost estimation and natural disaster risk assessment.

Estimates homeowners insurance, assesses flood risk via the OpenFEMA API,
and evaluates regional natural disaster exposure based on state-level data.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from hpa.analysis.base import BaseAnalyzer
from hpa.api.openfema import OpenFEMAClient
from hpa.config import AppConfig
from hpa.models.insurance import (
    FloodInsuranceEstimate,
    HomeownersInsuranceEstimate,
    InsuranceAnalysisResult,
    NaturalDisasterRisk,
)
from hpa.models.property import PropertyDetails

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State-level natural disaster risk lookup tables
# ---------------------------------------------------------------------------
_HURRICANE_HIGH_STATES: set[str] = {
    "FL", "LA", "TX", "NC", "SC", "AL", "MS", "GA",
}
_EARTHQUAKE_HIGH_STATES: set[str] = {
    "CA", "AK", "HI", "WA", "OR",
}
_WILDFIRE_HIGH_STATES: set[str] = {
    "CA", "CO", "OR", "WA", "MT", "AZ",
}
_TORNADO_HIGH_STATES: set[str] = {
    "TX", "OK", "KS", "NE", "SD", "IA", "IL", "IN", "MO", "AR",
}

# Flood insurance premium estimates by inferred zone
_FLOOD_PREMIUM_MODERATE = 500.0
_FLOOD_PREMIUM_HIGH = 1_200.0


class InsuranceAnalyzer(BaseAnalyzer):
    """Estimates insurance costs and assesses natural disaster risk for a
    property."""

    @property
    def name(self) -> str:
        return "Insurance & Risk Analysis"

    @property
    def requires_api(self) -> bool:
        return True

    def analyze(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> InsuranceAnalysisResult:
        """Run full insurance analysis including homeowners, flood, and
        disaster risk assessments.

        Parameters
        ----------
        property_details:
            The property being evaluated.
        config:
            Application configuration with default rate assumptions.
        """
        homeowners = self.estimate_homeowners_insurance(
            property_details, config
        )

        flood_risk_label, flood_estimate = self.assess_flood_risk(
            property_details, config
        )

        disaster_risk = self.assess_disaster_risk(property_details)

        # --- Totals ---
        total_annual = homeowners.annual_premium
        if flood_estimate is not None:
            total_annual += flood_estimate.annual_premium

        total_annual = round(total_annual, 2)
        total_monthly = round(total_annual / 12.0, 2)

        # Risk-adjusted monthly cost adds a buffer for high-risk areas.
        risk_multiplier = 1.0 + (disaster_risk.overall_risk_score - 1) * 0.01
        risk_adjusted = round(total_monthly * risk_multiplier, 2)

        return InsuranceAnalysisResult(
            homeowners=homeowners,
            flood=flood_estimate,
            disaster_risk=disaster_risk,
            total_annual_insurance=total_annual,
            total_monthly_insurance=total_monthly,
            risk_adjusted_monthly_cost=risk_adjusted,
        )

    # ------------------------------------------------------------------
    # Homeowners insurance
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_homeowners_insurance(
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> HomeownersInsuranceEstimate:
        """Estimate standard homeowners insurance (HO-3 equivalent)."""

        annual = round(
            property_details.list_price
            * config.defaults.homeowners_insurance_annual_pct,
            2,
        )
        monthly = round(annual / 12.0, 2)
        coverage = property_details.list_price  # dwelling replacement value

        return HomeownersInsuranceEstimate(
            annual_premium=annual,
            monthly_premium=monthly,
            coverage_amount=coverage,
        )

    # ------------------------------------------------------------------
    # Flood risk & insurance
    # ------------------------------------------------------------------

    def assess_flood_risk(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> tuple[str, Optional[FloodInsuranceEstimate]]:
        """Check OpenFEMA for flood disaster declarations in the ZIP code.

        Returns a tuple of (risk_label, optional flood insurance estimate).
        """
        zip_code = property_details.address.zip_code
        declarations = self._fetch_flood_declarations(zip_code)

        if declarations is not None and len(declarations) > 0:
            # Infer risk level from number of historical declarations.
            if len(declarations) >= 3:
                zone = "AE"
                risk_label = "high"
                premium = _FLOOD_PREMIUM_HIGH
            else:
                zone = "X500"
                risk_label = "moderate"
                premium = _FLOOD_PREMIUM_MODERATE

            flood_estimate = FloodInsuranceEstimate(
                flood_zone=zone,
                annual_premium=premium,
                required=True,
                coverage_amount=min(
                    property_details.list_price, 250_000.0
                ),
            )
            logger.info(
                "Flood risk for ZIP %s: %s (%d declarations found)",
                zip_code,
                risk_label,
                len(declarations),
            )
            return risk_label, flood_estimate

        # No declarations or API unavailable — assume low risk.
        logger.info(
            "No flood declarations found for ZIP %s; assuming low risk",
            zip_code,
        )
        return "low", None

    def _fetch_flood_declarations(
        self, zip_code: str
    ) -> Optional[list[dict]]:
        """Synchronously fetch flood declarations, handling both sync and
        async execution contexts gracefully."""

        client = OpenFEMAClient()
        try:
            # Try synchronous first (works when no event loop is running).
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # We're inside an existing async context — run in a new thread
                # to avoid blocking.
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=1
                ) as pool:
                    future = pool.submit(self._run_async_fetch, client, zip_code)
                    result = future.result(timeout=client.timeout)
            else:
                result = asyncio.run(client.get_flood_risk(zip_code))

            if result is not None and "DisasterDeclarationsSummaries" in result:
                return result["DisasterDeclarationsSummaries"]
            return None

        except Exception:
            logger.warning(
                "Failed to fetch flood data for ZIP %s; proceeding without",
                zip_code,
                exc_info=True,
            )
            return None

    @staticmethod
    def _run_async_fetch(
        client: OpenFEMAClient, zip_code: str
    ) -> Optional[dict]:
        """Run the async fetch in a fresh event loop (for thread-pool use)."""
        return asyncio.run(client.get_flood_risk(zip_code))

    # ------------------------------------------------------------------
    # Natural disaster risk assessment
    # ------------------------------------------------------------------

    @staticmethod
    def assess_disaster_risk(
        property_details: PropertyDetails,
    ) -> NaturalDisasterRisk:
        """Assess natural disaster risk based on the property's state.

        Uses hard-coded state-level risk tables for hurricane, earthquake,
        wildfire, and tornado exposure.  Overall risk score is 1-10 based
        on the number of high-risk categories.
        """
        state = property_details.address.state.upper().strip()

        hurricane = (
            "high" if state in _HURRICANE_HIGH_STATES else "low"
        )
        earthquake = (
            "high" if state in _EARTHQUAKE_HIGH_STATES else "low"
        )
        wildfire = (
            "high" if state in _WILDFIRE_HIGH_STATES else "low"
        )
        tornado = (
            "high" if state in _TORNADO_HIGH_STATES else "low"
        )

        high_count = sum(
            1
            for risk in (hurricane, earthquake, wildfire, tornado)
            if risk == "high"
        )

        # Map 0-4 high categories to a 1-10 score.
        # 0 high -> 1, 1 high -> 3, 2 high -> 5, 3 high -> 7, 4 high -> 9
        score_map = {0: 1, 1: 3, 2: 5, 3: 7, 4: 9}
        overall_score = score_map.get(high_count, 10)

        return NaturalDisasterRisk(
            earthquake_risk=earthquake,
            hurricane_risk=hurricane,
            wildfire_risk=wildfire,
            tornado_risk=tornado,
            overall_risk_score=overall_score,
        )
