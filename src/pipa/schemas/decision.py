"""Pydantic v2 schemas for decision workflow endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# DecisionCase
# ---------------------------------------------------------------------------

class DecisionCaseCreate(BaseModel):
    """Create a decision case for a property (most fields have defaults)."""

    stage: str = "discovered"
    decision_status: str = "maybe"
    priority: int = Field(default=5, ge=1, le=10)
    max_offer_current: Optional[float] = None
    walk_away_price: Optional[float] = None
    target_monthly_payment: Optional[float] = None
    status_summary: Optional[str] = None
    spouse_notes: Optional[str] = None
    family_notes: Optional[str] = None


class DecisionCaseUpdate(BaseModel):
    """Partial update for a decision case."""

    stage: Optional[str] = None
    decision_status: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    pursue_score: Optional[float] = None
    max_offer_current: Optional[float] = None
    walk_away_price: Optional[float] = None
    target_monthly_payment: Optional[float] = None
    confidence_level: Optional[str] = None
    status_summary: Optional[str] = None
    offer_deadline: Optional[datetime] = None
    spouse_notes: Optional[str] = None
    family_notes: Optional[str] = None


class DecisionCaseResponse(BaseModel):
    """Decision case returned by the API."""

    id: str
    property_id: str
    stage: str
    decision_status: str
    priority: int
    pursue_score: Optional[float] = None
    max_offer_current: Optional[float] = None
    walk_away_price: Optional[float] = None
    target_monthly_payment: Optional[float] = None
    confidence_level: Optional[str] = None
    status_summary: Optional[str] = None
    offer_deadline: Optional[datetime] = None
    spouse_notes: Optional[str] = None
    family_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DueDiligenceItem
# ---------------------------------------------------------------------------

class DueDiligenceCreate(BaseModel):
    """Create a due diligence item."""

    category: str
    title: str
    description: Optional[str] = None
    severity: str = "important"
    due_date: Optional[datetime] = None


class DueDiligenceUpdate(BaseModel):
    """Partial update for a due diligence item."""

    status: Optional[str] = None
    severity: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    resolution_note: Optional[str] = None
    document_id: Optional[str] = None


class DueDiligenceResponse(BaseModel):
    """Due diligence item returned by the API."""

    id: str
    property_id: str
    decision_case_id: Optional[str] = None
    category: str
    title: str
    description: Optional[str] = None
    status: str
    severity: Optional[str] = None
    due_date: Optional[datetime] = None
    resolution_note: Optional[str] = None
    document_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# RecommendationSnapshot
# ---------------------------------------------------------------------------

class RecommendationResponse(BaseModel):
    """Recommendation snapshot returned by the API."""

    id: str
    property_id: str
    decision_case_id: Optional[str] = None
    pursue_recommendation: str
    max_offer: Optional[float] = None
    walk_away_price: Optional[float] = None
    main_red_flags: Optional[list[str]] = None
    unresolved_unknowns: Optional[list[str]] = None
    top_questions: Optional[list[str]] = None
    compare_rank: Optional[int] = None
    analysis_run_ids: Optional[list[str]] = None
    confidence: str
    reasoning: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Decision Packet — the 7-section buyer output
# ---------------------------------------------------------------------------

class QuickTakeSection(BaseModel):
    """Section 1: QUICK TAKE."""
    recommendation: str  # pursue / maybe / pass
    bullets: list[str]


class PriceViewSection(BaseModel):
    """Section 2: PRICE VIEW."""
    list_price: Optional[float] = None
    comp_estimate: Optional[float] = None
    assessment_value: Optional[float] = None
    max_offer: Optional[float] = None
    walk_away_price: Optional[float] = None


class MonthlyCostSection(BaseModel):
    """Section 3: MONTHLY COST VIEW."""
    all_in_monthly: Optional[float] = None
    cash_to_close: Optional[float] = None
    stress_tested_monthly: Optional[float] = None
    breakdown: Optional[dict] = None


class HiddenCostSection(BaseModel):
    """Section 4: HIDDEN COST VIEW."""
    capex_items: Optional[list[dict]] = None
    unknowns: Optional[list[str]] = None
    permit_concerns: Optional[list[str]] = None


class CommunityViewSection(BaseModel):
    """Section 5: HOA / COMMUNITY VIEW."""
    hoa_monthly: Optional[float] = None
    hoa_health: Optional[str] = None
    community_notes: Optional[list[str]] = None


class CurrentHomeImpactSection(BaseModel):
    """Section 6: CURRENT HOME IMPACT."""
    sell_vs_rent_summary: Optional[str] = None
    net_monthly_delta: Optional[float] = None
    details: Optional[dict] = None


class NextActionsSection(BaseModel):
    """Section 7: NEXT ACTIONS."""
    actions: list[dict]  # Each has title, category, severity, status


class DecisionPacketResponse(BaseModel):
    """The full 7-section decision packet for a property."""

    property_id: str
    decision_case_id: Optional[str] = None
    generated_at: datetime
    quick_take: QuickTakeSection
    price_view: PriceViewSection
    monthly_cost: MonthlyCostSection
    hidden_cost: HiddenCostSection
    community_view: CommunityViewSection
    current_home_impact: CurrentHomeImpactSection
    next_actions: NextActionsSection
