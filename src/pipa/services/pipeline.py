"""Property analysis pipeline — the 7-step orchestrator.

Enforces the correct execution order:
  0. Ingest (scrape)
  1. Deterministic structured parse
  2. AI PASS 1 (unstructured extraction → evidence items)
  3. Deterministic resolver (source ranking → canonical values)
  4. Pure math (financial, condition, offer, stress — on canonical values)
  5. Deterministic warning engine (blockers, flags, pursue signal)
  6. AI PASS 2 (interpretation, narrative, questions)
  7. Decision packet assembly

AI PASS 1 feeds evidence. Resolver decides truth. Math computes on truth.
Warning engine flags issues. AI PASS 2 explains results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PropertyPipeline:
    """Orchestrates the full property analysis pipeline."""

    @staticmethod
    async def run_full_pipeline(
        db: AsyncSession,
        property_id: str,
        listing_data: dict,
        county_data: dict | None = None,
        description: str = "",
        current_home: dict | None = None,
        max_monthly_payment: float = 8000,
        max_cash_at_closing: float = 300000,
        assessment_markup_pct: float = 7.0,
    ) -> dict:
        """Run the complete 7-step pipeline.

        Args:
            listing_data: structured data from Zillow/Redfin scrape
                (price, beds, baths, sqft, year_built, hoa, zestimate, etc.)
            county_data: structured data from county scrape
                (sqft_above_grade, basement, baths, year_built, assessed, etc.)
            description: raw listing description text
            current_home: current home data for sell-vs-rent analysis
            max_monthly_payment: buyer's payment ceiling
            max_cash_at_closing: buyer's cash ceiling
            assessment_markup_pct: % above assessment for market estimate

        Returns:
            Complete analysis result dict with all 7 steps' outputs.
        """
        result: dict[str, Any] = {
            "_pipeline_version": "1.0.0",
            "_property_id": property_id,
            "_started_at": datetime.now(timezone.utc).isoformat(),
        }

        # ==============================================================
        # STEP 1: DETERMINISTIC STRUCTURED PARSE
        # ==============================================================
        # (Already done by scrapers — listing_data and county_data
        #  are the parsed outputs. This step is a no-op in the pipeline
        #  but we record what we have.)
        result["step1_sources"] = {
            "listing_fields": len(listing_data),
            "county_fields": len(county_data) if county_data else 0,
            "has_description": bool(description),
        }

        # ==============================================================
        # STEP 2: AI PASS 1 — UNSTRUCTURED EXTRACTION TO EVIDENCE
        # ==============================================================
        ai_extracted = {}
        if description:
            try:
                from pipa.services.ai_extraction import extract_components_from_text

                components = await extract_components_from_text(description)
                if components:
                    ai_extracted["components"] = components
                    logger.info("AI PASS 1: extracted %d components from description", len(components))
            except Exception:
                logger.exception("AI PASS 1 failed — continuing without AI extraction")

        result["step2_ai_extraction"] = ai_extracted

        # ==============================================================
        # STEP 3: DETERMINISTIC RESOLVER
        # ==============================================================
        canonical, conflicts, unknowns = _resolve_canonical(
            listing_data, county_data, ai_extracted
        )
        result["step3_canonical"] = canonical
        result["step3_conflicts"] = conflicts
        result["step3_unknowns"] = unknowns

        # ==============================================================
        # STEP 4: PURE MATH
        # ==============================================================
        math_results = _run_all_math(
            canonical,
            current_home=current_home,
            max_monthly_payment=max_monthly_payment,
            max_cash_at_closing=max_cash_at_closing,
            assessment_markup_pct=assessment_markup_pct,
        )
        result["step4_math"] = math_results

        # ==============================================================
        # STEP 5: DETERMINISTIC WARNING ENGINE
        # ==============================================================
        warnings = _generate_warnings(canonical, conflicts, unknowns, math_results)
        result["step5_warnings"] = warnings

        # ==============================================================
        # STEP 6: AI PASS 2 — INTERPRETATION / COPILOT
        # ==============================================================
        try:
            from pipa.services.ai_extraction import generate_property_summary

            ai_summary = await generate_property_summary(
                property_data=canonical,
                county_data=county_data,
                price_benchmarks=math_results.get("price_benchmarks"),
            )
            result["step6_ai_interpretation"] = ai_summary
        except Exception:
            logger.exception("AI PASS 2 failed — continuing without AI interpretation")
            result["step6_ai_interpretation"] = {}

        # ==============================================================
        # STEP 7: DECISION PACKET ASSEMBLY
        # ==============================================================
        result["step7_decision_packet"] = _assemble_decision_packet(
            canonical, math_results, warnings, ai_extracted,
            result.get("step6_ai_interpretation", {}),
        )

        result["_completed_at"] = datetime.now(timezone.utc).isoformat()
        return result


# ======================================================================
# Step 3: Deterministic Resolver
# ======================================================================


def _resolve_canonical(
    listing: dict,
    county: dict | None,
    ai_extracted: dict,
) -> tuple[dict, list[dict], list[str]]:
    """Merge all sources into canonical values using confidence ranking.

    Source priority (highest to lowest):
    1. County records (rank 90)
    2. Structured listing fields (rank 40)
    3. AI-extracted from description (rank 30)
    4. Defaults from year_built (rank 10)

    Returns:
        (canonical_input_set, conflict_list, unresolved_unknowns)
    """
    canonical: dict[str, Any] = {}
    conflicts: list[dict] = []
    unknowns: list[str] = []

    county = county or {}

    # Helper: set canonical value, tracking source
    def set_canonical(field: str, value: Any, source: str, rank: int):
        existing = canonical.get(f"_source_{field}")
        if existing and existing["rank"] >= rank:
            # Check for conflict
            if str(canonical.get(field)) != str(value) and value is not None:
                conflicts.append({
                    "field": field,
                    "canonical_value": canonical.get(field),
                    "canonical_source": existing["source"],
                    "conflicting_value": value,
                    "conflicting_source": source,
                })
            return  # Keep higher-ranked source
        if value is not None:
            canonical[field] = value
            canonical[f"_source_{field}"] = {"source": source, "rank": rank}

    # --- County data (rank 90) ---
    county_map = {
        "sqft_above_grade": ("sqft_above_grade", 90),
        "year_built": ("year_built", 90),
        "full_baths": ("full_baths", 90),
        "half_baths": ("half_baths", 90),
        "basement_total_sqft": ("basement_total_sqft", 90),
        "basement_finished_sqft": ("basement_finished_sqft", 90),
        "basement_entrance": ("basement_entrance", 90),
        "condition": ("condition", 90),
        "grade": ("grade", 90),
        "style": ("style", 90),
        "model": ("model", 90),
        "roof_type": ("roof_type", 90),
        "roof_material": ("roof_material", 90),
        "heating_ac": ("heating_ac", 90),
        "fireplaces": ("fireplaces", 90),
        "stories": ("stories", 90),
        "foundation": ("foundation", 90),
        "exterior_wall": ("exterior_wall", 90),
        "lot_acres": ("lot_acres", 90),
        "assessed_total": ("assessed_total", 90),
        "assessed_land": ("assessed_land", 90),
        "assessed_building": ("assessed_building", 90),
        "subdivision": ("subdivision", 90),
        "parcel_id": ("parcel_id", 90),
        "primary_zoning": ("zoning", 90),
        "total_value": ("assessed_total", 90),
        "taxable_value": ("taxable_value", 90),
    }
    for county_key, (canonical_key, rank) in county_map.items():
        val = county.get(county_key)
        if val is not None and val != "" and val != "0":
            set_canonical(canonical_key, val, "county", rank)

    # --- Listing data (rank 40) ---
    listing_map = {
        "price": ("asking_price", 40),
        "beds": ("bedrooms", 40),
        "baths": ("bathrooms", 40),
        "sqft": ("sqft_listing", 40),
        "year_built": ("year_built", 40),
        "hoa": ("hoa_monthly", 40),
        "hoa_monthly": ("hoa_monthly", 40),
        "lot_sqft": ("lot_sqft", 40),
        "lot_acres": ("lot_acres", 40),
        "zestimate": ("zestimate", 40),
        "rent_zestimate": ("rent_zestimate", 40),
        "annual_tax": ("annual_tax", 40),
        "tax_assessed": ("tax_assessed_zillow", 40),
        "status": ("listing_status", 40),
        "dom": ("dom", 40),
        "days_on_zillow": ("dom", 40),
        "cdom": ("cdom", 40),
        "home_type": ("property_type", 40),
        "parcel_id": ("parcel_id", 40),
        "mls_id": ("mls_id", 40),
        "agent_name": ("listing_agent", 40),
        "brokerage": ("listing_brokerage", 40),
    }
    for listing_key, (canonical_key, rank) in listing_map.items():
        val = listing.get(listing_key)
        if val is not None and val != "":
            set_canonical(canonical_key, val, "listing", rank)

    # --- AI-extracted components (rank 30) ---
    # Normalize AI component names to canonical keys used by condition
    # scoring. Claude paraphrases wildly — we've seen variants like
    # "HVAC system (x2)", "HVAC system (both units)", "HVAC systems",
    # "heat pump x2", "central air conditioning", etc. Exact-key
    # matching is whack-a-mole. Instead we do substring matching:
    # check the raw name for ANY of the component's keywords and map
    # to the canonical short key. First match wins, so list more
    # specific categories before more generic ones (water_heater
    # before heater, etc.).
    _COMPONENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        # (canonical_key, substring patterns to look for in lowered raw name)
        # water_heater before hvac — "water heat" catches both "water
        # heater" and "water heating" (and also "heat pump water
        # heater", which correctly resolves to water_heater because
        # the pump is the heating element OF the water heater).
        ("water_heater", ("water_heater", "water heater", "water heat", "hot_water")),
        ("hvac",         ("hvac", "heat_pump", "heatpump", "heat pump",
                          "furnace", "central_air", "central air",
                          "air_conditioning", "air conditioning", "ac_unit",
                          "heating", "cooling")),
        ("roof",         ("roof",)),
        ("electrical_panel", ("electrical_panel", "electrical panel",
                              "breaker_box", "service_panel", "panel",
                              "electrical")),
        ("windows",      ("window",)),           # matches windows too
        ("appliances",   ("appliance",)),        # matches appliances too
        ("fence",        ("fence", "fencing")),
        ("siding",       ("siding", "exterior")),
        ("driveway",     ("driveway",)),
        ("garage_door",  ("garage_door", "garage door")),
        ("deck",         ("deck", "decking")),
        ("patio",        ("patio",)),
        ("kitchen",      ("kitchen",)),           # cabinets, countertops
        ("basement",     ("basement",)),
        ("sprinkler",    ("sprinkler", "irrigation")),
    ]

    def _canonical_component_key(raw: str) -> str:
        """Map a free-text AI component name to a canonical short key.

        'HVAC system (both units)' → 'hvac'
        'roof asphalt shingle'     → 'roof'
        'Quartz kitchen counters'  → 'kitchen'
        'Gazebo'                   → 'gazebo' (passthrough, no match)
        """
        low = raw.lower().replace("_", " ").strip()
        for canonical_key, patterns in _COMPONENT_KEYWORDS:
            for pat in patterns:
                pat_norm = pat.replace("_", " ")
                if pat_norm in low:
                    return canonical_key
        # No match — passthrough with spaces→underscores so we still
        # get a valid key, just not one the condition engine scores.
        return raw.lower().replace(" ", "_")

    for comp in ai_extracted.get("components", []):
        raw_name = comp.get("component", "") or ""
        component_name = _canonical_component_key(raw_name)
        year = comp.get("year")
        confidence = comp.get("confidence", "low")

        # Only use AI-extracted year if confidence is high and no county data exists
        rank = 35 if confidence == "high" else 30 if confidence == "medium" else 20
        if year:
            set_canonical(f"component_{component_name}_year", year, "ai_extracted", rank)

    # --- Compute derived fields ---
    # Bathrooms: county full+half → baths as X.5
    full = _to_int(canonical.get("full_baths"))
    half = _to_int(canonical.get("half_baths"))
    if full is not None:
        canonical["baths_canonical"] = full + (half or 0) * 0.5

    # Livable sqft: above_grade + finished basement
    above = _to_int(canonical.get("sqft_above_grade"))
    fin_bsmt = _to_int(canonical.get("basement_finished_sqft"))
    if above:
        canonical["sqft_livable"] = above + (fin_bsmt or 0)

    # Unfinished basement
    bsmt_total = _to_int(canonical.get("basement_total_sqft"))
    if bsmt_total and fin_bsmt is not None:
        canonical["basement_unfinished_sqft"] = bsmt_total - fin_bsmt

    # Sqft conflict check: listing vs county
    sqft_listing = _to_int(canonical.get("sqft_listing"))
    if above and sqft_listing and abs(sqft_listing - above) / max(above, 1) > 0.10:
        conflicts.append({
            "field": "sqft",
            "canonical_value": above,
            "canonical_source": "county (above-grade)",
            "conflicting_value": sqft_listing,
            "conflicting_source": "listing (may include basement)",
            "severity": "warning" if abs(sqft_listing - above) / above < 0.3 else "critical",
        })

    # ----------------------------------------------------------------
    # Pass-through: rich Zillow facts_and_features fields
    # ----------------------------------------------------------------
    # These preserve all the structured listing data (rooms, HVAC,
    # materials, HOA amenities, etc.) into canonical so the UI and
    # AI Pass 1 can read them. Where a field could clash with county
    # (roof_material, foundation, subdivision, stories), we keep both
    # under separate keys (suffix _listing) instead of letting the
    # ranked merge silently drop the listing version.
    LISTING_PASSTHROUGH = (
        # Construction
        "architectural_style", "property_subtype",
        "exterior_materials", "foundation_type", "zillow_condition",
        "is_new_construction", "builder_model", "builder_name",
        "levels", "stories",
        # HVAC / systems
        "heating_features", "heating_fuel",
        "cooling_features", "cooling_fuel",
        "appliances_included", "laundry_features",
        # Interior
        "interior_features", "flooring", "windows_features",
        "basement_features", "fireplaces_count", "fireplace_features",
        # Sqft
        "total_structure_area", "total_livable_area",
        "finished_above_ground", "finished_below_ground",
        # Exterior / lot
        "patio_porch", "pool_features", "fencing", "lot_features",
        "additional_structures", "lot_sqft_listing",
        # Parking
        "parking_total_spaces", "parking_features",
        "attached_garage_spaces", "uncovered_spaces",
        "covered_spaces", "carport_spaces",
        # HOA
        "has_hoa", "hoa_amenities", "hoa_services", "hoa_name",
        "hoa_frequency",
        # Community
        "security_features", "region",
        # Utilities
        "sewer", "water", "utilities", "electric",
        # Tax / financial
        "tax_assessed_value_listing", "annual_tax_listing",
        "price_per_sqft", "date_on_market",
        "listing_agreement", "ownership_type",
        # Identity
        "parcel_number", "zoning", "special_conditions",
        # Per-room data
        "rooms", "room_types",
        "main_level_bathrooms",
        # Accessibility
        "accessibility_features",
    )
    for k in LISTING_PASSTHROUGH:
        if listing.get(k) is not None and k not in canonical:
            canonical[k] = listing[k]

    # Fields that exist in BOTH listing and county under similar names —
    # store the listing version under a _listing suffix so the ranked
    # county value (already in canonical) is preserved AND the listing
    # value is available for AI cross-reference.
    listing_dual_map = {
        "roof_material": "roof_material_listing",
        "foundation_type": "foundation_listing",
        "subdivision": "subdivision_listing",
    }
    for src, dst in listing_dual_map.items():
        v = listing.get(src)
        if v is not None:
            canonical[dst] = v

    # ----------------------------------------------------------------
    # Deterministic cross-checks: listing facts vs county facts
    # These produce conflict entries when there's an exact, objective
    # mismatch (no fuzzy string compare). Qualitative comparisons
    # (roof_material strings, HVAC type wording) are left to the AI
    # validator.
    # ----------------------------------------------------------------

    # finished_above_ground (listing) vs sqft_above_grade (county) — only
    # makes sense when county data exists; `above` was loaded from
    # canonical.sqft_above_grade above and is county-only.
    fin_above = _to_int(listing.get("finished_above_ground"))
    if above and fin_above and abs(fin_above - above) > 100:
        conflicts.append({
            "field": "above_grade_sqft",
            "canonical_value": above,
            "canonical_source": "county",
            "conflicting_value": fin_above,
            "conflicting_source": "listing (finished_above_ground)",
            "severity": "warning",
        })

    # parcel_number (listing facts) vs parcel_id (county) — compare against
    # the RAW county dict, not canonical, so we don't accidentally compare
    # listing-vs-listing when county didn't provide a parcel_id.
    listing_parcel = listing.get("parcel_number") or listing.get("parcel_id")
    county_parcel = county.get("parcel_id") if county else None
    if listing_parcel and county_parcel and str(listing_parcel) != str(county_parcel):
        conflicts.append({
            "field": "parcel_id",
            "canonical_value": county_parcel,
            "canonical_source": "county",
            "conflicting_value": listing_parcel,
            "conflicting_source": "listing",
            "severity": "critical",
        })

    # listing lot_sqft vs county lot_acres (convert acres → sqft) — read
    # county lot_acres directly so we know we're comparing across sources.
    lot_sqft_listing = _to_int(listing.get("lot_sqft_listing"))
    lot_acres_county = county.get("lot_acres") if county else None
    if lot_sqft_listing and lot_acres_county:
        try:
            county_lot_sqft = int(float(lot_acres_county) * 43560)
            if abs(county_lot_sqft - lot_sqft_listing) / max(county_lot_sqft, 1) > 0.10:
                conflicts.append({
                    "field": "lot_sqft",
                    "canonical_value": county_lot_sqft,
                    "canonical_source": f"county ({lot_acres_county} acres)",
                    "conflicting_value": lot_sqft_listing,
                    "conflicting_source": "listing",
                    "severity": "info",
                })
        except (ValueError, TypeError):
            pass

    # Internal consistency: listing total_livable_area should ≈
    # listing finished_above_ground + listing finished_below_ground.
    # Read directly from listing so we know all 3 come from the same source.
    fin_below = _to_int(listing.get("finished_below_ground"))
    fin_above_check = _to_int(listing.get("finished_above_ground"))
    livable_listing = _to_int(listing.get("total_livable_area"))
    if livable_listing and fin_above_check and fin_below is not None:
        expected = fin_above_check + fin_below
        if abs(expected - livable_listing) > 50:
            conflicts.append({
                "field": "total_livable_area",
                "canonical_value": expected,
                "canonical_source": "listing (above + below)",
                "conflicting_value": livable_listing,
                "conflicting_source": "listing (total_livable_area)",
                "severity": "info",
            })

    # Track unknowns
    critical_fields = [
        "year_built", "sqft_above_grade", "asking_price",
        "assessed_total", "hoa_monthly",
    ]
    for field in critical_fields:
        if canonical.get(field) is None:
            unknowns.append(field)

    # Component ages — check which are unknown
    year_built = _to_int(canonical.get("year_built"))
    for component in ["roof", "hvac", "water_heater", "electrical_panel", "windows"]:
        key = f"component_{component}_year"
        if canonical.get(key) is None:
            if year_built:
                # Default to year_built with low confidence
                canonical[key] = year_built
                canonical[f"_source_{key}"] = {"source": "default_year_built", "rank": 10}
            else:
                unknowns.append(f"{component}_age")

    # Clean up internal source tracking from output
    clean_canonical = {k: v for k, v in canonical.items() if not k.startswith("_source_")}

    return clean_canonical, conflicts, unknowns


# ======================================================================
# Step 4: Pure Math
# ======================================================================


def _run_all_math(
    canonical: dict,
    current_home: dict | None = None,
    max_monthly_payment: float = 8000,
    max_cash_at_closing: float = 300000,
    assessment_markup_pct: float = 7.0,
) -> dict:
    """Run all deterministic analysis engines on canonical data."""
    results: dict[str, Any] = {}
    price = _to_float(canonical.get("asking_price")) or 0
    if not price:
        return {"error": "no asking price"}

    year_built = _to_int(canonical.get("year_built"))
    hoa = _to_float(canonical.get("hoa_monthly")) or 0
    assessed = _to_float(canonical.get("assessed_total"))
    zestimate = _to_float(canonical.get("zestimate"))

    # --- Financial ---
    try:
        from pipa.analysis.financial import run_financial_analysis
        fin = run_financial_analysis(
            list_price=price, hoa_monthly=hoa,
            down_payment_pcts=[0.10, 0.20],
            term_years=[15, 30],
            property_tax_rate=0.00875,
        )
        results["financial"] = fin.model_dump()
    except Exception as e:
        results["financial_error"] = str(e)

    # --- Price Benchmarks ---
    try:
        from pipa.analysis.appraisal import compute_price_benchmarks
        benchmarks = compute_price_benchmarks(
            asking_price=price,
            county_assessed=assessed,
            zestimate=zestimate,
            assessment_markup_pct=assessment_markup_pct,
        )
        results["price_benchmarks"] = benchmarks.model_dump()
    except Exception as e:
        results["price_benchmarks_error"] = str(e)

    # --- Condition / Capex ---
    try:
        from pipa.analysis.condition import score_property_condition, calculate_capex_forecast
        from datetime import date
        current_year = date.today().year

        components = []
        for comp_type in ["roof", "hvac", "water_heater", "electrical_panel", "windows", "appliances"]:
            year = _to_int(canonical.get(f"component_{comp_type}_year"))
            # Map generic names to condition engine's specific names
            type_map = {
                "roof": "roof_asphalt_shingle",
                "hvac": "hvac_heat_pump",
                "water_heater": "water_heater_tank",
                "electrical_panel": "electrical_panel",
                "windows": "windows",
                "appliances": "appliances",
            }
            mapped = type_map.get(comp_type, comp_type)
            if year:
                components.append({"component_type": mapped, "estimated_install_year": year})

        if components:
            score = score_property_condition(components, current_year=current_year)
            capex = calculate_capex_forecast(components, current_year=current_year)
            results["condition"] = {"score": score, "capex_forecast": capex, "components": components}
    except Exception as e:
        results["condition_error"] = str(e)

    # --- Offer ---
    try:
        from pipa.analysis.offer import calculate_max_bid, analyze_appraisal_gap
        bid = calculate_max_bid(
            appraisal_value=assessed or price,
            max_monthly_payment=max_monthly_payment,
            max_cash_at_closing=max_cash_at_closing,
            interest_rate=0.065,
            term_years=30,
            property_tax_rate=0.00875,
            hoa_monthly=hoa,
        )
        results["offer"] = {"max_bid": bid}

        if assessed:
            gap = analyze_appraisal_gap(
                offer_price=price,
                estimated_appraisal=assessed,
                cash_reserves=max_cash_at_closing,
            )
            results["offer"]["appraisal_gap"] = gap
    except Exception as e:
        results["offer_error"] = str(e)

    # --- Stress Tests ---
    try:
        from pipa.analysis.stress_testing import run_stress_tests
        loan_80 = round(price * 0.80)
        stress = run_stress_tests(list_price=price, loan_amount=loan_80, interest_rate=0.065)
        results["stress_tests"] = stress
    except Exception as e:
        results["stress_error"] = str(e)

    # --- Tax / Sell vs Rent ---
    if current_home:
        try:
            from pipa.analysis.tax import run_tax_analysis
            tax = run_tax_analysis(
                list_price=price,
                loan_amount=round(price * 0.80),
                property_tax_rate=0.00875,
                current_home_purchase_price=current_home.get("purchase_price"),
                current_home_estimated_value=current_home.get("estimated_value"),
                current_home_remaining_mortgage=current_home.get("remaining_mortgage"),
                years_as_primary=current_home.get("years_as_primary"),
                estimated_monthly_rent=current_home.get("estimated_monthly_rent"),
            )
            results["tax"] = tax.model_dump()
        except Exception as e:
            results["tax_error"] = str(e)

    return results


# ======================================================================
# Step 5: Deterministic Warning Engine
# ======================================================================


def _generate_warnings(
    canonical: dict,
    conflicts: list[dict],
    unknowns: list[str],
    math_results: dict,
) -> dict:
    """Generate structured warnings from deterministic analysis."""
    blockers: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    price = _to_float(canonical.get("asking_price")) or 0

    # --- Conflict-based warnings ---
    for conflict in conflicts:
        severity = conflict.get("severity", "warning")
        msg = (
            f"{conflict['field']}: listing says {conflict.get('conflicting_value')}, "
            f"county says {conflict.get('canonical_value')}"
        )
        if severity == "critical":
            blockers.append(msg)
        else:
            warnings.append(msg)

    # --- Price warnings ---
    benchmarks = math_results.get("price_benchmarks", {})
    ask_vs_zest_pct = benchmarks.get("ask_vs_zestimate_pct")
    if ask_vs_zest_pct and ask_vs_zest_pct > 10:
        warnings.append(f"Price is {ask_vs_zest_pct:+.1f}% above Zestimate")
    ask_vs_derived_pct = benchmarks.get("ask_vs_county_derived_pct")
    if ask_vs_derived_pct and ask_vs_derived_pct > 5:
        warnings.append(f"Price is {ask_vs_derived_pct:+.1f}% above county-derived market value")

    # --- Payment warnings ---
    fin = math_results.get("financial", {})
    breakdowns = fin.get("payment_breakdowns", {})
    for scenario, bd in breakdowns.items():
        if "20pct" in scenario and "30yr" in scenario:
            total = bd.get("total", 0)
            if total > 8000:
                warnings.append(f"Monthly payment ${total:,.0f} exceeds $8,000 target ({scenario})")

    # --- Condition warnings ---
    condition = math_results.get("condition", {})
    score = condition.get("score")
    if score is not None and score < 50:
        warnings.append(f"Condition score {score:.0f}/100 — significant near-term maintenance expected")
    capex = condition.get("capex_forecast", {})
    capex_5yr = capex.get(5, 0)
    if capex_5yr > 20000:
        warnings.append(f"5-year capex forecast: ${capex_5yr:,.0f}")

    # --- CDOM warnings ---
    cdom = _to_int(canonical.get("cdom"))
    if cdom and cdom > 30:
        warnings.append(f"Cumulative {cdom} days on market — property has been sitting")

    # --- Unknown/missing data warnings ---
    for field in unknowns:
        info.append(f"Missing: {field} — using conservative assumptions")

    # --- Pursue signal ---
    if blockers:
        pursue_signal = "red"
    elif len(warnings) >= 3:
        pursue_signal = "yellow"
    else:
        pursue_signal = "green"

    return {
        "pursue_signal": pursue_signal,
        "blockers": blockers,
        "warnings": warnings,
        "info": info,
    }


# ======================================================================
# Step 7: Decision Packet Assembly
# ======================================================================


def _assemble_decision_packet(
    canonical: dict,
    math_results: dict,
    warnings_output: dict,
    ai_extracted: dict,
    ai_interpretation: dict,
) -> dict:
    """Assemble the final 7-section decision packet."""
    return {
        "quick_take": {
            "pursue_signal": warnings_output.get("pursue_signal", "unknown"),
            "ai_recommendation": ai_interpretation.get("quick_take", "unknown"),
            "ai_confidence": ai_interpretation.get("confidence", "unknown"),
            "ai_summary": ai_interpretation.get("one_line_summary", ""),
            "blockers": warnings_output.get("blockers", []),
        },
        "price_view": math_results.get("price_benchmarks", {}),
        "monthly_cost": _extract_monthly_cost(math_results),
        "hidden_cost": {
            "condition_score": math_results.get("condition", {}).get("score"),
            "capex_forecast": math_results.get("condition", {}).get("capex_forecast", {}),
            "ai_components": ai_extracted.get("components", []),
            "unknowns": canonical.get("_unknowns", []),
        },
        "offer_strategy": math_results.get("offer", {}),
        "current_home_impact": math_results.get("tax", {}),
        "warnings": warnings_output,
        "ai_interpretation": ai_interpretation,
    }


def _extract_monthly_cost(math_results: dict) -> dict:
    """Extract monthly cost summary from financial results."""
    fin = math_results.get("financial", {})
    breakdowns = fin.get("payment_breakdowns", {})
    cash = fin.get("cash_needed_at_closing", {})

    summary = {}
    for scenario, bd in breakdowns.items():
        summary[scenario] = {
            "total": bd.get("total"),
            "cash_at_closing": cash.get(scenario),
        }
    return summary


# ======================================================================
# Helpers
# ======================================================================


def _to_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None
