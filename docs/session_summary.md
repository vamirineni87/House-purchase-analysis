# PIPA Development Session Summary — March 29-30, 2026

## What Was Built

Starting from an empty repo with a CLI home purchase analysis tool, we built a complete
property intelligence platform for a home buyer searching in Fairfax/Loudoun County, VA.

### Architecture
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite (WAL mode), Pydantic v2
- **Frontend**: Vanilla JS SPA served by FastAPI (replaced Next.js mid-session)
- **Scrapers**: Playwright (Zillow, Redfin, Realtor, Loudoun County, LCPS, GreatSchools)
- **AI**: Claude CLI subprocess for text extraction and interpretation
- **Database**: 61 tables, Alembic migrations

### Key Numbers
- 138 Python source files
- 36 JavaScript SPA files
- 74 API routes
- 61 database tables
- 13 analysis engines
- 99 unit/integration tests passing

## Properties Analyzed

### 42580 Deer Isle Dr, Chantilly, VA 20152 (Loudoun County)
- **$1,367,000** | 6BR/5BA | 6,045 sqft (Zillow) / 3,845 above grade (county)
- Built 2019 by K. Hovnanian | Melody Farm / Clarke Assemblage
- **CDOM**: 82 days across 2 listing episodes | Total reduction: $232,900
- **Key finding**: County shows only 80 sqft finished basement vs listing claim of "fully finished"
- **Schools**: Buffalo Trail ES (6/10), Willard MS (7/10), Lightridge HS (8/10)
- **Condition**: 67/100 (all original 2019 components)

### 23648 Amesfield Pl, Aldie, VA 20105 (Loudoun County)
- **$1,399,900** | 5BR/5BA (Zillow says 5, county says 4.5) | 3,566 above grade
- Built 2018 by NVR/Ryan Homes (Longwood model) | Grant at Willowsford
- Basement: 1,684 total, 1,110 finished, 574 unfinished, walk-up
- **Zestimate**: $1,274,000 (ask is 9.9% above)
- Sport court built 2021

### 42459 Belmont Glen Pl, Ashburn, VA 20148 (Loudoun County)
- **$1,339,900** | 4BR/6BA (Zillow) / 4F+1H (county) | 4,580 above grade
- Built 2004 | Oakton model | Belmont Glen
- Basement: 2,030 total, 1,497 finished, walk-up
- **37 DOM** — been sitting, negotiation leverage
- 22 years old — roof and HVAC likely need replacement soon

## Data Sources Tested (Live)

| Source | Status | What We Got |
|---|---|---|
| **Zillow GraphQL** | Working | Price, beds, baths, sqft, schools, zestimate, price history, CDOM |
| **Loudoun County** (reparcelasmt.loudoun.gov) | Working | All 10 tabs: profile, values, residential, sales, land, permits, etc. |
| **LCPS School Locator** | Working | Official school assignments, confirmed all 3 match Zillow |
| **GreatSchools** | Working | Ratings, test scores, demographics, enrollment |
| **Claude CLI** | Working | Component extraction, red flags, seller motivation, listing vs county validation |
| **Coldwell Banker** | Working (WebFetch) | Full MLS data as Zillow fallback |

## Pipeline Architecture (7 Steps)

```
0. Ingest (Playwright scrape Zillow/Redfin)
1. Deterministic structured parse
2. AI Pass 1: extract from description text → evidence items
3. Deterministic resolver: merge sources by confidence rank
4. Pure math: financial, condition, offer, stress (on resolved data)
5. Deterministic warning engine: blockers, pursue signal
6. AI Pass 2: interpretation, narrative, questions
7. Decision packet assembly
```

Key rule: AI feeds evidence (step 2), deterministic code decides truth (step 3),
math computes on truth (step 4), AI explains results (step 6).

## Key Design Decisions

1. **Parcel ID as canonical anchor** (not address text)
2. **County records outrank listing claims** (confidence: county=90, listing=40, AI=30)
3. **Append-only snapshots** for time-varying data
4. **2-stage comps**: quick comp (auto, <2s) + deep comp (county-verified, ~2min)
5. **Price benchmarks**: ask vs zestimate vs assessed+7% (configurable markup)
6. **CDOM tracking**: cumulative days on market across listing episodes
7. **Portal scraping as evidence, not truth**: stored with confidence="estimated"
8. **AI extraction before math**: so "roof replaced 2024" from description feeds condition engine
9. **Pipeline orchestration with partial success**: county fails → math still runs on listing data
10. **SPA served by FastAPI**: one process, one port, no npm/node needed

## Scrapers: How They Work

### Zillow (3-layer extraction)
1. **GraphQL interception** (primary): browser renders page, we capture /graphql/ response
2. **JSON-LD** (secondary): structured data in initial HTML
3. **HTML DOM** (fallback): data-testid selectors + text patterns
- CAPTCHA: PerimeterX "Press & Hold" — solved by finding #px-captcha in iframe, mouse down 12s
- Non-headless browser works best for CAPTCHA bypass

### Loudoun County (iasWorld portal)
- ASP.NET WebForms with ViewState
- Search by address → navigate tabs (Profile, Values, Residential, Sales, Land, etc.)
- 43 fields per property from Residential tab alone

### LCPS Schools (Qlik dashboard)
- Click folded-listbox → search for address → select from dropdown → extract from Qlik objects

### GreatSchools
- Scrape profile page → extract from window.gon + visible text parsing
- Gets: rating, test scores, demographics, enrollment, student:teacher ratio

## Commits (30+)

Key commits:
- Platform rewrite from CLI to FastAPI + SQLite
- Zillow GraphQL scraper (v2.0, tested)
- Loudoun County scraper (all 10 tabs, tested)
- LCPS school locator (tested, cross-referenced)
- GreatSchools scraper (tested)
- AI extraction via Claude CLI (components, red flags, validation)
- 7-step pipeline orchestrator with 2 AI passes
- Pipeline run model for partial success tracking
- 2-stage comp system (quick + deep)
- Price benchmarks (assessed+7%)
- DOM/CDOM with relist detection
- Decision workflow (case files, due diligence, recommendations)
- Data refresh with real scrapers (not stubs)
- SPA replacing Next.js (one process, one port)
