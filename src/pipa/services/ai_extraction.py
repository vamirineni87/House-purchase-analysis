"""AI-powered text extraction using Claude CLI.

Shells out to `claude` CLI (available on the user's desktop) to extract
structured data from unstructured listing descriptions, disclosures,
and inspection reports.

No Claude API key needed — uses the already-authenticated CLI session.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.source import EvidenceItem, SourceRecord

logger = logging.getLogger(__name__)


def extract_components_from_text(text: str) -> list[dict]:
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

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Claude CLI failed: %s", result.stderr[:200])
            return []

        output = result.stdout.strip()

        # Extract JSON from the response (may be wrapped in ```json ... ```)
        json_match = re.search(r"\[.*\]", output, re.DOTALL)
        if json_match:
            components = json.loads(json_match.group())
            return components
        else:
            logger.warning("No JSON array found in Claude output")
            return []

    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI timed out")
        return []
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude output as JSON: %s", e)
        return []
    except FileNotFoundError:
        logger.warning("Claude CLI not found — is it installed?")
        return []


def extract_red_flags_from_text(text: str) -> list[dict]:
    """Extract potential red flags from listing description.

    Looks for concerning language: water damage, foundation issues,
    as-is, seller will not repair, etc.

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

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        output = result.stdout.strip()
        json_match = re.search(r"\[.*\]", output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return []

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def extract_seller_motivation(text: str) -> dict:
    """Detect seller motivation signals from listing text.

    Looks for: price reductions, motivated seller language, relocation,
    estate sale, divorce, vacant property, etc.

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

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {}

        output = result.stdout.strip()
        json_match = re.search(r"\{.*\}", output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {}

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return {}


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
    components = extract_components_from_text(description)
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
                confidence="inferred",  # AI extraction is inferred, not confirmed
            )
            db.add(evidence)

    # Extract red flags
    red_flags = extract_red_flags_from_text(description)
    if red_flags:
        result["red_flags"] = red_flags

    # Extract seller motivation
    motivation = extract_seller_motivation(description)
    if motivation:
        result["seller_motivation"] = motivation

    await db.flush()
    return result
