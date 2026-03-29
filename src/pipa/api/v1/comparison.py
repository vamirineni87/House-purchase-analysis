"""Property comparison endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_db
from pipa.models.component import ComponentSystem
from pipa.models.property import Property
from pipa.schemas.comparison import ComparisonRequest, ComparisonResult, PropertyScore

router = APIRouter(tags=["comparison"])


@router.post("/comparison", response_model=ComparisonResult)
async def compare_properties(
    body: ComparisonRequest,
    db: AsyncSession = Depends(get_db),
):
    """Compare multiple properties using weighted scoring.

    Currently scores properties on a 0-100 scale across configurable
    categories. Categories without data are scored at 50 (neutral).
    """
    # Load all requested properties
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses))
        .where(Property.id.in_(body.property_ids))
    )
    properties = {p.id: p for p in result.scalars().all()}

    # Verify all requested properties exist
    missing = set(body.property_ids) - set(properties.keys())
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Properties not found: {', '.join(missing)}",
        )

    weights = body.weights
    total_weight = sum(weights.values()) or 1.0

    scores: list[PropertyScore] = []

    for pid in body.property_ids:
        prop = properties[pid]

        # Get address for display
        address = None
        for addr in prop.addresses:
            if addr.is_current and addr.address_type == "situs":
                address = addr.normalized_address
                break

        category_scores: dict[str, float] = {}

        # Financial score — based on price relative to peers
        # For now, use neutral score; real impl would compare payment-to-income, etc.
        category_scores["financial"] = 50.0

        # Condition score — from component data
        comp_result = await db.execute(
            select(ComponentSystem).where(
                ComponentSystem.property_id == pid
            )
        )
        components = list(comp_result.scalars().all())
        if components:
            from pipa.analysis.condition import score_property_condition

            comp_dicts = [
                {
                    "type": c.component_type,
                    "install_year": c.estimated_install_year or 2020,
                }
                for c in components
            ]
            category_scores["condition"] = score_property_condition(comp_dicts)
        else:
            category_scores["condition"] = 50.0

        # Location, risk, hoa, surrounding — neutral defaults
        category_scores["location"] = 50.0
        category_scores["risk"] = 50.0
        category_scores["hoa"] = 50.0
        category_scores["surrounding"] = 50.0

        # Compute weighted total
        total_score = 0.0
        for cat, weight in weights.items():
            cat_score = category_scores.get(cat, 50.0)
            total_score += cat_score * (weight / total_weight)

        scores.append(
            PropertyScore(
                property_id=pid,
                address=address,
                total_score=round(total_score, 1),
                category_scores=category_scores,
            )
        )

    # Rank by total score descending
    scores.sort(key=lambda s: s.total_score, reverse=True)
    for i, s in enumerate(scores, 1):
        s.rank = i

    return ComparisonResult(
        properties=scores,
        weights_used=weights,
    )
