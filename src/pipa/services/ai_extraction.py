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
) -> dict:
    """Generate a buyer-focused property summary using AI.

    Combines listing data + county data + price benchmarks into
    a concise buyer-oriented summary with pursue/maybe/pass recommendation.
    """
    context_parts = [f"Listing data: {json.dumps(property_data, default=str)[:2000]}"]
    if county_data:
        context_parts.append(f"County data: {json.dumps(county_data, default=str)[:1500]}")
    if price_benchmarks:
        context_parts.append(f"Price benchmarks: {json.dumps(price_benchmarks, default=str)[:500]}")
    context = "\n\n".join(context_parts)

    prompt = (
        "You are a buyer's advisor analyzing a property. Based on the data below, "
        "provide a JSON object with:\n"
        "- quick_take: pursue/maybe/pass\n"
        "- confidence: high/medium/low\n"
        "- top_3_pros: [list of 3 strings]\n"
        "- top_3_cons: [list of 3 strings]\n"
        "- red_flags: [list of strings, empty if none]\n"
        "- questions_for_agent: [list of 3-5 questions to ask]\n"
        "- one_line_summary: string (1 sentence verdict)\n\n"
        "Label each pro/con as [FACT] if from county/verified data, "
        "[ESTIMATE] if from listing/Zillow, [INFERENCE] if your analysis.\n\n"
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
