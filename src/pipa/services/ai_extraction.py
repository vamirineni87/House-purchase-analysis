"""AI-powered text extraction using Claude CLI.

Shells out to `claude` CLI (available on the user's desktop) to extract
structured data from unstructured listing descriptions, disclosures,
and inspection reports.

No Claude API key needed — uses the already-authenticated CLI session.

Pattern borrowed from schwab-TradingBot-StockScanner/app/ai_analyst/claude_client.py:
- asyncio.create_subprocess_exec (non-blocking)
- --output-format json (structured output)
- --model flag (configurable)
- Rate limiting + retry with backoff
- shutil.which("claude") to find binary
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.source import EvidenceItem, SourceRecord

logger = logging.getLogger(__name__)

# Resolve claude CLI path once at import time
_CLAUDE_BIN = shutil.which("claude")
if not _CLAUDE_BIN:
    logger.warning("Claude CLI not found in PATH at import time; will retry on each call")

_last_call_time = 0.0
_RATE_LIMIT_SECONDS = 5  # Min seconds between Claude calls
_DEFAULT_TIMEOUT = 60
_DEFAULT_MODEL = "claude-sonnet-4-6"  # Fast model for extraction tasks

# In-memory log of recent AI calls (prompt + response + timing)
# Flushed to DB via store_ai_call_log() after each pipeline step.
_call_log: list[dict] = []


def get_call_log() -> list[dict]:
    """Return and clear the accumulated AI call log."""
    log = list(_call_log)
    _call_log.clear()
    return log


async def _ask_claude(
    prompt: str,
    timeout: int = _DEFAULT_TIMEOUT,
    model: str = _DEFAULT_MODEL,
    max_retries: int = 2,
    call_label: str = "",
) -> str | None:
    """Call Claude via CLI subprocess (async, non-blocking).

    Uses `claude -p` with --output-format json for structured output.
    Rate limited to avoid hammering the CLI.
    Every call is logged to _call_log with prompt, raw response, model, and timing.
    """
    global _last_call_time

    # Rate limiting
    now = time.monotonic()
    elapsed = now - _last_call_time
    if elapsed < _RATE_LIMIT_SECONDS:
        wait = _RATE_LIMIT_SECONDS - elapsed
        logger.debug("Claude rate limit: waiting %.1fs", wait)
        await asyncio.sleep(wait)

    for attempt in range(max_retries + 1):
        try:
            call_start = time.monotonic()
            _last_call_time = call_start

            claude_bin = _CLAUDE_BIN or shutil.which("claude")
            if not claude_bin:
                logger.error("Claude CLI not found. Ensure 'claude' is in PATH.")
                return None

            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt, "--output-format", "json", "--model", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            duration_ms = int((time.monotonic() - call_start) * 1000)

            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace").strip()
                logger.warning("Claude CLI error (attempt %d): %s", attempt + 1, err_text[:200])
                _call_log.append({
                    "label": call_label,
                    "model": model,
                    "prompt": prompt,
                    "response": None,
                    "error": err_text[:500],
                    "duration_ms": duration_ms,
                    "attempt": attempt + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                if attempt < max_retries:
                    await asyncio.sleep(5)
                    continue
                return None

            raw = stdout.decode("utf-8", errors="replace").strip()

            # Parse JSON output format
            # claude --output-format json returns {"type": "result", "result": "..."}
            parsed_response = raw
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and "result" in data:
                    parsed_response = data["result"]
            except json.JSONDecodeError:
                pass

            # Log the call
            _call_log.append({
                "label": call_label,
                "model": model,
                "prompt": prompt,
                "raw_response": raw[:5000],
                "parsed_response": parsed_response[:5000] if isinstance(parsed_response, str) else json.dumps(parsed_response, default=str)[:5000],
                "duration_ms": duration_ms,
                "attempt": attempt + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return parsed_response

        except asyncio.TimeoutError:
            logger.warning("Claude CLI timeout (%ds) on attempt %d", timeout, attempt + 1)
            _call_log.append({
                "label": call_label,
                "model": model,
                "prompt": prompt,
                "response": None,
                "error": f"timeout after {timeout}s",
                "duration_ms": timeout * 1000,
                "attempt": attempt + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if attempt < max_retries:
                await asyncio.sleep(5)
                continue
            return None
        except FileNotFoundError:
            logger.error("Claude CLI not found. Ensure 'claude' is in PATH.")
            return None
        except Exception:
            logger.exception("Claude CLI unexpected error (attempt %d)", attempt + 1)
            if attempt < max_retries:
                await asyncio.sleep(5)
                continue
            return None

    return None


def _parse_json_from_response(text: str) -> Any:
    """Extract JSON array or object from Claude's response text."""
    if not text:
        return None
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding raw JSON array or object
    for pattern in [r"(\[.*\])", r"(\{.*\})"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


# ======================================================================
# Extraction functions
# ======================================================================


async def extract_components_from_text(text: str) -> list[dict]:
    """Extract home component replacements/upgrades from listing text.

    Uses Claude CLI to parse free-text descriptions like:
    "new roof 2024, HVAC replaced 2023, updated kitchen..."

    Returns list of dicts: [{component, year, details, confidence}, ...]
    """
    if not text or len(text.strip()) < 20:
        return []

    prompt = (
        "Extract all home component replacements, upgrades, and renovations "
        "from this listing description. Return ONLY a JSON array with objects "
        "containing: component (string), year (int or null), details (string), "
        "confidence (string: high if year is explicitly stated, medium if "
        "implied like 'recently', low if vague). "
        "No explanation, just the JSON array.\n\n"
        f"Listing text:\n{text[:3000]}"
    )

    response = await _ask_claude(prompt, call_label="extract_components")
    result = _parse_json_from_response(response)
    return result if isinstance(result, list) else []


async def extract_red_flags_from_text(text: str) -> list[dict]:
    """Extract potential red flags from listing description.

    Returns list of dicts: [{flag, severity, excerpt}, ...]
    """
    if not text or len(text.strip()) < 20:
        return []

    prompt = (
        "Analyze this listing description for potential red flags or concerns "
        "a home buyer should know about. Look for: mentions of damage, repairs "
        "needed, as-is conditions, seller limitations, known issues, "
        "unusual disclaimers, or anything a buyer should investigate. "
        "Return ONLY a JSON array with objects containing: "
        "flag (string), severity (critical/warning/info), excerpt (the relevant text). "
        "If no red flags found, return an empty array []. No explanation.\n\n"
        f"Listing text:\n{text[:3000]}"
    )

    response = await _ask_claude(prompt, call_label="extract_red_flags")
    result = _parse_json_from_response(response)
    return result if isinstance(result, list) else []


async def extract_seller_motivation(text: str) -> dict:
    """Detect seller motivation signals from listing text.

    Returns dict with: {motivation_level, signals, negotiation_leverage}
    """
    if not text or len(text.strip()) < 20:
        return {}

    prompt = (
        "Analyze this listing description for seller motivation signals. "
        "Look for: price reduction mentions, 'motivated seller', relocation, "
        "estate sale, divorce indicators, vacancy clues, 'bring all offers', "
        "'priced to sell', concession offers, agent remarks suggesting urgency. "
        "Return ONLY a JSON object with: "
        "motivation_level (high/medium/low/unknown), "
        "signals (list of strings describing each signal found), "
        "negotiation_leverage (string: strong/moderate/weak/unknown). "
        "No explanation.\n\n"
        f"Listing text:\n{text[:3000]}"
    )

    response = await _ask_claude(prompt, call_label="extract_seller_motivation")
    result = _parse_json_from_response(response)
    return result if isinstance(result, dict) else {}


async def validate_listing_against_county(
    listing_data: dict,
    county_data: dict,
) -> dict:
    """Cross-reference listing claims against county records using AI.

    Finds discrepancies between what the listing says and what the
    county officially records. Examples:
    - Listing says "fully finished basement" but county shows 80 sqft finished
    - Listing says "5 bedrooms" but county shows 4 + 1 basement den
    - Listing says "new roof 2024" but no county permit found
    - Listing says 6,045 sqft but county above-grade is 3,845

    Returns dict with:
    - conflicts: [{field, listing_says, county_says, severity, explanation}]
    - validated: [{field, value, source}]  (fields that match)
    - unverifiable: [fields from listing not in county data]
    """
    prompt = (
        "You are a property analyst cross-referencing a real estate listing "
        "against official county records. Find ALL discrepancies.\n\n"
        "For each field, compare what the listing claims vs what the county records show. "
        "Pay special attention to:\n"
        "- Square footage (listing often includes basement, county shows above-grade only)\n"
        "- Bedroom count (basement rooms may not be official bedrooms)\n"
        "- Bathroom count\n"
        "- Basement finished area\n"
        "- Year built or renovation claims vs permits\n"
        "- Any upgrade claims with no permit evidence\n\n"
        "Return ONLY a JSON object with:\n"
        "- conflicts: [{field, listing_says, county_says, severity (critical/warning/info), explanation}]\n"
        "- validated: [{field, value, note}] (fields that match or are consistent)\n"
        "- unverifiable: [{field, listing_claims, note}] (claims we can't check)\n"
        "- buyer_warnings: [string] (plain English warnings for the buyer)\n\n"
        f"LISTING DATA:\n{json.dumps(listing_data, default=str)[:2000]}\n\n"
        f"COUNTY RECORDS:\n{json.dumps(county_data, default=str)[:2000]}"
    )

    response = await _ask_claude(prompt, timeout=90, call_label="validate_listing_vs_county")
    result = _parse_json_from_response(response)
    return result if isinstance(result, dict) else {}


async def extract_all_from_listing(
    description: str,
    listing_facts: dict | None = None,
    county_data: dict | None = None,
) -> dict:
    """One-shot extraction: components + red flags + motivation + validation.

    Combines all AI extraction into a single comprehensive analysis.
    If county_data is provided, also validates listing claims against it.
    """
    result = {}

    # Extract components from description
    components = await extract_components_from_text(description)
    if components:
        result["components"] = components

    # Extract red flags
    red_flags = await extract_red_flags_from_text(description)
    if red_flags:
        result["red_flags"] = red_flags

    # Seller motivation
    motivation = await extract_seller_motivation(description)
    if motivation:
        result["seller_motivation"] = motivation

    # Cross-reference listing vs county if both available
    if listing_facts and county_data:
        validation = await validate_listing_against_county(listing_facts, county_data)
        if validation:
            result["validation"] = validation

    return result


async def generate_property_summary(
    property_data: dict,
    county_data: dict | None = None,
    price_benchmarks: dict | None = None,
    comp_data: dict | None = None,
    financial_data: dict | None = None,
    condition_data: dict | None = None,
    school_data: dict | None = None,
    flood_data: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Generate a buyer-focused property summary using AI.

    Combines ALL available data — listing, county, comps, financial,
    condition, schools, flood, warnings — into a comprehensive
    buyer-oriented summary with pursue/maybe/pass recommendation.
    """
    context_parts = [f"Listing data: {json.dumps(property_data, default=str)[:2000]}"]
    if county_data:
        context_parts.append(f"County data: {json.dumps(county_data, default=str)[:1500]}")
    if price_benchmarks:
        context_parts.append(f"Price benchmarks: {json.dumps(price_benchmarks, default=str)[:500]}")
    if comp_data:
        # Include value band, confidence, asking assessment, filtered comps summary
        comp_summary = {}
        if comp_data.get("rough_value_band"):
            comp_summary["value_band"] = comp_data["rough_value_band"]
        if comp_data.get("quick_confidence"):
            comp_summary["confidence"] = comp_data["quick_confidence"]
        if comp_data.get("asking_vs_comps"):
            comp_summary["asking_vs_comps"] = comp_data["asking_vs_comps"]
        if comp_data.get("filtered_comps"):
            comp_summary["comp_count"] = len(comp_data["filtered_comps"])
            comp_summary["comps"] = comp_data["filtered_comps"][:6]
        if comp_data.get("ai_interpretation"):
            ai_int = comp_data["ai_interpretation"]
            if ai_int.get("value_opinion"):
                comp_summary["ai_value_opinion"] = ai_int["value_opinion"]
            if ai_int.get("asking_assessment"):
                comp_summary["ai_asking_assessment"] = ai_int["asking_assessment"]
            if ai_int.get("key_insights"):
                comp_summary["ai_insights"] = ai_int["key_insights"]
        context_parts.append(f"Comparable sales: {json.dumps(comp_summary, default=str)[:1500]}")
    if financial_data:
        fin_summary = {}
        for key in ("payment_breakdowns", "cash_at_closing", "stress_tests", "monthly_total"):
            if key in financial_data:
                fin_summary[key] = financial_data[key]
        context_parts.append(f"Financial analysis: {json.dumps(fin_summary, default=str)[:1000]}")
    if condition_data:
        cond_summary = {}
        for key in ("overall_score", "components", "capex_10yr", "red_flags"):
            if key in condition_data:
                cond_summary[key] = condition_data[key]
        context_parts.append(f"Condition assessment: {json.dumps(cond_summary, default=str)[:800]}")
    if school_data:
        context_parts.append(f"School assignments: {json.dumps(school_data, default=str)[:500]}")
    if flood_data:
        context_parts.append(f"Flood zone: {json.dumps(flood_data, default=str)[:300]}")
    if warnings:
        context_parts.append(f"Warning flags: {json.dumps(warnings, default=str)[:500]}")
    context = "\n\n".join(context_parts)

    prompt = (
        "You are a buyer's advisor analyzing a residential property in Northern Virginia "
        "for a buyer making a $1M+ purchase decision. Based on ALL the data below, "
        "provide a JSON object with:\n"
        "- quick_take: pursue/maybe/pass\n"
        "- confidence: high/medium/low\n"
        "- top_3_pros: [list of 3 strings]\n"
        "- top_3_cons: [list of 3 strings]\n"
        "- red_flags: [list of strings, empty if none]\n"
        "- questions_for_agent: [list of 3-5 questions to ask the listing agent]\n"
        "- one_line_summary: string (1 sentence verdict)\n"
        "- value_assessment: string (is the asking price fair given comps and condition?)\n"
        "- financial_notes: string (any concerns about affordability or cash requirements)\n"
        "- negotiation_leverage: [list of strings — points that could justify a lower offer]\n\n"
        "Label each pro/con as [FACT] if from county/verified data, "
        "[ESTIMATE] if from listing/Zillow, [INFERENCE] if your analysis.\n"
        "Consider comps, condition, financial burden, school quality, flood risk, "
        "and any warning flags when forming your recommendation.\n\n"
        f"{context}"
    )

    response = await _ask_claude(prompt, timeout=90, call_label="generate_property_summary")
    result = _parse_json_from_response(response)
    return result if isinstance(result, dict) else {}


async def extract_and_store(
    db: AsyncSession,
    property_id: str,
    description: str,
    source: str = "listing_description",
) -> dict:
    """Extract components + red flags from text and store as evidence.

    Returns dict with: {components, red_flags, seller_motivation}
    """
    result = {}

    # Extract components
    components = await extract_components_from_text(description)
    if components:
        result["components"] = components

        # Store each as evidence
        now = datetime.now(timezone.utc)
        source_record = SourceRecord(
            property_id=property_id,
            source_name="ai_extraction",
            source_url=None,
            raw_payload={"description": description[:1000], "components": components},
            fetched_at=now,
        )
        db.add(source_record)
        await db.flush()

        for comp in components:
            evidence = EvidenceItem(
                property_id=property_id,
                field_name=f"component_{comp.get('component', 'unknown').lower().replace(' ', '_')}",
                field_value=json.dumps(comp),
                source_record_id=source_record.id,
                observed_at=now,
                confidence="inferred",
            )
            db.add(evidence)

    # Extract red flags
    red_flags = await extract_red_flags_from_text(description)
    if red_flags:
        result["red_flags"] = red_flags

    # Extract seller motivation
    motivation = await extract_seller_motivation(description)
    if motivation:
        result["seller_motivation"] = motivation

    await db.flush()
    return result


async def interpret_comps(
    subject: dict,
    comps: list[dict],
    market_context: dict | None = None,
    condition_data: dict | None = None,
    flood_data: dict | None = None,
    financial_data: dict | None = None,
) -> dict:
    """AI interpretation of comparable sales vs subject property.

    Asks Claude to rank comps by true comparability, flag outliers,
    identify non-arms-length transactions, and provide a value opinion
    with reasoning — things pure math misses.

    Returns dict with:
      ranked_comps: [{address, rank, reasoning, is_outlier, adjusted_opinion}]
      value_opinion: {low, mid, high, reasoning}
      outliers: [{address, reason}]
      key_insights: [str]
      confidence: str
    """
    subject_summary = (
        f"Subject: {subject.get('address', 'Unknown')}\n"
        f"  List Price: ${subject.get('list_price', 0):,.0f}\n"
        f"  Sqft: {subject.get('sqft', 'unknown')}, "
        f"Beds: {subject.get('beds', 'unknown')}, "
        f"Baths: {subject.get('baths', 'unknown')}\n"
        f"  Year Built: {subject.get('year_built', 'unknown')}\n"
        f"  Lot: {subject.get('lot_size', 'unknown')} sqft\n"
        f"  Condition: {subject.get('condition', 'unknown')}, "
        f"Grade: {subject.get('grade', 'unknown')}\n"
        f"  County: {subject.get('county', 'unknown')}\n"
        f"  Subdivision: {subject.get('subdivision', 'unknown')}"
    )

    comp_lines = []
    for i, c in enumerate(comps, 1):
        sqft = c.get("sqft_above_grade") or c.get("sqft") or c.get("total_sqft") or "?"
        beds = c.get("beds") or c.get("bedrooms") or "?"
        baths = c.get("baths") or c.get("bathrooms") or "?"
        yr = c.get("year_built") or "?"
        price = c.get("sale_price") or c.get("price") or 0
        ppsf = c.get("price_per_sqft") or ""
        cond = c.get("condition") or "?"
        grade = c.get("grade") or "?"
        lot = c.get("lot_size") or "?"
        addr = c.get("address") or f"Comp {i}"
        sale_date = c.get("sale_date") or c.get("date") or "?"
        similarity = c.get("similarity_score") or "?"

        comp_lines.append(
            f"  Comp {i}: {addr}\n"
            f"    Sale: ${price:,.0f} on {sale_date}\n"
            f"    Sqft: {sqft}, Beds: {beds}, Baths: {baths}, Year: {yr}\n"
            f"    Condition: {cond}, Grade: {grade}, Lot: {lot} sqft\n"
            f"    Math Similarity Score: {similarity}/100"
            + (f", $/sqft: ${ppsf:,.0f}" if ppsf else "")
        )

    comps_text = "\n".join(comp_lines)

    market_text = ""
    if market_context:
        market_text = (
            f"\nMarket Context:\n"
            f"  Active listings nearby: {market_context.get('active_count', 0)}\n"
            f"  Pending sales: {market_context.get('pending_count', 0)}\n"
            f"  Sold in last 6 months: {market_context.get('sold_count', 0)}"
        )
        if market_context.get("active_price_range"):
            apr = market_context["active_price_range"]
            market_text += f"\n  Active price range: ${apr.get('low', 0):,.0f} - ${apr.get('high', 0):,.0f}"
        if market_context.get("subject_schools"):
            schools = market_context["subject_schools"]
            market_text += f"\n  Subject school assignments: {json.dumps(schools, default=str)[:500]}"
            market_text += "\n  NOTE: Comps in different school zones may not be directly comparable."

    condition_text = ""
    if condition_data:
        cond_parts = []
        if condition_data.get("overall_score") is not None:
            cond_parts.append(f"Overall Score: {condition_data['overall_score']}/100")
        if condition_data.get("components"):
            for comp in condition_data["components"][:8]:
                name = comp.get("component") or comp.get("name", "?")
                remaining = comp.get("remaining_life_years") or comp.get("remaining_life", "?")
                cond_parts.append(f"  {name}: {remaining} yrs remaining")
        if condition_data.get("capex_10yr"):
            cond_parts.append(f"10-Year CapEx Estimate: ${condition_data['capex_10yr']:,.0f}")
        if condition_data.get("red_flags"):
            cond_parts.append(f"Red Flags: {', '.join(str(f) for f in condition_data['red_flags'])}")
        if cond_parts:
            condition_text = "\n\nSubject Condition:\n" + "\n".join(f"  {p}" for p in cond_parts)

    flood_text = ""
    if flood_data:
        zone = flood_data.get("flood_zone") or flood_data.get("zone", "Unknown")
        risk = flood_data.get("risk_level") or flood_data.get("risk", "Unknown")
        insurance = flood_data.get("insurance_required", "Unknown")
        flood_text = f"\n\nFlood Zone: {zone} (Risk: {risk}, Insurance Required: {insurance})"

    financial_text = ""
    if financial_data:
        fin_parts = []
        if financial_data.get("monthly_total"):
            fin_parts.append(f"Monthly Payment (default scenario): ${financial_data['monthly_total']:,.0f}")
        if financial_data.get("cash_at_closing"):
            cac = financial_data["cash_at_closing"]
            if isinstance(cac, dict):
                fin_parts.append(f"Cash at Closing: ${cac.get('total', 0):,.0f}")
            else:
                fin_parts.append(f"Cash at Closing: ${cac:,.0f}")
        if financial_data.get("stress_tests"):
            fin_parts.append(f"Stress Tests: {json.dumps(financial_data['stress_tests'], default=str)[:300]}")
        if fin_parts:
            financial_text = "\n\nFinancial Context:\n" + "\n".join(f"  {p}" for p in fin_parts)

    prompt = (
        "You are a residential real estate appraiser analyzing comparable sales for a "
        "home purchase decision in Northern Virginia. The buyer is making a $1M+ decision "
        "and needs honest, precise analysis.\n\n"
        f"{subject_summary}\n\n"
        f"Comparable Sales:\n{comps_text}\n"
        f"{market_text}{condition_text}{flood_text}{financial_text}\n\n"
        "Analyze these comps and respond in JSON with this exact structure:\n"
        "{\n"
        '  "ranked_comps": [\n'
        "    {\n"
        '      "address": "...",\n'
        '      "rank": 1,\n'
        '      "reasoning": "Why this is/isn\'t a good comp (specific, 1-2 sentences)",\n'
        '      "is_outlier": false,\n'
        '      "outlier_reason": null,\n'
        '      "adjusted_opinion": 1300000\n'
        "    }\n"
        "  ],\n"
        '  "value_opinion": {\n'
        '    "low": 1200000,\n'
        '    "mid": 1275000,\n'
        '    "high": 1350000,\n'
        '    "reasoning": "2-3 sentence explanation of value conclusion"\n'
        "  },\n"
        '  "outliers": [\n'
        '    {"address": "...", "reason": "Estate sale / new construction / different neighborhood"}\n'
        "  ],\n"
        '  "key_insights": [\n'
        '    "Specific insight about market, pricing, or comparability"\n'
        "  ],\n"
        '  "confidence": "high|moderate|low",\n'
        '  "asking_assessment": "The asking price of $X is [above/at/below] market because..."\n'
        "}\n\n"
        "Focus on:\n"
        "- Which comps are TRULY comparable (same neighborhood feel, similar age/size/condition)\n"
        "- Flag distress sales, estate sales, new construction, or non-arms-length transactions\n"
        "- Whether the asking price is justified by the comp evidence\n"
        "- Any patterns the math might miss (price trends, neighborhood differences, condition gaps)\n"
        "- School zone differences — comps in different school boundaries may not be directly comparable\n"
        "- If data is missing for some comps, note the uncertainty\n"
        "Respond ONLY with the JSON, no other text."
    )

    response = await _ask_claude(prompt, timeout=90, call_label="interpret_comps")
    result = _parse_json_from_response(response)
    return result if isinstance(result, dict) else {}
