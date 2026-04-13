"""Property CRUD and ingest endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pipa.core.dependencies import get_config, get_db
from pipa.models.decision import DecisionCase
from pipa.models.property import AddressHistory, Property
from pipa.models.user import WatchlistEntry
from pipa.schemas.property import (
    PropertyCreate,
    PropertyIngestRequest,
    PropertyIngestResponse,
    PropertyResponse,
    PropertySummary,
)
from pipa.utils.geo import detect_county, normalize_address, parse_address

logger = logging.getLogger(__name__)

router = APIRouter(tags=["properties"])


@router.post("/properties", response_model=PropertyResponse, status_code=201)
async def create_property(body: PropertyCreate, db: AsyncSession = Depends(get_db)):
    """Create a new property with its address."""
    addr = body.address
    parsed = parse_address(f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}")

    # Detect county if not provided
    county = addr.county or detect_county(addr.city, addr.state, addr.zip_code)

    # Create property
    prop = Property(property_type=body.property_type)
    db.add(prop)
    await db.flush()  # Get the ID

    # Create address
    normalized = normalize_address(f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}")
    address = AddressHistory(
        property_id=prop.id,
        address_type="situs",
        normalized_address=normalized,
        raw_address=f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}",
        city=addr.city,
        state=addr.state,
        zip_code=addr.zip_code,
        county=county,
        latitude=addr.latitude,
        longitude=addr.longitude,
        is_current=True,
        valid_from=datetime.now(timezone.utc),
    )
    db.add(address)
    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses), selectinload(Property.parcel_identifiers))
        .where(Property.id == prop.id)
    )
    prop = result.scalar_one()

    return prop


@router.get("/properties", response_model=list[PropertySummary])
async def list_properties(db: AsyncSession = Depends(get_db)):
    """List all properties."""
    result = await db.execute(
        select(Property).options(selectinload(Property.addresses)).order_by(Property.created_at.desc())
    )
    properties = result.scalars().all()

    # Fetch watchlist stages and decision cases in bulk, keyed by property_id.
    # WatchlistEntry is per-user; if multiple users track the same property we
    # just pick whichever row comes back first — PIPA is effectively single-user
    # today, so this matches how the rest of the code treats watchlist data.
    watchlist_rows = (await db.execute(select(WatchlistEntry))).scalars().all()
    watchlist_by_property: dict[str, str] = {}
    for w in watchlist_rows:
        watchlist_by_property.setdefault(w.property_id, w.stage)

    decision_rows = (await db.execute(select(DecisionCase))).scalars().all()
    decision_by_property: dict[str, DecisionCase] = {
        d.property_id: d for d in decision_rows
    }

    summaries = []
    for p in properties:
        current_addr = None
        county = None
        for a in p.addresses:
            if a.is_current and a.address_type == "situs":
                current_addr = a.normalized_address
                county = a.county
                break
        dc = decision_by_property.get(p.id)
        summaries.append(
            PropertySummary(
                id=p.id,
                property_type=p.property_type,
                address=current_addr,
                county=county,
                created_at=p.created_at,
                watchlist_stage=watchlist_by_property.get(p.id),
                decision_status=dc.decision_status if dc else None,
                decision_stage=dc.stage if dc else None,
            )
        )
    return summaries


@router.get("/properties/{property_id}", response_model=PropertyResponse)
async def get_property(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get a property by ID with all addresses and identifiers."""
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.addresses), selectinload(Property.parcel_identifiers))
        .where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/properties/{property_id}/listing-data")
