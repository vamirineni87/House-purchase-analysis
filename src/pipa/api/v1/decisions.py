"""Decision workflow endpoints — case files, due diligence, recommendations, and packets."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.schemas.decision import (
    DecisionCaseCreate,
    DecisionCaseResponse,
    DecisionCaseUpdate,
    DecisionPacketResponse,
    DueDiligenceCreate,
    DueDiligenceResponse,
    DueDiligenceUpdate,
    RecommendationResponse,
)
from pipa.services.decision_service import DecisionService

router = APIRouter(tags=["decisions"])


# ------------------------------------------------------------------
# Decision case
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/decision",
    response_model=DecisionCaseResponse,
)
async def get_decision_case(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the decision case for a property."""
    case = await DecisionService.get_case(db, property_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Decision case not found")
    return case


@router.post(
    "/properties/{property_id}/decision",
    response_model=DecisionCaseResponse,
    status_code=201,
)
async def create_decision_case(
    property_id: str,
    body: DecisionCaseCreate | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Create a decision case for a property."""
    existing = await DecisionService.get_case(db, property_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Decision case already exists for this property",
        )
    case = await DecisionService.create_case(db, property_id)
    # Apply any overrides from the body
    if body is not None:
        if body.stage != "discovered":
            case.stage = body.stage
        if body.decision_status != "maybe":
            case.decision_status = body.decision_status
        if body.priority != 5:
            case.priority = body.priority
        if body.max_offer_current is not None:
            case.max_offer_current = body.max_offer_current
        if body.walk_away_price is not None:
            case.walk_away_price = body.walk_away_price
        if body.target_monthly_payment is not None:
            case.target_monthly_payment = body.target_monthly_payment
        if body.status_summary is not None:
            case.status_summary = body.status_summary
        if body.spouse_notes is not None:
            case.spouse_notes = body.spouse_notes
        if body.family_notes is not None:
            case.family_notes = body.family_notes
    return case


@router.patch(
    "/properties/{property_id}/decision",
    response_model=DecisionCaseResponse,
)
async def update_decision_case(
    property_id: str,
    body: DecisionCaseUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the stage and/or status of a decision case."""
    case = await DecisionService.get_case(db, property_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Decision case not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(case, field, value)

    return case


# ------------------------------------------------------------------
# Due diligence
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/due-diligence",
    response_model=list[DueDiligenceResponse],
)
async def list_due_diligence(
    property_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List due diligence items for a property, optionally filtered by status."""
    return await DecisionService.list_due_diligence(db, property_id, status=status)


@router.post(
    "/properties/{property_id}/due-diligence",
    response_model=DueDiligenceResponse,
    status_code=201,
)
async def create_due_diligence(
    property_id: str,
    body: DueDiligenceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a due diligence item for a property."""
    item = await DecisionService.add_due_diligence(
        db,
        property_id=property_id,
        category=body.category,
        title=body.title,
        severity=body.severity,
    )
    # Apply optional fields from body
    if body.description is not None:
        item.description = body.description
    if body.due_date is not None:
        item.due_date = body.due_date
    return item


@router.patch(
    "/properties/{property_id}/due-diligence/{item_id}",
    response_model=DueDiligenceResponse,
)
async def update_due_diligence(
    property_id: str,
    item_id: str,
    body: DueDiligenceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a due diligence item."""
    try:
        item = await DecisionService.update_due_diligence(
            db,
            item_id=item_id,
            status=body.status or "open",
            resolution_note=body.resolution_note,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Due diligence item not found")

    # Apply additional optional fields
    update_data = body.model_dump(exclude_unset=True, exclude={"status", "resolution_note"})
    for field, value in update_data.items():
        setattr(item, field, value)

    return item


# ------------------------------------------------------------------
# Decision packet
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/decision/packet",
    response_model=DecisionPacketResponse,
)
async def get_decision_packet(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the full 7-section decision packet for a property."""
    packet = await DecisionService.generate_decision_packet(db, property_id)
    return packet


# ------------------------------------------------------------------
# Recommendations
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/decision/recommendations",
    response_model=list[RecommendationResponse],
)
async def get_recommendations(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get recommendation history for a property, newest first."""
    return await DecisionService.get_recommendations(db, property_id)
