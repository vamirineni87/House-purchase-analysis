"""Decision workflow service — manages case files, due diligence, and recommendations.

Bridges the analysis layer with the buyer's live decision process,
generating actionable packets from computed data and tracked items.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.analysis_models import AnalysisRun
from pipa.models.decision import DecisionCase, DueDiligenceItem, RecommendationSnapshot

logger = logging.getLogger(__name__)


class DecisionService:
    """Creates, queries, and manages decision cases, due diligence, and recommendations."""

    # ------------------------------------------------------------------
    # Decision cases
    # ------------------------------------------------------------------

    @staticmethod
    async def create_case(
        db: AsyncSession,
        property_id: str,
    ) -> DecisionCase:
        """Create a new decision case for a property with stage='discovered'."""
        case = DecisionCase(
            property_id=property_id,
            stage="discovered",
            decision_status="maybe",
            priority=5,
        )
        db.add(case)
        await db.flush()
        return case

    @staticmethod
    async def get_case(
        db: AsyncSession,
        property_id: str,
    ) -> DecisionCase | None:
        """Get the decision case for a property. Returns None if not found."""
        result = await db.execute(
            select(DecisionCase).where(DecisionCase.property_id == property_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_stage(
        db: AsyncSession,
        case_id: str,
        stage: str,
        notes: Optional[str] = None,
    ) -> DecisionCase:
        """Update the stage of a decision case."""
        result = await db.execute(
            select(DecisionCase).where(DecisionCase.id == case_id)
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise ValueError(f"DecisionCase {case_id} not found")
        case.stage = stage
        if notes is not None:
            case.status_summary = notes
        return case

    @staticmethod
    async def update_decision(
        db: AsyncSession,
        case_id: str,
        decision_status: str,
        max_offer: Optional[float] = None,
        walk_away: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> DecisionCase:
        """Update the decision status and optional pricing thresholds."""
        result = await db.execute(
            select(DecisionCase).where(DecisionCase.id == case_id)
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise ValueError(f"DecisionCase {case_id} not found")
        case.decision_status = decision_status
        if max_offer is not None:
            case.max_offer_current = max_offer
        if walk_away is not None:
            case.walk_away_price = walk_away
        if notes is not None:
            case.status_summary = notes
        return case

    # ------------------------------------------------------------------
    # Due diligence
    # ------------------------------------------------------------------

    @staticmethod
    async def add_due_diligence(
        db: AsyncSession,
        property_id: str,
        category: str,
        title: str,
        severity: str = "important",
    ) -> DueDiligenceItem:
        """Add a new due diligence item for a property."""
        # Auto-link to an existing decision case if one exists
        case_result = await db.execute(
            select(DecisionCase).where(DecisionCase.property_id == property_id)
        )
        case = case_result.scalar_one_or_none()

        item = DueDiligenceItem(
            property_id=property_id,
            decision_case_id=case.id if case else None,
            category=category,
            title=title,
            severity=severity,
            status="open",
        )
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def list_due_diligence(
        db: AsyncSession,
        property_id: str,
        status: Optional[str] = None,
    ) -> list[DueDiligenceItem]:
        """List due diligence items for a property, optionally filtered by status."""
        query = (
            select(DueDiligenceItem)
            .where(DueDiligenceItem.property_id == property_id)
            .order_by(DueDiligenceItem.created_at.desc())
        )
        if status is not None:
            query = query.where(DueDiligenceItem.status == status)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update_due_diligence(
        db: AsyncSession,
        item_id: str,
        status: str,
        resolution_note: Optional[str] = None,
    ) -> DueDiligenceItem:
        """Update the status (and optional resolution note) of a due diligence item."""
        result = await db.execute(
            select(DueDiligenceItem).where(DueDiligenceItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"DueDiligenceItem {item_id} not found")
        item.status = status
        if resolution_note is not None:
            item.resolution_note = resolution_note
        return item

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    @staticmethod
    async def create_recommendation(
        db: AsyncSession,
        property_id: str,
        analyses: dict,
        decision_case_id: Optional[str] = None,
    ) -> RecommendationSnapshot:
        """Auto-generate a recommendation snapshot from the latest analysis results.

        ``analyses`` is expected to be the dict returned by
        ``AnalysisService.run_all`` (keys: financial, tax, investment, condition).
        """
        red_flags: list[str] = []
        unknowns: list[str] = []
        questions: list[str] = []

        # --- Extract signals from analyses ---
        financial = analyses.get("financial", {})
        condition = analyses.get("condition", {})
        investment = analyses.get("investment", {})

        # Condition red flags
        condition_score = condition.get("condition_score", 100.0)
        if condition_score < 60:
            red_flags.append(f"Property condition score is low ({condition_score:.0f}/100)")
        capex = condition.get("capex_forecast", {})
        if capex:
            total_capex = sum(v.get("estimated_cost", 0) for v in capex.values()) if isinstance(capex, dict) else 0
            if total_capex > 30_000:
                red_flags.append(f"Near-term capital expenditures estimated at ${total_capex:,.0f}")

        # Determine max offer and walk-away from financial data
        max_offer: float | None = None
        walk_away_price: float | None = None

        # Try to pull from scenarios in financial analysis
        scenarios = financial.get("scenarios", [])
        if scenarios:
            first_scenario = scenarios[0] if isinstance(scenarios, list) else None
            if first_scenario and isinstance(first_scenario, dict):
                monthly = first_scenario.get("monthly_payment")
                if monthly and monthly > 5_000:
                    red_flags.append(f"Monthly payment ${monthly:,.0f} exceeds $5,000 threshold")

        # If no components analyzed, flag it as unknown
        if condition.get("components_analyzed", 0) == 0:
            unknowns.append("No component/system data — condition assessment incomplete")

        # Standard questions when data is thin
        if not financial:
            unknowns.append("Financial analysis has not been run")
            questions.append("Request full financial analysis before making an offer")
        if not investment:
            unknowns.append("Investment analysis has not been run")

        questions.append("Confirm HOA fees and any pending special assessments")
        questions.append("Request seller's disclosure statement")
        questions.append("Verify property tax assessment vs. actual taxes paid")

        # Determine recommendation
        if len(red_flags) >= 3:
            recommendation = "pass"
            confidence = "medium"
        elif len(red_flags) >= 1:
            recommendation = "maybe"
            confidence = "medium"
        else:
            recommendation = "pursue"
            confidence = "low" if len(unknowns) >= 3 else "medium"

        # Collect analysis run IDs if available
        analysis_run_ids: list[str] = []
        run_result = await db.execute(
            select(AnalysisRun.id)
            .where(AnalysisRun.property_id == property_id)
            .order_by(AnalysisRun.computed_at.desc())
            .limit(10)
        )
        analysis_run_ids = [row[0] for row in run_result.all()]

        reasoning_parts = []
        if red_flags:
            reasoning_parts.append(f"Red flags: {'; '.join(red_flags)}")
        if unknowns:
            reasoning_parts.append(f"Unknowns: {'; '.join(unknowns)}")
        reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Initial assessment — more data needed."

        snapshot = RecommendationSnapshot(
            property_id=property_id,
            decision_case_id=decision_case_id,
            pursue_recommendation=recommendation,
            max_offer=max_offer,
            walk_away_price=walk_away_price,
            main_red_flags=red_flags,
            unresolved_unknowns=unknowns,
            top_questions=questions,
            analysis_run_ids=analysis_run_ids,
            confidence=confidence,
            reasoning=reasoning,
        )
        db.add(snapshot)
        await db.flush()
        return snapshot

    @staticmethod
    async def get_recommendations(
        db: AsyncSession,
        property_id: str,
    ) -> list[RecommendationSnapshot]:
        """Get all recommendation snapshots for a property, newest first."""
        result = await db.execute(
            select(RecommendationSnapshot)
            .where(RecommendationSnapshot.property_id == property_id)
            .order_by(RecommendationSnapshot.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Decision packet
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_decision_packet(
        db: AsyncSession,
        property_id: str,
    ) -> dict:
        """Generate the standard 7-section decision packet for a property.

        Sections:
          1. QUICK TAKE — pursue/maybe/pass + 3 bullets
          2. PRICE VIEW — list vs comps vs assessment, max offer, walk-away
          3. MONTHLY COST VIEW — all-in, cash to close, stress-tested
          4. HIDDEN COST VIEW — capex, unknowns, permit concerns
          5. HOA / COMMUNITY VIEW
          6. CURRENT HOME IMPACT — sell vs rent effect
          7. NEXT ACTIONS — auto-generated from due diligence items
        """
        # Fetch decision case
        case = await DecisionService.get_case(db, property_id)

        # Fetch latest recommendation
        recs = await DecisionService.get_recommendations(db, property_id)
        latest_rec = recs[0] if recs else None

        # Fetch latest analysis runs by type.
        # ai_interpretation = AI Pass 2 output (pursue/maybe/pass + pros/cons)
        # ai_extraction    = AI Pass 1 output (components + red flags)
        analyses: dict[str, dict] = {}
        for analysis_type in (
            "financial", "tax", "investment", "condition", "offer", "stress",
            "ai_interpretation", "ai_extraction",
        ):
            run_result = await db.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.property_id == property_id,
                    AnalysisRun.analysis_type == analysis_type,
                )
                .order_by(AnalysisRun.computed_at.desc())
                .limit(1)
            )
            run = run_result.scalar_one_or_none()
            if run is not None:
                analyses[analysis_type] = run.output_json

        # Fetch open due diligence items
        dd_items = await DecisionService.list_due_diligence(db, property_id)

        financial = analyses.get("financial", {})
        condition = analyses.get("condition", {})
        offer = analyses.get("offer", {})
        stress = analyses.get("stress", {})
        tax = analyses.get("tax", {})
        ai_interp = analyses.get("ai_interpretation", {}) or {}
        ai_extract = analyses.get("ai_extraction", {}) or {}

        # --- Section 1: QUICK TAKE ---
        # Priority order (most authoritative first):
        #   1. AI Pass 2 (ai_interpretation) — quick_take + pros/cons/red_flags
        #      straight from Claude's synthesis of ALL available data.
        #      This is what the pipeline produces for every property on
        #      ingest and is the source of truth when available.
        #   2. RecommendationSnapshot — only populated when DecisionService
        #      .create_recommendation is called manually.
        #   3. DecisionCase.decision_status — set manually via the
        #      /properties/{id}/decision endpoint.
        #   4. Hardcoded "maybe" + explanation.
        if ai_interp.get("quick_take") or ai_interp.get("top_3_pros") or ai_interp.get("top_3_cons"):
            recommendation = (ai_interp.get("quick_take") or "maybe").lower()
            # Assemble bullets from cons + red flags (cons = what buyer
            # should be cautious about), then fall back to pros if empty.
            bullets: list[str] = []
            for c in (ai_interp.get("top_3_cons") or [])[:3]:
                if isinstance(c, str) and c.strip():
                    bullets.append(c.strip())
            if len(bullets) < 3:
                for rf in (ai_interp.get("red_flags") or []):
                    if isinstance(rf, str) and rf.strip() and rf not in bullets:
                        bullets.append(rf.strip())
                        if len(bullets) >= 3:
                            break
            if not bullets and ai_interp.get("one_line_summary"):
                bullets = [ai_interp["one_line_summary"]]
            if not bullets:
                bullets = ["See AI Analysis tab for details"]
        elif latest_rec:
            recommendation = latest_rec.pursue_recommendation
            bullets = (latest_rec.main_red_flags or [])[:3]
            if len(bullets) < 3 and latest_rec.unresolved_unknowns:
                bullets.extend(latest_rec.unresolved_unknowns[:3 - len(bullets)])
        elif case:
            recommendation = case.decision_status
            bullets = [case.status_summary or "No analysis run yet"]
        elif ai_extract.get("red_flags"):
            # Pass 1 ran but Pass 2 didn't — surface what we have.
            recommendation = "maybe"
            rf = ai_extract.get("red_flags") or []
            bullets = [
                (r.get("description") or r.get("issue") or str(r))[:150]
                if isinstance(r, dict) else str(r)[:150]
                for r in rf[:3]
            ]
        else:
            recommendation = "maybe"
            bullets = ["Run the pipeline to generate an AI recommendation"]

        quick_take = {
            "recommendation": recommendation,
            "bullets": bullets[:3],
        }

        # --- Section 2: PRICE VIEW ---
        max_bid = offer.get("max_bid", {})
        walk_away = offer.get("walk_away_price", {})
        price_view = {
            "list_price": financial.get("list_price") or (
                max_bid.get("list_price")
            ),
            "comp_estimate": None,  # populated when comp analysis exists
            "assessment_value": None,  # populated from assessment model
            "max_offer": max_bid.get("max_price") or (
                case.max_offer_current if case else None
            ),
            "walk_away_price": walk_away.get("walk_away_price") or (
                case.walk_away_price if case else None
            ),
        }

        # --- Section 3: MONTHLY COST VIEW ---
        scenarios = financial.get("scenarios", [])
        first_scenario = scenarios[0] if scenarios else {}
        stress_scenarios = stress.get("rate_stress", [])
        worst_stress = stress_scenarios[-1] if stress_scenarios else {}

        monthly_cost = {
            "all_in_monthly": first_scenario.get("monthly_payment"),
            "cash_to_close": first_scenario.get("cash_to_close"),
            "stress_tested_monthly": worst_stress.get("monthly_payment"),
            "breakdown": {
                "principal_interest": first_scenario.get("principal_interest"),
                "property_tax": first_scenario.get("property_tax"),
                "insurance": first_scenario.get("insurance"),
                "hoa": first_scenario.get("hoa"),
            } if first_scenario else None,
        }

        # --- Section 4: HIDDEN COST VIEW ---
        capex_forecast = condition.get("capex_forecast", {})
        capex_items = []
        if isinstance(capex_forecast, dict):
            for component, details in capex_forecast.items():
                if isinstance(details, dict):
                    capex_items.append({
                        "component": component,
                        "estimated_cost": details.get("estimated_cost"),
                        "years_remaining": details.get("years_remaining"),
                    })

        permit_concerns: list[str] = []
        # DD items in the permit category that are unresolved
        for item in dd_items:
            if item.category == "permit" and item.status not in ("resolved",):
                permit_concerns.append(item.title)

        unknowns = []
        if latest_rec and latest_rec.unresolved_unknowns:
            unknowns = latest_rec.unresolved_unknowns

        hidden_cost = {
            "capex_items": capex_items,
            "unknowns": unknowns,
            "permit_concerns": permit_concerns,
        }

        # --- Section 5: HOA / COMMUNITY VIEW ---
        community_view = {
            "hoa_monthly": first_scenario.get("hoa"),
            "hoa_health": None,  # populated when HOA financial snapshot exists
            "community_notes": [],
        }

        # --- Section 6: CURRENT HOME IMPACT ---
        sell_vs_rent = tax.get("sell_vs_rent_summary") if tax else None
        current_home_impact = {
            "sell_vs_rent_summary": sell_vs_rent,
            "net_monthly_delta": None,
            "details": tax.get("current_home_impact") if tax else None,
        }

        # --- Section 7: NEXT ACTIONS ---
        actions = []
        for item in dd_items:
            if item.status not in ("resolved",):
                actions.append({
                    "title": item.title,
                    "category": item.category,
                    "severity": item.severity,
                    "status": item.status,
                })

        # If no DD items, generate default next actions
        if not actions:
            actions = [
                {"title": "Run full analysis suite", "category": "general", "severity": "important", "status": "open"},
                {"title": "Schedule property tour", "category": "inspection", "severity": "important", "status": "open"},
                {"title": "Request seller disclosure", "category": "seller_question", "severity": "important", "status": "open"},
            ]

        next_actions = {"actions": actions}

        return {
            "property_id": property_id,
            "decision_case_id": case.id if case else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quick_take": quick_take,
            "price_view": price_view,
            "monthly_cost": monthly_cost,
            "hidden_cost": hidden_cost,
            "community_view": community_view,
            "current_home_impact": current_home_impact,
            "next_actions": next_actions,
        }
