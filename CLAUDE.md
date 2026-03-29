# PIPA - Property Intelligence Platform Analysis

Property intelligence platform targeting **Fairfax County** and **Loudoun County**, Virginia. Aggregates county GIS data, public records, listing history, and user-uploaded documents into a unified research workspace for home purchase decisions.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2
- **Database:** SQLite with WAL mode, Alembic migrations
- **HTTP:** httpx (async), Playwright (browser scraping)
- **Frontend:** Next.js, Tailwind CSS
- **Package name:** `pipa` (under `src/pipa/`)

## Key Commands

```bash
pipa serve                    # Start FastAPI backend (uvicorn)
pipa dbinfo                   # Show database stats and table counts
pytest                        # Run test suite
alembic upgrade head          # Apply database migrations
cd frontend && npm run dev    # Start Next.js dev server
```

## Project Structure

```
src/pipa/
  analysis/     # Pure functions: financial, tax, investment, condition, HOA, offer, stress, surrounding, AI synthesis
  api/          # FastAPI routers and app factory
  cli/          # Click CLI commands (serve, dbinfo, etc.)
  clients/      # External API clients (county GIS, ArcGIS, scrapers)
  core/         # Config, dependencies, database engine setup
  models/       # SQLAlchemy ORM models (54 tables)
  report/       # Report generation (HTML, JSON, terminal)
  schemas/      # Pydantic v2 request/response schemas
  services/     # Business logic layer (property, analysis, county, listing, document, alert)
  utils/        # Formatters, geo helpers
  workers/      # Background job scheduler, refresh workers
alembic/        # Database migration scripts
frontend/       # Next.js + Tailwind dashboard
tests/          # pytest with async fixtures, in-memory SQLite
```

## Database

- **54 tables** in SQLite with WAL mode
- Alembic manages schema migrations
- Key tables: `property`, `evidence_item`, `source_record`, `assessment_snapshot`, `listing_event`, `document`, `extracted_fact`, `alert_rule`

## Design Principles

1. **Parcel ID as anchor** — every property is keyed by its county parcel identifier
2. **Append-only snapshots** — assessment values, listing events, and source records are never overwritten; new rows are appended with timestamps
3. **Evidence hierarchy** — county records > deed/permit > licensed API > listing agent > heuristic. Confidence levels are tracked on every `evidence_item`
4. **Pure analysis functions** — all analysis modules (`analysis/`) are pure functions with no I/O; data is passed in as parameters
5. **Source provenance** — every external data fetch is archived in `source_record` with raw payload; every derived fact links back to its source

## Testing

- **pytest** with `pytest-asyncio` for async test support
- In-memory SQLite (`sqlite+aiosqlite:///:memory:`) for test database
- `asyncio_mode = "auto"` in pytest config
- Fixtures in `tests/conftest.py`: `engine`, `db_session`, `client` (FastAPI test client)

## County Data Sources

### Fairfax County
- **GIS/ArcGIS:** Property boundaries, zoning, land use layers
- **iCare:** Tax assessment lookup (parcel-based)
- **PLUS:** Permit and land-use system

### Loudoun County
- **GIS:** ArcGIS REST services for parcel data
- **Parcel DB:** Assessment and ownership records
- **LandMARC:** Permit tracking system
