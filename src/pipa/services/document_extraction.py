"""Document fact extraction service.

Extracts structured facts from uploaded documents (inspection reports,
disclosures, appraisals, HOA CC&Rs, contracts).  Uses PyMuPDF (fitz)
for PDF text extraction when available, with a raw-bytes fallback.

All extraction is keyword/regex-based.  AI model integration is
deferred to a later phase.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# PDF text extraction
# ------------------------------------------------------------------


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extract text content from a PDF file.

    Uses PyMuPDF (``fitz``) when available for high-quality extraction.
    Falls back to reading the raw bytes and decoding whatever text is
    present (lossy but better than nothing).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    # Try PyMuPDF first
    try:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(str(file_path))
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        logger.debug("PyMuPDF (fitz) not installed; falling back to raw text extraction")
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed for %s: %s", file_path, exc)

    # Fallback: read raw bytes and extract printable text
    raw = file_path.read_bytes()
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = raw.decode("latin-1", errors="ignore")

    # Strip non-printable characters but keep newlines/tabs
    text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
    # Collapse excessive whitespace
    text = re.sub(r" {3,}", "  ", text)
    return text


# ------------------------------------------------------------------
# Document classification
# ------------------------------------------------------------------

_CLASSIFICATION_KEYWORDS: dict[str, list[str]] = {
    "inspection": [
        "inspection report",
        "home inspection",
        "property inspection",
        "inspector",
        "deficiency",
        "serviceable",
        "not functioning",
        "recommend repair",
        "safety hazard",
        "general home inspection",
    ],
    "disclosure": [
        "seller disclosure",
        "property disclosure",
        "disclosure statement",
        "known defect",
        "material fact",
        "residential property disclosure",
        "lead-based paint",
    ],
    "appraisal": [
        "appraisal report",
        "market value",
        "comparable sale",
        "appraised value",
        "uniform residential appraisal",
        "subject property",
        "reconciliation of value",
    ],
    "hoa_ccr": [
        "covenants, conditions",
        "cc&r",
        "homeowners association",
        "architectural review",
        "common area",
        "assessment",
        "association dues",
        "reserve fund",
        "rental restriction",
        "declaration of covenants",
    ],
    "contract": [
        "purchase agreement",
        "real estate contract",
        "earnest money",
        "contingency",
        "closing date",
        "settlement date",
        "offer to purchase",
        "addendum",
    ],
}


def classify_document(text: str) -> str:
    """Classify a document based on keyword matching.

    Returns one of: ``inspection``, ``disclosure``, ``appraisal``,
    ``hoa_ccr``, ``contract``, or ``other``.
    """
    text_lower = text.lower()

    scores: dict[str, int] = {}
    for doc_type, keywords in _CLASSIFICATION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return "other"

    return max(scores, key=scores.get)  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Fact extraction patterns
# ------------------------------------------------------------------

# Each pattern is (regex, fact_type, value_group_index, is_numeric)
_INSPECTION_PATTERNS: list[tuple[str, str, int, bool]] = [
    (r"roof\s+(?:age|installed|replaced)\s*[:;]?\s*(?:approx(?:imately)?\.?\s+)?(\d{4}|\d{1,2}\s*years?)", "roof_age", 1, False),
    (r"roof\s+(?:type|material)\s*[:;]?\s*([A-Za-z ]+?)(?:\.|,|\n)", "roof_material", 1, False),
    (r"hvac\s+(?:age|installed|replaced)\s*[:;]?\s*(?:approx(?:imately)?\.?\s+)?(\d{4}|\d{1,2}\s*years?)", "hvac_age", 1, False),
    (r"(?:furnace|heating)\s+(?:age|installed|replaced)\s*[:;]?\s*(?:approx(?:imately)?\.?\s+)?(\d{4}|\d{1,2}\s*years?)", "hvac_age", 1, False),
    (r"water\s+heater\s+(?:age|installed|replaced)\s*[:;]?\s*(?:approx(?:imately)?\.?\s+)?(\d{4}|\d{1,2}\s*years?)", "water_heater_age", 1, False),
    (r"water\s+heater\s+(?:type|style)\s*[:;]?\s*(tank(?:less)?|electric|gas)", "water_heater_type", 1, False),
    (r"electrical\s+panel\s*[:;]?\s*(\d{2,4}\s*amp|[A-Za-z ]+?(?:breaker|fuse))", "electrical_panel", 1, False),
    (r"(?:foundation)\s+(?:type|condition|material)\s*[:;]?\s*([A-Za-z ]+?)(?:\.|,|\n)", "foundation_type", 1, False),
    (r"foundation\s+(?:crack|issue|problem|settlement|heaving)", "foundation_issue", 0, False),
    (r"(?:plumbing|supply\s+line|drain)\s+(?:material|type)\s*[:;]?\s*(copper|pex|cpvc|galvanized|cast\s+iron|pvc|abs)", "plumbing_material", 1, False),
]

_DISCLOSURE_PATTERNS: list[tuple[str, str, int, bool]] = [
    (r"known\s+defect[s]?\s*[:;]?\s*([^\n.]+)", "known_defect", 1, False),
    (r"repair[s]?\s+(?:made|completed|performed)\s*[:;]?\s*([^\n.]+)", "repair_made", 1, False),
    (r"hoa\s+(?:fee|dues|assessment)\s*[:;]?\s*\$?\s*([\d,]+(?:\.\d{2})?)", "hoa_fee", 1, True),
    (r"special\s+assessment\s*[:;]?\s*\$?\s*([\d,]+(?:\.\d{2})?)", "special_assessment", 1, True),
    (r"(?:water\s+damage|mold|termite|pest|radon|asbestos|lead)", "known_defect", 0, False),
]

_HOA_PATTERNS: list[tuple[str, str, int, bool]] = [
    (r"(?:monthly|annual)\s+(?:fee|dues|assessment)\s*[:;]?\s*\$?\s*([\d,]+(?:\.\d{2})?)", "hoa_monthly_fee", 1, True),
    (r"reserve\s+(?:balance|fund)\s*[:;]?\s*\$?\s*([\d,]+(?:\.\d{2})?)", "reserve_balance", 1, True),
    (r"rental\s+restriction", "rental_restriction", 0, False),
    (r"(?:no|prohibit|restrict)\s+(?:short[- ]term\s+)?rental", "rental_restriction", 0, False),
    (r"(?:rental|lease)\s+cap\s*[:;]?\s*(\d{1,3})\s*%", "rental_cap_pct", 1, True),
    (r"minimum\s+lease\s+(?:term|period)\s*[:;]?\s*(\d+)\s*month", "min_lease_months", 1, True),
    (r"pet\s+restriction", "pet_restriction", 0, False),
    (r"(?:age[- ]restricted|55\s*\+|senior)", "age_restriction", 0, False),
]

_PATTERNS_BY_TYPE: dict[str, list[tuple[str, str, int, bool]]] = {
    "inspection": _INSPECTION_PATTERNS,
    "disclosure": _DISCLOSURE_PATTERNS,
    "hoa_ccr": _HOA_PATTERNS,
}


def _extract_context(text: str, match: re.Match, context_chars: int = 120) -> str:
    """Extract a source excerpt around a regex match."""
    start = max(0, match.start() - context_chars // 2)
    end = min(len(text), match.end() + context_chars // 2)
    excerpt = text[start:end].strip()
    # Normalize whitespace
    excerpt = re.sub(r"\s+", " ", excerpt)
    return excerpt


def _parse_numeric(value_text: str) -> Optional[float]:
    """Try to parse a numeric value from extracted text."""
    cleaned = value_text.replace(",", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def extract_facts(text: str, document_type: str) -> list[dict]:
    """Extract structured facts from document text.

    Parameters
    ----------
    text:
        Full text content of the document.
    document_type:
        One of ``inspection``, ``disclosure``, ``hoa_ccr``, etc.

    Returns
    -------
    list of dicts, each with:
    - ``fact_type``: str identifier of the fact
    - ``fact_value_text``: human-readable extracted value
    - ``fact_value_number``: numeric value if applicable, else None
    - ``confidence``: ``"estimated"`` (regex extraction is never ``"confirmed"``)
    - ``source_excerpt``: surrounding text for provenance
    """
    patterns = _PATTERNS_BY_TYPE.get(document_type, [])
    if not patterns:
        # For unknown types, try all patterns
        all_patterns: list[tuple[str, str, int, bool]] = []
        for pats in _PATTERNS_BY_TYPE.values():
            all_patterns.extend(pats)
        patterns = all_patterns

    facts: list[dict] = []
    seen_types: set[str] = set()

    for pattern_str, fact_type, value_group, is_numeric in patterns:
        for match in re.finditer(pattern_str, text, re.IGNORECASE):
            # De-duplicate: keep only the first match per fact_type
            # unless it's a type that can have multiples (defects, repairs)
            dedup_key = fact_type
            allow_multiple = fact_type in ("known_defect", "repair_made")
            if not allow_multiple and dedup_key in seen_types:
                continue

            if value_group > 0 and value_group <= len(match.groups()):
                value_text = match.group(value_group).strip()
            else:
                value_text = match.group(0).strip()

            fact_value_number: Optional[float] = None
            if is_numeric:
                fact_value_number = _parse_numeric(value_text)

            excerpt = _extract_context(text, match)

            facts.append({
                "fact_type": fact_type,
                "fact_value_text": value_text,
                "fact_value_number": fact_value_number,
                "confidence": "estimated",
                "source_excerpt": excerpt,
            })
            seen_types.add(dedup_key)

    return facts


# ------------------------------------------------------------------
# Contradiction detection
# ------------------------------------------------------------------


def find_contradictions(
    facts: list[dict],
    existing_evidence: list[dict],
) -> list[dict]:
    """Compare extracted facts against existing evidence and flag conflicts.

    Parameters
    ----------
    facts:
        Newly extracted facts (output of :func:`extract_facts`).
    existing_evidence:
        Existing evidence items, each with at least ``field_name``,
        ``field_value``, and optionally ``source_record_id`` and
        ``confidence``.

    Returns
    -------
    list of contradiction dicts, each with:
    - ``field``: the conflicting field name
    - ``new_value``: value from the new document
    - ``existing_value``: value from existing evidence
    - ``existing_source``: source of the existing evidence (if available)
    - ``severity``: ``"low"``, ``"medium"``, or ``"high"``
    """
    # Build a lookup of existing evidence by field name
    evidence_by_field: dict[str, list[dict]] = {}
    for ev in existing_evidence:
        fname = ev.get("field_name", "")
        if fname:
            evidence_by_field.setdefault(fname, []).append(ev)

    # Map fact_types to evidence field_names (flexible matching)
    _FACT_TO_FIELD: dict[str, list[str]] = {
        "roof_age": ["roof_age", "roof_year", "roof_install_year"],
        "hvac_age": ["hvac_age", "hvac_year", "hvac_install_year"],
        "water_heater_age": ["water_heater_age", "water_heater_year"],
        "hoa_fee": ["hoa_fee", "hoa_monthly", "hoa_monthly_fee"],
        "hoa_monthly_fee": ["hoa_fee", "hoa_monthly", "hoa_monthly_fee"],
        "reserve_balance": ["reserve_balance", "hoa_reserve_balance"],
        "foundation_type": ["foundation_type", "foundation"],
        "plumbing_material": ["plumbing_material", "plumbing_type"],
        "electrical_panel": ["electrical_panel", "electrical"],
        "special_assessment": ["special_assessment"],
    }

    contradictions: list[dict] = []

    for fact in facts:
        fact_type = fact.get("fact_type", "")
        new_value = fact.get("fact_value_text", "")
        new_number = fact.get("fact_value_number")

        # Find matching evidence fields
        candidate_fields = _FACT_TO_FIELD.get(fact_type, [fact_type])

        for field in candidate_fields:
            for ev in evidence_by_field.get(field, []):
                existing_value = ev.get("field_value", "")

                # Check for conflict
                is_conflict = False
                severity = "low"

                if new_number is not None:
                    # Numeric comparison
                    try:
                        existing_number = float(str(existing_value).replace(",", ""))
                        if existing_number > 0 and new_number > 0:
                            pct_diff = abs(new_number - existing_number) / existing_number
                            if pct_diff > 0.20:
                                is_conflict = True
                                if pct_diff > 0.50:
                                    severity = "high"
                                elif pct_diff > 0.20:
                                    severity = "medium"
                    except (ValueError, TypeError):
                        # Fall through to text comparison
                        pass

                if not is_conflict and new_value and existing_value:
                    # Text comparison (case-insensitive)
                    new_norm = new_value.lower().strip()
                    existing_norm = existing_value.lower().strip()
                    if new_norm != existing_norm and new_norm and existing_norm:
                        # Only flag if the values are genuinely different
                        # (not just one being a substring of the other)
                        if new_norm not in existing_norm and existing_norm not in new_norm:
                            is_conflict = True
                            severity = "medium"

                if is_conflict:
                    contradictions.append({
                        "field": field,
                        "new_value": new_value,
                        "existing_value": existing_value,
                        "existing_source": ev.get("source_record_id", "unknown"),
                        "severity": severity,
                    })

    return contradictions
