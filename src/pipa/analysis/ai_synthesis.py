"""AI evidence synthesis stubs — Phase 10A.

Rule-based / template-based implementations that will be replaced by
LLM-powered versions in a future phase.  Every output is labeled with
an epistemic tag: [FACT], [ESTIMATE], or [INFERENCE], and links back
to supporting evidence.

NON-NEGOTIABLE: no output leaves this module without a label and an
evidence link.  If there is no evidence, the label is [INFERENCE] and
the link is ``None``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Epistemic labels
# ------------------------------------------------------------------

FACT = "[FACT]"
ESTIMATE = "[ESTIMATE]"
INFERENCE = "[INFERENCE]"


def _label(tag: str, text: str, evidence_ids: list[str] | None = None) -> dict:
    """Create a labeled statement with evidence links."""
    return {
        "label": tag,
        "text": text,
        "evidence_ids": evidence_ids or [],
    }


# ------------------------------------------------------------------
# Property dossier generation
# ------------------------------------------------------------------


def generate_property_dossier(
    property_data: dict,
    evidence_items: list[dict],
    analysis_results: dict,
) -> dict:
    """Generate a structured property dossier from available data.

    Parameters
    ----------
    property_data:
        Core property attributes (address, sqft, year_built, etc.).
    evidence_items:
        List of evidence dicts with ``field_name``, ``field_value``,
        ``confidence``, ``source_record_id``.
    analysis_results:
        Dict of analysis outputs keyed by analysis type
        (e.g. ``"financial"``, ``"tax"``, ``"condition"``).

    Returns
    -------
    dict with sections:
    - ``key_facts``: list of labeled statements about the property
    - ``risk_flags``: list of labeled risk items
    - ``unknowns``: list of data gaps
    - ``follow_up_questions``: list of questions for further research
    - ``generated_at``: ISO timestamp
    """
    key_facts: list[dict] = []
    risk_flags: list[dict] = []
    unknowns: list[str] = []
    follow_up_questions: list[str] = []

    # -- Key facts from property data ---------------------------------
    address = property_data.get("address", "Unknown")
    key_facts.append(_label(FACT, f"Address: {address}"))

    year_built = property_data.get("year_built")
    if year_built:
        age = datetime.now().year - int(year_built)
        evidence_ids = _find_evidence_ids(evidence_items, "year_built")
        key_facts.append(
            _label(FACT, f"Built {year_built} ({age} years old)", evidence_ids)
        )
    else:
        unknowns.append("Year built is unknown")

    sqft = property_data.get("sqft") or property_data.get("living_area")
    if sqft:
        evidence_ids = _find_evidence_ids(evidence_items, "sqft")
        key_facts.append(_label(FACT, f"Living area: {sqft:,} sqft", evidence_ids))

    lot_size = property_data.get("lot_size") or property_data.get("lot_sqft")
    if lot_size:
        evidence_ids = _find_evidence_ids(evidence_items, "lot_size")
        key_facts.append(_label(FACT, f"Lot size: {lot_size:,} sqft", evidence_ids))

    # -- Key facts from evidence with high confidence -----------------
    confirmed_evidence = [
        e for e in evidence_items if e.get("confidence") == "confirmed"
    ]
    for ev in confirmed_evidence[:10]:  # Cap to avoid huge dossiers
        field = ev.get("field_name", "")
        value = ev.get("field_value", "")
        src = ev.get("source_record_id", "")
        if field and value and field not in ("year_built", "sqft", "lot_size"):
            key_facts.append(
                _label(FACT, f"{_humanize_field(field)}: {value}", [src] if src else [])
            )

    # -- Risk flags from analysis results -----------------------------
    condition = analysis_results.get("condition")
    if condition is not None:
        if isinstance(condition, dict):
            score = condition.get("score", condition.get("condition_score"))
        else:
            score = condition
        if score is not None and float(score) < 50.0:
            risk_flags.append(
                _label(
                    ESTIMATE,
                    f"Property condition score is low ({score}/100) indicating "
                    f"significant deferred maintenance",
                )
            )

    capex = analysis_results.get("capex")
    if isinstance(capex, dict):
        near_term = capex.get(1, capex.get("1", 0))
        if near_term and float(near_term) > 10_000:
            risk_flags.append(
                _label(
                    ESTIMATE,
                    f"Estimated capital expenditure within 1 year: ${float(near_term):,.0f}",
                )
            )

    stress = analysis_results.get("stress_tests")
    if isinstance(stress, dict):
        downside = stress.get("downside_sale", {})
        for pct_str, result in downside.items():
            if isinstance(result, dict) and result.get("underwater"):
                risk_flags.append(
                    _label(
                        INFERENCE,
                        f"Underwater risk: a {float(pct_str)*100:.0f}% price decline "
                        f"would leave the buyer with negative equity",
                    )
                )
                break

    hoa_risk = analysis_results.get("hoa_risk")
    if hoa_risk is not None and int(hoa_risk) >= 7:
        risk_flags.append(
            _label(
                ESTIMATE,
                f"HOA risk score is elevated ({hoa_risk}/10)",
            )
        )

    # -- Unknowns / data gaps ----------------------------------------
    critical_fields = [
        ("year_built", "Year built"),
        ("sqft", "Living area"),
        ("lot_size", "Lot size"),
        ("roof_age", "Roof age/replacement year"),
        ("hvac_age", "HVAC age"),
        ("foundation_type", "Foundation type"),
    ]
    known_fields = {e.get("field_name") for e in evidence_items}
    for field, label in critical_fields:
        if field not in known_fields and not property_data.get(field):
            unknowns.append(f"{label} is unknown or unverified")

    # -- Follow-up questions -----------------------------------------
    if "roof_age" not in known_fields:
        follow_up_questions.append(
            "When was the roof last replaced? Request permit records or inspection report."
        )
    if "hvac_age" not in known_fields:
        follow_up_questions.append(
            "What is the age of the HVAC system? Check the serial number plate."
        )
    if not analysis_results.get("condition"):
        follow_up_questions.append(
            "No condition analysis available. Schedule a home inspection."
        )
    if year_built and int(year_built) < 1978:
        follow_up_questions.append(
            "Property predates 1978. Has a lead paint inspection been performed?"
        )
    if not risk_flags:
        # No risks found may mean insufficient data
        if len(evidence_items) < 5:
            follow_up_questions.append(
                "Limited evidence available. Gather county records, inspection "
                "report, and seller disclosure for a complete picture."
            )

    return {
        "key_facts": key_facts,
        "risk_flags": risk_flags,
        "unknowns": unknowns,
        "follow_up_questions": follow_up_questions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ------------------------------------------------------------------
# Comparison narrative
# ------------------------------------------------------------------


def generate_comparison_narrative(
    properties: list[dict],
    scores: list[dict],
) -> str:
    """Generate a template-based narrative comparing properties.

    Parameters
    ----------
    properties:
        List of property dicts with ``address``, ``list_price``, ``sqft``,
        ``year_built``, etc.
    scores:
        List of scoring dicts aligned with *properties*, each with
        ``overall_score``, ``financial_score``, ``condition_score``, etc.

    Returns
    -------
    Narrative string with labeled statements.
    """
    if not properties:
        return f"{INFERENCE} No properties provided for comparison."

    lines: list[str] = []
    lines.append(f"{FACT} Comparing {len(properties)} properties:\n")

    for i, (prop, score) in enumerate(zip(properties, scores), 1):
        addr = prop.get("address", f"Property {i}")
        price = prop.get("list_price", 0)
        sqft = prop.get("sqft", 0)
        ppsf = round(price / sqft, 2) if sqft else 0
        year = prop.get("year_built", "unknown")
        overall = score.get("overall_score", "N/A")

        lines.append(
            f"  {i}. {addr}\n"
            f"     {FACT} List price: ${price:,.0f} | {sqft:,} sqft | ${ppsf:.0f}/sqft | Built {year}\n"
            f"     {ESTIMATE} Overall score: {overall}/100"
        )

        cond = score.get("condition_score")
        if cond is not None:
            lines.append(f"     {ESTIMATE} Condition: {cond}/100")

        fin = score.get("financial_score")
        if fin is not None:
            lines.append(f"     {ESTIMATE} Financial: {fin}/100")

    # Summary
    if len(properties) >= 2 and len(scores) >= 2:
        best_idx = max(range(len(scores)), key=lambda i: scores[i].get("overall_score", 0))
        best_addr = properties[best_idx].get("address", f"Property {best_idx + 1}")
        lines.append(
            f"\n{INFERENCE} Based on available scoring, {best_addr} "
            f"ranks highest overall. This ranking should be validated "
            f"against personal priorities and in-person assessment."
        )

    return "\n".join(lines)


# ------------------------------------------------------------------
# Contradiction detection across evidence
# ------------------------------------------------------------------


def detect_contradictions(evidence_items: list[dict]) -> list[dict]:
    """Find conflicting evidence across different sources.

    Groups evidence by ``field_name`` and flags items where multiple
    sources report different values for the same field.

    Parameters
    ----------
    evidence_items:
        List of evidence dicts with ``field_name``, ``field_value``,
        ``source_record_id``, ``confidence``, ``observed_at``.

    Returns
    -------
    list of contradiction dicts:
    - ``field``: the contested field
    - ``values``: list of {value, source, confidence, observed_at}
    - ``severity``: ``"low"``, ``"medium"``, ``"high"``
    - ``label``: epistemic label
    """
    # Group by field
    by_field: dict[str, list[dict]] = {}
    for ev in evidence_items:
        fname = ev.get("field_name", "")
        if fname:
            by_field.setdefault(fname, []).append(ev)

    contradictions: list[dict] = []

    for field, items in by_field.items():
        if len(items) < 2:
            continue

        # Normalize values for comparison
        unique_values: dict[str, list[dict]] = {}
        for item in items:
            val = str(item.get("field_value", "")).strip().lower()
            unique_values.setdefault(val, []).append(item)

        if len(unique_values) < 2:
            continue  # All agree

        # There is a genuine conflict
        values_detail: list[dict] = []
        for val, sources in unique_values.items():
            for src in sources:
                values_detail.append({
                    "value": src.get("field_value", ""),
                    "source": src.get("source_record_id", "unknown"),
                    "confidence": src.get("confidence", "unknown"),
                    "observed_at": src.get("observed_at", ""),
                })

        # Determine severity based on confidence levels
        confidences = [item.get("confidence", "") for item in items]
        has_confirmed = "confirmed" in confidences
        severity = "high" if has_confirmed else "medium"

        contradictions.append({
            "field": field,
            "values": values_detail,
            "severity": severity,
            "label": INFERENCE,
        })

    return contradictions


# ------------------------------------------------------------------
# Inspection checklist generation
# ------------------------------------------------------------------


def generate_inspection_checklist(
    property_data: dict,
    condition_analysis: dict | None = None,
) -> list[dict]:
    """Generate targeted inspection focus areas based on property data.

    Parameters
    ----------
    property_data:
        Core property attributes.
    condition_analysis:
        Output of condition scoring (capex forecast, component ages, etc.).

    Returns
    -------
    list of checklist items, each with:
    - ``area``: inspection area (e.g. ``"roof"``, ``"hvac"``)
    - ``priority``: ``"high"``, ``"medium"``, ``"low"``
    - ``reason``: why this area needs attention
    - ``label``: epistemic label
    - ``evidence_ids``: supporting evidence
    """
    items: list[dict] = []

    year_built = property_data.get("year_built")
    current_year = datetime.now().year

    # Age-based priorities
    if year_built:
        age = current_year - int(year_built)

        if age >= 40:
            items.append({
                "area": "electrical",
                "priority": "high",
                "reason": f"{ESTIMATE} Home is {age} years old. Electrical panel, wiring, and grounding should be inspected for code compliance and safety.",
                "label": ESTIMATE,
                "evidence_ids": [],
            })
            items.append({
                "area": "plumbing",
                "priority": "high",
                "reason": f"{ESTIMATE} Home is {age} years old. Check supply line material (galvanized steel corrodes over time) and main sewer line condition.",
                "label": ESTIMATE,
                "evidence_ids": [],
            })

        if age >= 20:
            items.append({
                "area": "roof",
                "priority": "high",
                "reason": f"{ESTIMATE} Home is {age} years old. Asphalt shingle roofs typically last 20-25 years. Verify last replacement date.",
                "label": ESTIMATE,
                "evidence_ids": [],
            })
            items.append({
                "area": "hvac",
                "priority": "medium",
                "reason": f"{ESTIMATE} HVAC systems typically last 15-20 years. Verify system age and recent maintenance records.",
                "label": ESTIMATE,
                "evidence_ids": [],
            })

        if age >= 15:
            items.append({
                "area": "water_heater",
                "priority": "medium",
                "reason": f"{ESTIMATE} Tank water heaters last ~12 years. Verify age from serial number.",
                "label": ESTIMATE,
                "evidence_ids": [],
            })

        if year_built < 1978:
            items.append({
                "area": "hazardous_materials",
                "priority": "high",
                "reason": f"{FACT} Built before 1978. Federal law requires lead paint disclosure. Test for lead paint and check for asbestos in insulation, floor tiles, or pipe wrap.",
                "label": FACT,
                "evidence_ids": [],
            })

    # Condition-analysis-based priorities
    if condition_analysis:
        components = condition_analysis.get("components", [])
        capex = condition_analysis.get("capex", {})

        # Components at or past end of life
        for comp in components:
            remaining = comp.get("remaining_life", 999)
            comp_type = comp.get("type", comp.get("component_type", "unknown"))
            if remaining <= 0:
                items.append({
                    "area": comp_type,
                    "priority": "high",
                    "reason": f"{ESTIMATE} Component '{comp_type}' has exceeded its expected lifespan. Inspect condition and budget for replacement.",
                    "label": ESTIMATE,
                    "evidence_ids": comp.get("evidence_ids", []),
                })
            elif remaining <= 3:
                items.append({
                    "area": comp_type,
                    "priority": "medium",
                    "reason": f"{ESTIMATE} Component '{comp_type}' has ~{remaining} years of remaining life. Assess current condition.",
                    "label": ESTIMATE,
                    "evidence_ids": comp.get("evidence_ids", []),
                })

    # Standard items that always apply
    items.append({
        "area": "foundation",
        "priority": "medium",
        "reason": f"{INFERENCE} Always inspect for foundation cracks, settling, and water intrusion in basement/crawlspace.",
        "label": INFERENCE,
        "evidence_ids": [],
    })
    items.append({
        "area": "grading_drainage",
        "priority": "medium",
        "reason": f"{INFERENCE} Check lot grading and drainage patterns. Water should flow away from the foundation.",
        "label": INFERENCE,
        "evidence_ids": [],
    })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))

    return items


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _find_evidence_ids(evidence_items: list[dict], field_name: str) -> list[str]:
    """Find all source_record_ids for a given field in evidence items."""
    ids: list[str] = []
    for ev in evidence_items:
        if ev.get("field_name") == field_name:
            src = ev.get("source_record_id")
            if src:
                ids.append(src)
    return ids


def _humanize_field(field_name: str) -> str:
    """Convert a snake_case field name to a human-readable label."""
    return field_name.replace("_", " ").title()
