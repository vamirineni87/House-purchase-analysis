"""Side-by-side property comparison across financial and physical dimensions."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from hpa.analysis.base import BaseAnalyzer
from hpa.analysis.financial import FinancialAnalyzer
from hpa.config import AppConfig
from hpa.models.financial import FinancialAnalysisResult
from hpa.models.property import PropertyDetails


# ------------------------------------------------------------------
# Result models
# ------------------------------------------------------------------


class PropertyScore(BaseModel):
    """Scored summary of a single property within a comparison set."""

    address: str
    financial_score: float  # 0-100
    value_score: float  # 0-100 (price per sqft relative to others)
    size_score: float  # 0-100
    total_score: float  # weighted average
    monthly_payment: float  # best-scenario monthly payment
    price_per_sqft: float
    pros: list[str]
    cons: list[str]


class ComparisonResult(BaseModel):
    """Aggregated comparison across all evaluated properties."""

    properties: list[PropertyScore]
    ranking: list[str]  # addresses sorted best to worst
    best_value: str  # address with best price/sqft
    lowest_payment: str  # address with lowest monthly payment


# ------------------------------------------------------------------
# Default scoring weights
# ------------------------------------------------------------------

_DEFAULT_WEIGHTS: dict[str, float] = {
    "financial": 0.40,
    "value": 0.35,
    "size": 0.25,
}


# ------------------------------------------------------------------
# Analyzer
# ------------------------------------------------------------------


class ComparisonAnalyzer(BaseAnalyzer):
    """Compares a set of properties and produces a ranked scorecard."""

    @property
    def name(self) -> str:
        return "Property Comparison"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        properties: list[PropertyDetails],
        config: AppConfig,
        weights: dict[str, float] | None = None,
    ) -> ComparisonResult:
        """Score and rank *properties* relative to one another.

        Parameters
        ----------
        properties:
            Two or more properties to compare.
        config:
            Application configuration with default assumptions.
        weights:
            Optional weight overrides for ``"financial"``, ``"value"``,
            and ``"size"`` dimensions.  Values should sum to 1.0.
        """
        if weights is None:
            weights = _DEFAULT_WEIGHTS

        w_fin = weights.get("financial", _DEFAULT_WEIGHTS["financial"])
        w_val = weights.get("value", _DEFAULT_WEIGHTS["value"])
        w_size = weights.get("size", _DEFAULT_WEIGHTS["size"])

        financial_analyzer = FinancialAnalyzer()

        # ----- Step 1: Gather raw data per property ----- #
        raw_data: list[dict] = []

        for prop in properties:
            result: FinancialAnalysisResult = financial_analyzer.analyze(prop, config)

            # Best (lowest) monthly payment across scenarios
            best_payment = min(
                bd.total for bd in result.payment_breakdowns.values()
            )

            price_per_sqft = (
                round(prop.list_price / prop.square_feet, 2)
                if prop.square_feet > 0
                else 0.0
            )

            address_str = (
                f"{prop.address.street}, {prop.address.city}, "
                f"{prop.address.state} {prop.address.zip_code}"
            )

            raw_data.append(
                {
                    "property": prop,
                    "result": result,
                    "address": address_str,
                    "best_payment": best_payment,
                    "price_per_sqft": price_per_sqft,
                    "sqft": prop.square_feet,
                }
            )

        # ----- Step 2: Compute group statistics ----- #
        payments = [d["best_payment"] for d in raw_data]
        ppsfs = [d["price_per_sqft"] for d in raw_data]
        sqfts = [d["sqft"] for d in raw_data]

        min_payment = min(payments)
        max_payment = max(payments) if max(payments) != min_payment else min_payment + 1

        min_ppsf = min(ppsfs)
        max_ppsf = max(ppsfs) if max(ppsfs) != min_ppsf else min_ppsf + 1

        min_sqft = min(sqfts)
        max_sqft = max(sqfts) if max(sqfts) != min_sqft else min_sqft + 1

        # ----- Step 3: Score each property ----- #
        scored: list[PropertyScore] = []

        for d in raw_data:
            # Lower payment -> higher score
            financial_score = round(
                100 * (1 - (d["best_payment"] - min_payment) / (max_payment - min_payment)),
                2,
            )

            # Lower price/sqft -> higher score
            value_score = round(
                100 * (1 - (d["price_per_sqft"] - min_ppsf) / (max_ppsf - min_ppsf)),
                2,
            )

            # More sqft -> higher score
            size_score = round(
                100 * ((d["sqft"] - min_sqft) / (max_sqft - min_sqft)),
                2,
            )

            total_score = round(
                w_fin * financial_score + w_val * value_score + w_size * size_score,
                2,
            )

            # ----- Step 4: Pros / Cons ----- #
            pros: list[str] = []
            cons: list[str] = []

            prop: PropertyDetails = d["property"]

            if d["best_payment"] == min_payment:
                pros.append("Lowest monthly payment")
            if d["best_payment"] == max(payments):
                cons.append("Highest monthly payment")

            if d["price_per_sqft"] == min_ppsf:
                pros.append("Lowest price per sqft")
            if d["price_per_sqft"] == max_ppsf:
                cons.append("Highest price per sqft")

            if d["sqft"] == max(sqfts):
                pros.append("Largest living area")
            if d["sqft"] == min(sqfts):
                cons.append("Smallest living area")

            if prop.hoa_monthly == 0.0:
                pros.append("No HOA fees")
            elif prop.hoa_monthly == max(p.hoa_monthly for p in properties):
                cons.append("Highest HOA")

            if prop.year_built is not None:
                newest = max(
                    (p.year_built for p in properties if p.year_built is not None),
                    default=0,
                )
                oldest = min(
                    (p.year_built for p in properties if p.year_built is not None),
                    default=0,
                )
                if prop.year_built == newest and newest != oldest:
                    pros.append("Newest construction")
                if prop.year_built == oldest and newest != oldest:
                    cons.append("Oldest construction")

            if prop.lot_size_sqft is not None:
                lot_sizes = [
                    p.lot_size_sqft
                    for p in properties
                    if p.lot_size_sqft is not None
                ]
                if lot_sizes and prop.lot_size_sqft == max(lot_sizes):
                    pros.append("Largest lot")

            if prop.garage_spaces == max(p.garage_spaces for p in properties):
                if prop.garage_spaces > 0:
                    pros.append(f"{prop.garage_spaces}-car garage")

            scored.append(
                PropertyScore(
                    address=d["address"],
                    financial_score=financial_score,
                    value_score=value_score,
                    size_score=size_score,
                    total_score=total_score,
                    monthly_payment=d["best_payment"],
                    price_per_sqft=d["price_per_sqft"],
                    pros=pros,
                    cons=cons,
                )
            )

        # ----- Step 5: Rank ----- #
        scored.sort(key=lambda s: s.total_score, reverse=True)
        ranking = [s.address for s in scored]

        best_value_entry = min(scored, key=lambda s: s.price_per_sqft)
        lowest_payment_entry = min(scored, key=lambda s: s.monthly_payment)

        return ComparisonResult(
            properties=scored,
            ranking=ranking,
            best_value=best_value_entry.address,
            lowest_payment=lowest_payment_entry.address,
        )
