# PIPA - Property Intelligence Platform Analysis

Buyer copilot for evaluating listed homes in **Fairfax County** and **Loudoun County**, Virginia. Scrapes Zillow/county records, runs 13 analysis engines, surfaces red flags, and helps decide whether to pursue.

## Quick Start

```bash
pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn pipa.api.app:app --port 8000
# Open http://localhost:8000
```

No npm. No build step. No second process.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2
- **Database:** SQLite with WAL mode, Alembic migrations (61 tables)
- **Frontend:** Vanilla JS SPA served by FastAPI (Tailwind CSS via CDN)
- **Scrapers:** Playwright (Zillow, Loudoun County, LCPS, GreatSchools)
- **AI:** Claude CLI subprocess for text extraction/interpretation
- **HTTP:** httpx (async), Playwright (browser scraping)
- **Package name:** `pipa` (under `src/pipa/`)

## Key Commands

```bash
pipa serve                    # Start FastAPI backend (uvicorn)
pipa dbinfo                   # Show database stats and table counts
pytest                        # Run test suite (99 tests)
alembic upgrade head          # Apply database migrations
python run_pipeline.py <url>  # Run full pipeline from CLI
```

## Project Structure

```
src/pipa/
  analysis/     # 13 pure-function analysis engines (no I/O)
  api/          # FastAPI routers and app factory (74 routes)
  cli/          # Click CLI commands (serve, dbinfo)
  clients/      # External API clients + Playwright scrapers
  core/         # Config, dependencies, database engine, events
  models/       # SQLAlchemy ORM models (61 tables)
  report/       # Report generation (HTML, JSON)
  schemas/      # Pydantic v2 request/response schemas
  services/     # Pipeline, ingest, analysis, refresh, AI extraction
  static/       # SPA frontend (index.html + 36 JS modules)
  utils/        # Formatters, geo helpers
  workers/      # Background scheduler, refresh workers
```

## Database

- **61 tables** in SQLite with WAL mode
- Alembic manages schema migrations
- Key tables: `property`, `evidence_item`, `source_record`, `listing_page_snapshot`, `assessment_snapshot`, `component_system`, `pipeline_run`, `decision_case`, `app_setting`

## Pipeline (7 Steps)

```
0. Ingest (scrape Zillow/Redfin)
1. Deterministic structured parse
2. AI Pass 1: extract from text → evidence items
3. Resolver: merge sources by confidence rank
4. Pure math: financial, condition, offer, stress
5. Warning engine: blockers, pursue signal
6. AI Pass 2: interpretation + narrative
7. Decision packet assembly
```

## Design Principles

1. **Parcel ID as anchor** — county parcel identifier, not address text
2. **Append-only snapshots** — assessments, listings never overwritten
3. **Evidence hierarchy** — county (90) > deed (80) > listing (40) > AI (30)
4. **Pure analysis functions** — no I/O; data passed as parameters
5. **Source provenance** — every fetch archived with raw payload
6. **AI enriches evidence, code decides truth**

## Testing

- **pytest** with `pytest-asyncio` for async support
- In-memory SQLite for test database
- `asyncio_mode = "auto"` in pytest config
- 99 tests passing

## County Data Sources

### Loudoun County (tested)
- **Assessment:** reparcelasmt.loudoun.gov (Playwright, all 10 tabs)
- **GIS:** logis.loudoun.gov ArcGIS REST
- **Schools:** dashboards.lcps.org (Qlik dashboard)

### Fairfax County (built, untested)
- **GIS:** fairfaxcounty.gov/euclid MapServer
- **iCare:** Assessment lookup
- **PLUS:** Building permits
