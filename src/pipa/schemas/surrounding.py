"""Pydantic v2 schemas for surrounding properties endpoint."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SurroundingStats(BaseModel):
    """Surrounding property statistics."""

    property_id: str
    investor_share: float = 0.0
    turnover_rate: float = 0.0
    flip_count: int = 0
    stability_score: float = 100.0
    total_nearby: int = 0
    median_sale_price: Optional[float] = None
    avg_price_per_sqft: Optional[float] = None
