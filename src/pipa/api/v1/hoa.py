"""HOA endpoints — community info, fee history, and management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.community import Community, PropertyCommunityMembership
from pipa.models.hoa import HOAFeeHistory
from pipa.models.property import Property
from pipa.schemas.hoa import HOAFeeCreate, HOAFeeResponse, HOASummary, HOAUpdate

router = APIRouter(tags=["hoa"])


async def _verify_property(db: AsyncSession, property_id: str) -> Property:
    """Return the property or raise 404."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


async def _get_community_for_property(
    db: AsyncSession,
    property_id: str,
) -> tuple[Community | None, PropertyCommunityMembership | None]:
    """Return the current community and membership for a property."""
    result = await db.execute(
        select(PropertyCommunityMembership)
        .where(
            PropertyCommunityMembership.property_id == property_id,
            PropertyCommunityMembership.is_current == True,  # noqa: E712
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return None, None

    comm_result = await db.execute(
        select(Community).where(Community.id == membership.community_id)
    )
    community = comm_result.scalar_one_or_none()
    return community, membership


@router.get(
    "/properties/{property_id}/hoa",
    response_model=HOASummary,
)
async def get_hoa(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get HOA summary for a property."""
    await _verify_property(db, property_id)
    community, membership = await _get_community_for_property(db, property_id)

    if community is None:
        return HOASummary(is_member=False)

    # Get latest fee
    fee_result = await db.execute(
        select(HOAFeeHistory)
        .where(HOAFeeHistory.community_id == community.id)
        .order_by(HOAFeeHistory.effective_date.desc())
        .limit(1)
    )
    latest_fee = fee_result.scalar_one_or_none()

    return HOASummary(
        community_id=community.id,
        community_name=community.name,
        community_type=community.community_type,
        management_company=community.management_company,
        current_monthly_fee=latest_fee.monthly_amount if latest_fee else None,
        is_member=True,
    )


@router.put(
    "/properties/{property_id}/hoa",
    response_model=HOASummary,
)
async def update_hoa(
    property_id: str,
    body: HOAUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Set or update the HOA community link for a property.

    Creates the community if it does not already exist, then links it
    to the property.
    """
    await _verify_property(db, property_id)

    # Check if community already exists by name
    comm_result = await db.execute(
        select(Community).where(Community.name == body.community_name)
    )
    community = comm_result.scalar_one_or_none()

    if community is None:
        community = Community(
            name=body.community_name,
            community_type=body.community_type,
            management_company=body.management_company,
        )
        db.add(community)
        await db.flush()
    else:
        # Update existing
        community.community_type = body.community_type
        if body.management_company is not None:
            community.management_company = body.management_company

    # Mark old memberships as not current
    old_result = await db.execute(
        select(PropertyCommunityMembership).where(
            PropertyCommunityMembership.property_id == property_id,
            PropertyCommunityMembership.is_current == True,  # noqa: E712
        )
    )
    for old in old_result.scalars().all():
        old.is_current = False

    # Create new membership
    membership = PropertyCommunityMembership(
        property_id=property_id,
        community_id=community.id,
        is_current=True,
    )
    db.add(membership)
    await db.flush()

    return HOASummary(
        community_id=community.id,
        community_name=community.name,
        community_type=community.community_type,
        management_company=community.management_company,
        is_member=True,
    )


@router.get(
    "/properties/{property_id}/hoa/fees",
    response_model=list[HOAFeeResponse],
)
async def get_hoa_fees(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get HOA fee history for a property's community."""
    await _verify_property(db, property_id)
    community, _ = await _get_community_for_property(db, property_id)

    if community is None:
        return []

    result = await db.execute(
        select(HOAFeeHistory)
        .where(HOAFeeHistory.community_id == community.id)
        .order_by(HOAFeeHistory.effective_date.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/properties/{property_id}/hoa/fees",
    response_model=HOAFeeResponse,
    status_code=201,
)
async def add_hoa_fee(
    property_id: str,
    body: HOAFeeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add an HOA fee history entry for a property's community."""
    await _verify_property(db, property_id)
    community, _ = await _get_community_for_property(db, property_id)

    if community is None:
        raise HTTPException(
            status_code=400,
            detail="Property is not linked to an HOA community. Use PUT /properties/{id}/hoa first.",
        )

    fee = HOAFeeHistory(
        community_id=community.id,
        effective_date=body.effective_date,
        monthly_amount=body.monthly_amount,
        special_assessment=body.special_assessment,
    )
    db.add(fee)
    await db.flush()
    return fee
