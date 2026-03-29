# PIPA Pipeline Architecture

## The 7-Step Pipeline

```
0. INGEST (Playwright scrapers)
   │
1. DETERMINISTIC STRUCTURED PARSE (regex, JSON, field mapping)
   │
2. AI PASS 1 — UNSTRUCTURED EXTRACTION TO EVIDENCE
   │  (Claude CLI → extracted_facts with confidence + verification_required)
   │
3. DETERMINISTIC RESOLVER / CONFLICT ARBITRATION
   │  (source ranking: county > permit > disclosure > listing > AI-extracted)
   │  Output: canonical_input_set + conflict_set + unresolved_unknowns
   │
4. PURE MATH / RULE-BASED ANALYSIS
   │  (financial, tax, condition, offer, stress — deterministic)
   │  Supports uncertainty bands for unresolved fields
   │
5. DETERMINISTIC WARNING ENGINE
   │  (conflict flags, blockers, pursue signal: green/yellow/red)
   │
6. AI PASS 2 — INTERPRETATION / COPILOT
   │  (explain conflicts, prioritize warnings, generate questions, narrative)
   │
7. DECISION PACKET (assembled from all above)
```

## Responsibility Split

### DETERMINISTIC CODE does:
- Structured parsing (GraphQL, HTML, county fields)
- Source ranking by confidence
- Canonical field resolution
- Conflict detection
- Financial math (mortgage, tax, IRR, amortization)
- Reserve/capex math (lifespan calculations)
- Comp adjustments (sqft, beds, baths, age)
- Rule-based warnings and blockers
- Decision thresholds (pursue signal)

### AI does:
- Extract from messy text/docs (listing descriptions, disclosures, inspection reports)
- Summarize findings in plain English
- Prioritize warnings by buyer impact
- Explain conflicts and their implications
- Generate questions for agent/inspector/HOA
- Produce buyer-friendly narrative
- Compare tradeoffs across homes

### AI does NOT:
- Adjudicate truth between sources (resolver does that)
- Override deterministic warnings
- Replace scoring logic
- Invent precise numbers from vague phrases
- Calculate mortgage, tax, or capex numbers
- Decide canonical property facts

## AI PASS 1: Evidence Extraction

### What it extracts:
- Component upgrade claims: "new roof 2024", "HVAC replaced 2023"
- Defect mentions: "prior basement seepage", "foundation crack"
- Restriction mentions: "HOA restricts rentals"
- Seller signals: "sold as-is", "estate sale", "bring all offers"
- Feature claims: "fully finished basement", "gourmet kitchen"

### How it stores them:
```
extracted_fact:
  fact_type: "component_claim" / "defect_mention" / "restriction" / "upgrade_claim"
  raw_text: "new roof installed 2024"
  normalized_value: {component: "roof", year: 2024}
  source_type: "listing_remarks"
  confidence: "high" (explicit year) / "medium" (implied) / "low" (vague)
  requires_verification: true
  evidence_excerpt: "...featuring a new roof installed 2024 and..."
```

### What it does NOT do:
- Set `roof_install_year = 2024` as canonical truth
- Override county permit data
- Convert "newer HVAC" into `hvac_year = 2022`

## Step 3: Deterministic Resolver

### Source priority (highest to lowest):
1. County records / deed / permit (confidence: confirmed, rank: 90)
2. Uploaded inspection report / disclosure (confidence: confirmed, rank: 80)
3. Structured listing fields (confidence: estimated, rank: 40)
4. AI-extracted listing remarks (confidence: inferred, rank: 30)
5. Photo inference (confidence: inferred, rank: 10)

### Resolution rules:
- If county has a value → use it (canonical)
- If county missing but AI extracted with high confidence → use as estimated
- If county contradicts AI extraction → flag conflict, use county, note discrepancy
- If only AI extraction exists with low confidence → use conservative assumption
- If nothing → mark unknown, use default lifespan from year_built

### Output:
```
canonical_input_set:
  roof_year: 2024 (source: listing_remarks, confidence: inferred, verified: false)
  sqft_above_grade: 3845 (source: county, confidence: confirmed)
  ...

conflict_set:
  - field: basement_finished, listing: "fully finished", county: 80 sqft

unresolved_unknowns:
  - HVAC age (no permit, no listing mention)
  - Water heater age
```

## Step 4: Math with Uncertainty

When inputs are uncertain, math engines should support:
- **Known**: use exact value (from county/permit)
- **Estimated**: use AI-extracted value, flag as estimated
- **Unknown**: use conservative assumption range
- **Scenario range**: show best/worst case

Example:
```
Roof remaining life:
  If known (permit): 2024 install → 21 years remaining → no capex 10yr
  If estimated (listing text): "claimed 2024, unverified" → 21yr, flag
  If unknown: assume original (2004) → 1yr remaining → $15-20k capex
```

## Step 5: Deterministic Warning Engine

Produces structured, testable outputs:

```
pursue_signal: yellow

blockers:
  - "Basement sqft misrepresented: listing says fully finished, county shows 80/2120 sqft"
  - "Payment $8,423/mo exceeds target $8,000"

warnings:
  - "Roof age unverified — no county permit found for claimed replacement"
  - "Price 6.1% above Zestimate"
  - "CDOM: 82 days across 2 listing episodes — property has been sitting"

info:
  - "HOA $115/mo — below area average"
  - "Walk-out basement (county confirmed)"
```

## Step 6: AI PASS 2

Takes ALL deterministic outputs and produces buyer-facing narrative:

```
Input to AI:
  - canonical_input_set (resolved facts)
  - conflict_set (what disagrees)
  - math results (payment, capex, offer analysis)
  - warning engine output (blockers, warnings)
  - price benchmarks
  - school ratings
  - comp analysis

Output from AI:
  - pursue_recommendation: pursue / maybe / pass
  - confidence: high / medium / low
  - one_line_summary: "Well-priced 2019 Colonial but basement claims are false"
  - top_red_flags: ["Basement not finished despite listing claim", ...]
  - top_strengths: ["Walk-out basement potential", "Strong schools", ...]
  - unresolved_unknowns: ["HVAC age unverified", ...]
  - questions_for_agent: ["Can you provide permit for basement finish?", ...]
  - next_actions: ["Request HOA reserve study", "Schedule inspection", ...]

All labeled: [FACT] / [ESTIMATE] / [INFERENCE]
```
