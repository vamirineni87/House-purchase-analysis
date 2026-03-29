"""Pydantic v2 schemas for property comparison endpoint."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ComparisonRequest(BaseModel):
    """Request body for multi-property comparison."""

    property_ids: list[str] = Field(..., min_length=2, max_length=10)
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "financial": 0.25,
            "condition": 0.20,
            "location": 0.20,
            "risk": 0.15,
            "hoa": 0.10,
            "surrounding": 0.10,
        }
    )
    # Common financial params for comparison
    list_prices: Optional[dict[str, float]] = None  # property_id -> price
    down_payment_pct: float = 0.20
    term_years: int = 30


class PropertyScore(BaseModel):
    """Score breakdown for a single property."""

    property_id: str
    address: Optional[str] = None
    total_score: float = 0.0
    category_scores: dict[str, float] = {}
    rank: int = 0


class ComparisonResult(BaseModel):
    """Result of multi-property comparison."""

    properties: list[PropertyScore]
    weights_used: dict[str, float]
