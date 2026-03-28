"""Appraisal analysis module for evaluating property value via comparable sales."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from statistics import mean
from typing import Optional

from hpa.analysis.base import BaseAnalyzer
from hpa.config import AppConfig
from hpa.models.appraisal import AppraisalResult, ComparableSale
from hpa.models.property import Address, PropertyDetails
from hpa.api.rentcast import RentCastClient

logger = logging.getLogger(__name__)


class AppraisalAnalyzer(BaseAnalyzer):
    """Evaluates whether a property is priced fairly by analyzing comparable sales."""

    @property
    def name(self) -> str:
        return "Appraisal Analysis"

    @property
    def requires_api(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
        manual_comps: list[dict] | None = None,
    ) -> AppraisalResult:
        """Run appraisal analysis for *property_details*.

        1. Attempt to fetch comps from RentCast if an API key is available.
        2. Fall back to *manual_comps* if provided.
        3. If no comps at all, generate a basic estimate using price-per-sqft
           heuristics.
        """
        comps: list[ComparableSale] = []

        # --- Step 1: Try RentCast API ---
        if config.api_keys.rentcast:
            try:
                comps = self._fetch_comps_from_api(property_details, config)
            except Exception:
                logger.warning("RentCast API call failed; falling back to manual comps.")

        # --- Step 2: Fall back to manual comps ---
        if not comps and manual_comps:
            comps = self._parse_manual_comps(manual_comps)

        # --- Step 3: Adjust comparables ---
        adjusted_comps = [
            self.adjust_comparable(comp, property_details, config) for comp in comps
        ]

        # --- Step 4: Assess value ---
        if adjusted_comps:
            low, mid, high, assessment = self.assess_value(
                property_details, adjusted_comps
            )
        else:
            # Heuristic fallback: assume subject price is the only data point
            low, mid, high, assessment = self._heuristic_estimate(property_details)

        confidence = self.determine_confidence(adjusted_comps)

        subject_ppsf = property_details.list_price / max(property_details.square_feet, 1)
        market_ppsf = mid / max(property_details.square_feet, 1) if mid else subject_ppsf

        return AppraisalResult(
            comparables=adjusted_comps,
            estimated_value_low=round(low, 2),
            estimated_value_mid=round(mid, 2),
            estimated_value_high=round(high, 2),
            price_per_sqft_market=round(market_ppsf, 2),
            subject_price_per_sqft=round(subject_ppsf, 2),
            value_assessment=assessment,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Comparable adjustments
    # ------------------------------------------------------------------

    def adjust_comparable(
        self,
        comp: ComparableSale,
        subject: PropertyDetails,
        config: AppConfig,
    ) -> ComparableSale:
        """Apply standard appraisal adjustments to a comparable sale.

        Adjustments move the comp's price toward what it *would have sold for*
        if it were identical to the subject property.

        - Square footage: $100 per sqft difference.
        - Bedrooms: $10,000 per bedroom difference.
        - Bathrooms: $7,500 per bathroom difference.
        - Year built: $2,000 per year difference.
        - Time: appreciation_rate applied to months since sale.
        """
        adjustments: dict[str, float] = {}

        # --- Square footage ---
        sqft_diff = subject.square_feet - comp.square_feet
        adjustments["sqft"] = sqft_diff * 100.0

        # --- Bedrooms ---
        bed_diff = subject.bedrooms - comp.bedrooms
        adjustments["bedrooms"] = bed_diff * 10_000.0

        # --- Bathrooms ---
        bath_diff = subject.bathrooms - comp.bathrooms
        adjustments["bathrooms"] = bath_diff * 7_500.0

        # --- Year built / age ---
        if comp.year_built and subject.year_built:
            year_diff = subject.year_built - comp.year_built
            adjustments["year_built"] = year_diff * 2_000.0
        else:
            adjustments["year_built"] = 0.0

        # --- Time adjustment (market appreciation since sale) ---
        today = date.today()
        months_since_sale = (
            (today.year - comp.sale_date.year) * 12
            + (today.month - comp.sale_date.month)
        )
        monthly_appreciation = config.defaults.appreciation_rate / 12.0
        time_adjustment = comp.sale_price * monthly_appreciation * max(months_since_sale, 0)
        adjustments["time"] = round(time_adjustment, 2)

        total_adjustment = sum(adjustments.values())
        adjusted_price = comp.sale_price + total_adjustment

        return comp.model_copy(
            update={
                "adjustments": adjustments,
                "adjusted_price": round(adjusted_price, 2),
            }
        )

    # ------------------------------------------------------------------
    # Value assessment
    # ------------------------------------------------------------------

    def assess_value(
        self,
        property_details: PropertyDetails,
        adjusted_comps: list[ComparableSale],
    ) -> tuple[float, float, float, str]:
        """Derive low/mid/high value estimates and a market assessment.

        Returns:
            (low, mid, high, assessment) where assessment is one of
            ``"below_market"``, ``"at_market"``, or ``"above_market"``.
        """
        sqft = max(property_details.square_feet, 1)

        adjusted_ppsf_values = [
            (c.adjusted_price or c.sale_price) / max(c.square_feet, 1)
            for c in adjusted_comps
        ]

        low = min(adjusted_ppsf_values) * sqft
        mid = mean(adjusted_ppsf_values) * sqft
        high = max(adjusted_ppsf_values) * sqft

        list_price = property_details.list_price
        if list_price < mid * 0.95:
            assessment = "below_market"
        elif list_price > mid * 1.05:
            assessment = "above_market"
        else:
            assessment = "at_market"

        return low, mid, high, assessment

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    @staticmethod
    def determine_confidence(comps: list[ComparableSale]) -> str:
        """Return a confidence label based on the number of comparables.

        - 0 comps  -> ``"low"``
        - 1-3 comps -> ``"medium"``
        - 4+ comps -> ``"high"``
        """
        count = len(comps)
        if count == 0:
            return "low"
        if count <= 3:
            return "medium"
        return "high"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_comps_from_api(
        self,
        property_details: PropertyDetails,
        config: AppConfig,
    ) -> list[ComparableSale]:
        """Fetch comparable sales from RentCast and convert to models."""
        client = RentCastClient(api_key=config.api_keys.rentcast)
        addr = property_details.address
        full_address = f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}"

        raw_comps = asyncio.run(client.get_comparable_sales(full_address))
        if not raw_comps:
            return []

        return [self._raw_comp_to_model(raw) for raw in raw_comps if raw]

    def _parse_manual_comps(self, manual_comps: list[dict]) -> list[ComparableSale]:
        """Convert a list of plain dicts to ComparableSale models."""
        results: list[ComparableSale] = []
        for raw in manual_comps:
            try:
                results.append(self._raw_comp_to_model(raw))
            except Exception:
                logger.warning("Skipping invalid manual comparable: %s", raw)
        return results

    @staticmethod
    def _raw_comp_to_model(raw: dict) -> ComparableSale:
        """Map a raw dict (from API or manual input) to a ComparableSale."""
        # Address handling: accept nested dict or flat fields.
        if "address" in raw and isinstance(raw["address"], dict):
            address = Address(**raw["address"])
        else:
            address = Address(
                street=raw.get("street", raw.get("formattedAddress", "Unknown")),
                city=raw.get("city", "Unknown"),
                state=raw.get("state", "Unknown"),
                zip_code=raw.get("zip_code", raw.get("zipCode", "00000")),
            )

        sale_price = float(raw.get("sale_price", raw.get("price", raw.get("lastSalePrice", 0))))
        square_feet = int(raw.get("square_feet", raw.get("squareFootage", 0)))
        price_per_sqft = sale_price / max(square_feet, 1)

        sale_date_raw = raw.get("sale_date", raw.get("lastSaleDate", None))
        if isinstance(sale_date_raw, str):
            sale_date = date.fromisoformat(sale_date_raw[:10])
        elif isinstance(sale_date_raw, date):
            sale_date = sale_date_raw
        else:
            sale_date = date.today()

        return ComparableSale(
            address=address,
            sale_price=sale_price,
            sale_date=sale_date,
            square_feet=square_feet,
            bedrooms=int(raw.get("bedrooms", 0)),
            bathrooms=float(raw.get("bathrooms", 0)),
            year_built=raw.get("year_built", raw.get("yearBuilt")),
            price_per_sqft=round(price_per_sqft, 2),
            distance_miles=float(raw.get("distance_miles", raw.get("distance", 0.0))),
        )

    @staticmethod
    def _heuristic_estimate(
        property_details: PropertyDetails,
    ) -> tuple[float, float, float, str]:
        """Generate a rough value estimate when no comps are available.

        Uses the list price as the midpoint and applies +/- 10% band.
        """
        mid = property_details.list_price
        low = mid * 0.90
        high = mid * 1.10
        assessment = "at_market"
        return low, mid, high, assessment
