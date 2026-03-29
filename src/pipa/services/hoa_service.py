"""HOA / community association service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.analysis.hoa import (
    analyze_fee_trend,
    analyze_resale_friction,
    score_hoa_risk,
    score_reserve_health,
)
from pipa.models.community import Community, PropertyCommunityMembership
from pipa.models.hoa import HOAFeeHistory, HOAFinancialSnapshot, HOARule

logger = logging.getLogger(__name__)


class HOAService:
    """Manages community associations, fee history, and HOA analysis."""

    # ------------------------------------------------------------------
    # Community lookup
    # ------------------------------------------------------------------

    @staticmethod
    async def get_community(
        db: AsyncSession,
        property_id: str,
    ) -> Optional[Community]:
        """Find the community associated with a property.

        Uses ``PropertyCommunityMembership`` to resolve the link.
        Returns the current community, or None if none is linked.
        """
        result = await db.execute(
            select(PropertyCommunityMembership).where(
                PropertyCommunityMembership.property_id == property_id,
                PropertyCommunityMembership.is_current.is_(True),
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            return None

        comm_result = await db.execute(
            select(Community).where(Community.id == membership.community_id)
        )
        return comm_result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Community create / update
    # ------------------------------------------------------------------

    @staticmethod
    async def create_or_update_community(
        db: AsyncSession,
        property_id: str,
        community_data: dict,
    ) -> Community:
        """Create or update a community and link it to the property.

        *community_data* should contain:
        - ``name``: community name (required)
        - ``community_type``: HOA, condo, coop, civic_association
        - ``management_company``: optional
        - ``county``: optional

        If the property already has a current community with the same
        name, that community is updated. Otherwise a new community is
        created and linked.
        """
        name = community_data["name"]

        # Check for existing community by name
        existing_result = await db.execute(
            select(Community).where(Community.name == name)
        )
        community = existing_result.scalar_one_or_none()

        if community is not None:
            # Update fields if provided
            if "community_type" in community_data:
                community.community_type = community_data["community_type"]
            if "management_company" in community_data:
                community.management_company = community_data["management_company"]
            if "county" in community_data:
                community.county = community_data["county"]
        else:
            community = Community(
                name=name,
                community_type=community_data.get("community_type", "HOA"),
                management_company=community_data.get("management_company"),
                county=community_data.get("county"),
            )
            db.add(community)
            await db.flush()

        # Ensure membership link exists
        membership_result = await db.execute(
            select(PropertyCommunityMembership).where(
                PropertyCommunityMembership.property_id == property_id,
                PropertyCommunityMembership.community_id == community.id,
            )
        )
        membership = membership_result.scalar_one_or_none()

        if membership is None:
            membership = PropertyCommunityMembership(
                property_id=property_id,
                community_id=community.id,
                is_current=True,
                effective_from=datetime.now(timezone.utc),
            )
            db.add(membership)
            await db.flush()

        logger.info(
            "Linked property %s to community %s (%s)",
            property_id,
            community.id,
            name,
        )
        return community

    # ------------------------------------------------------------------
    # Fee history
    # ------------------------------------------------------------------

    @staticmethod
    async def add_fee_record(
        db: AsyncSession,
        community_id: str,
        fee_data: dict,
    ) -> HOAFeeHistory:
        """Add an HOA fee history record.

        *fee_data* should contain:
        - ``effective_date``: datetime or ISO string
        - ``monthly_amount``: float
        - ``special_assessment``: float (optional)
        """
        effective_date = fee_data["effective_date"]
        if isinstance(effective_date, str):
            effective_date = datetime.fromisoformat(effective_date)

        fee = HOAFeeHistory(
            community_id=community_id,
            effective_date=effective_date,
            monthly_amount=fee_data["monthly_amount"],
            special_assessment=fee_data.get("special_assessment"),
        )
        db.add(fee)
        await db.flush()
        return fee

    @staticmethod
    async def get_fee_history(
        db: AsyncSession,
        community_id: str,
    ) -> list[HOAFeeHistory]:
        """Get all fee history records for a community, newest first."""
        result = await db.execute(
            select(HOAFeeHistory)
            .where(HOAFeeHistory.community_id == community_id)
            .order_by(HOAFeeHistory.effective_date.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # HOA analysis
    # ------------------------------------------------------------------

    @staticmethod
    async def analyze_hoa(
        db: AsyncSession,
        property_id: str,
    ) -> dict:
        """Run comprehensive HOA analysis for a property.

        Combines fee trend analysis, reserve health scoring, risk
        scoring, and resale friction analysis.

        Returns a dict with:
        - ``community_name``: name of the HOA or None
        - ``fee_trend``: output of ``analyze_fee_trend``
        - ``reserve_health``: 0-100 score
        - ``risk_score``: 1-10 score
        - ``resale_friction``: output of ``analyze_resale_friction``
        - ``current_monthly_fee``: latest fee amount or None
        """
        community = await HOAService.get_community(db, property_id)
        if community is None:
            return {
                "community_name": None,
                "fee_trend": {},
                "reserve_health": 100.0,
                "risk_score": 1,
                "resale_friction": {},
                "current_monthly_fee": None,
            }

        # Load fee history
        fees = await HOAService.get_fee_history(db, community.id)

        # Build fee_history dicts for analysis (sorted oldest first)
        fee_dicts = sorted(
            [
                {
                    "year": f.effective_date.year,
                    "monthly_fee": f.monthly_amount,
                }
                for f in fees
            ],
            key=lambda d: d["year"],
        )

        fee_trend = analyze_fee_trend(fee_dicts) if fee_dicts else {}

        # Current monthly fee
        current_fee = fees[0].monthly_amount if fees else None

        # Load financial snapshot for reserve health
        fin_result = await db.execute(
            select(HOAFinancialSnapshot)
            .where(HOAFinancialSnapshot.community_id == community.id)
            .order_by(HOAFinancialSnapshot.fiscal_year.desc())
        )
        fin_snapshot = fin_result.scalar_one_or_none()

        reserve_health = 100.0
        if fin_snapshot and fin_snapshot.reserve_balance is not None:
            annual_expenses = fin_snapshot.expenses or 0.0
            reserve_health = score_reserve_health(
                fin_snapshot.reserve_balance, annual_expenses
            )

        # Special assessments from fee history
        special_assessments = [
            {"year": f.effective_date.year, "amount": f.special_assessment}
            for f in fees
            if f.special_assessment and f.special_assessment > 0
        ]

        # Load rules for resale friction
        rules_result = await db.execute(
            select(HOARule).where(HOARule.community_id == community.id)
        )
        rules = list(rules_result.scalars().all())

        rules_dict: dict = {}
        for rule in rules:
            category = rule.category.lower()
            if "rental" in category:
                rules_dict["rental_restriction"] = True
            if "pet" in category:
                rules_dict["pet_restriction"] = True
            if "age" in category or "55" in rule.description:
                rules_dict["age_restriction"] = True
            if "exterior" in category or "modification" in category:
                rules_dict["exterior_modification_approval"] = True

        resale_friction = analyze_resale_friction(rules_dict) if rules_dict else {}

        # Compute risk score
        risk_score = score_hoa_risk(
            fee_trend=fee_trend or {"annual_increase_rate": 0.0},
            reserve_health=reserve_health,
            special_assessments=special_assessments,
        )

        result = {
            "community_name": community.name,
            "fee_trend": fee_trend,
            "reserve_health": reserve_health,
            "risk_score": risk_score,
            "resale_friction": resale_friction,
            "current_monthly_fee": current_fee,
        }

        logger.info(
            "HOA analysis for property %s: risk=%d, reserve_health=%.1f",
            property_id,
            risk_score,
            reserve_health,
        )
        return result