async def get_listing_data(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get the scraped listing data (from Zillow/Redfin GraphQL) for a property."""
    from pipa.models.listing_page import ListingPageSnapshot

    result = await db.execute(
        select(ListingPageSnapshot)
        .where(ListingPageSnapshot.property_id == property_id)
        .order_by(ListingPageSnapshot.scraped_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        return {"property_id": property_id, "listing_data": None, "source": None}

    return {
        "property_id": property_id,
        "listing_data": snap.parsed_fields or {},
        "source": snap.source_site,
        "scraped_at": snap.scraped_at.isoformat() if snap.scraped_at else None,
        "parser_version": snap.parser_version,
    }


@router.get("/properties/{property_id}/analysis-results")
async def get_analysis_results(property_id: str, db: AsyncSession = Depends(get_db)):
    """Get the latest pipeline analysis results for a property."""
    from pipa.models.analysis_models import AnalysisRun

    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.property_id == property_id)
        .order_by(AnalysisRun.computed_at.desc())
    )
    runs = result.scalars().all()

    results = {}
    for run in runs:
        # Keep only the latest of each type
        if run.analysis_type not in results:
            results[run.analysis_type] = {
                "analysis_type": run.analysis_type,
                "output": run.output_json,
                "computed_at": run.computed_at.isoformat() if run.computed_at else None,
                "ruleset_version": run.ruleset_version,
            }

    return {"property_id": property_id, "analyses": results}


@router.delete("/properties/{property_id}", status_code=204)
async def delete_property(property_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a property and ALL associated data."""
    from sqlalchemy import delete as sql_delete
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Delete pipeline_task_run first (references pipeline_run)
    await db.execute(
        text("""DELETE FROM pipeline_task_run WHERE pipeline_run_id IN
                (SELECT id FROM pipeline_run WHERE property_id = :pid)"""),
        {"pid": property_id},
    )

    # Delete from ALL tables with property_id FK
    tables_with_property_fk = [
        "address_history", "alert_event", "analysis_run",
        "assessment_snapshot", "component_system", "decision_case",
        "deed_record", "development_case", "document",
        "due_diligence_item", "evidence_item", "extracted_fact",
        "geometry_snapshot", "hazard_profile", "insurance_quote",
        "listing_episode", "listing_page_snapshot", "mortgage_quote",
        "overlay_intersection", "parcel", "parcel_event",
        "parcel_identifier", "permit_record", "photo_asset",
        "pipeline_run", "plat_record", "property_community_membership",
        "property_note", "property_tag", "recommendation_snapshot",
        "refresh_job", "repair_estimate", "sale_event",
        "source_record", "watchlist_entry", "zoning_case", "zoning_record",
    ]
    for table_name in tables_with_property_fk:
        try:
            await db.execute(
                text(f"DELETE FROM {table_name} WHERE property_id = :pid"),
                {"pid": property_id},
            )
        except Exception:
            pass

    # Manual component-year overrides live in app_setting (no FK to
    # property), so the table loop above misses them. If a property_id
    # is ever reused, surviving overrides would silently apply at rank
    # 100 to the next property — the worst kind of ghost data.
    await db.execute(
        text("DELETE FROM app_setting WHERE key LIKE :k"),
        {"k": f"component_override.{property_id}.%"},
    )

    await db.delete(prop)


@router.post("/properties/ingest", response_model=PropertyIngestResponse, status_code=201)
async def ingest_property(
    body: PropertyIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a property from a listing URL or manual address.

    If a URL is provided, scrapes the listing page and creates the property
    record immediately, then schedules the slow auto-chain (county scrape,
    schools, quick comp, AI pipeline) as a background task so the response
    returns in seconds rather than minutes.
    """
    from pipa.services.listing_ingest import ListingIngestService

    config = get_config()
    logger.info("Ingest request: url=%s, address=%s, type=%s",
                body.url, body.address, body.property_type)
    logger.debug("Config: storage_dir=%s, headless=%s",
                config.storage_dir, config.scrapers.playwright_headless)
    service = ListingIngestService(
        storage_dir=config.storage_dir,
        headless=config.scrapers.playwright_headless,
    )

    try:
        if body.url:
            # Validate URL source before attempting scrape
            source = service.detect_source(body.url)
            logger.debug("Detected source: %s", source)
            if source == "unknown":
                raise HTTPException(
                    status_code=400,
                    detail="URL must be from zillow.com, redfin.com, or realtor.com",
                )

            # Instant-response path: create a placeholder property from the
            # URL slug, return 201 in ~100ms, then run the full scrape +
            # county + schools + comps + AI pipeline in the background.
            prop = await service.create_placeholder_from_url(db, body.url)
            property_id_for_bg = prop.id
            url_for_bg = body.url

            # Commit so the placeholder is durable + visible to other
            # connections (e.g. the property list refresh) before we hand
            # off to the background task.
            await db.commit()

            background_tasks.add_task(
                ListingIngestService.run_post_ingest_chain,
                property_id_for_bg,
                url_for_bg,
                source,
            )

            return PropertyIngestResponse(
                property=PropertyResponse.model_validate(prop),
                snapshot=None,  # snapshot will be created by the bg task
            )
        elif body.address:
            # Manual address entry
            addr = body.address
            address_str = f"{addr.street}, {addr.city}, {addr.state} {addr.zip_code}"
            prop = await service.ingest_from_address(
                db, address_str, property_type=body.property_type
            )
            return PropertyIngestResponse(
                property=PropertyResponse.model_validate(prop),
                snapshot=None,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="At least one of 'url' or 'address' must be provided",
            )
    except ValueError as e:
        logger.warning("Ingest ValueError: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to ingest property: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to ingest property from listing: {exc}")
    finally:
        await service.close()
