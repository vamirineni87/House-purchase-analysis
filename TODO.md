# PIPA — TODO / Known Gaps

## Critical: Data Conflict Handling

The evidence model and reconciliation service exist, but aren't wired into the analysis and decision flows.

### TODO-001: Analysis engines should use reconciled values
**Priority:** High
**Status:** Open

Analysis engines (financial, tax, investment, condition, etc.) currently take raw parameters passed by the caller. They should receive values that have been reconciled across sources — i.e., the analysis_service should call `SourceReconciliationService.reconcile_field()` for key fields (sqft, year_built, lot_size, hoa, annual_tax) before passing them to the analysis functions.

**Where:** `src/pipa/services/analysis_service.py` — before calling each analysis engine, reconcile key fields from the evidence table and pass the best-confidence values.

### TODO-002: Auto-flag conflicts as red flags in decision packet
**Priority:** High
**Status:** Open

When `generate_decision_packet()` runs, it should call `SourceReconciliationService.find_conflicts()` and surface any conflicts as red flags in the Hidden Cost / QUICK TAKE sections. Example: "Zillow lists 6,045 sqft but county records show 3,845 sqft above grade — verify whether finished basement is included."

**Where:** `src/pipa/services/decision_service.py` — in `generate_decision_packet()`, after loading analysis results, also run conflict detection and append to red_flags.

### TODO-003: Auto-create alerts when county data contradicts portal data
**Priority:** Medium
**Status:** Open

When county enrichment runs (`county_service.refresh_county_data()`), compare newly stored evidence items against existing portal-sourced evidence. If any key field differs, create an `AlertEvent` with severity based on the magnitude of the difference (e.g., 5% sqft difference = warning, 20% = critical).

**Where:** `src/pipa/services/county_service.py` — after storing county evidence items, compare against existing evidence for same fields. `src/pipa/services/alert_service.py` to create alerts.

### TODO-004: Listing ingest should check for existing conflicting evidence
**Priority:** Medium
**Status:** Open

When `ListingIngestService.ingest_from_url()` stores evidence items from Zillow/Redfin, it should check if any existing evidence (from a prior source) conflicts. If so, log a warning and optionally create a due diligence item.

**Where:** `src/pipa/services/listing_ingest.py` — after creating evidence items, call `SourceReconciliationService.find_conflicts()`.

### TODO-005: Conflict display in dashboard
**Priority:** Medium
**Status:** Open

No UI currently shows data conflicts. The property detail page should have a "Data Quality" section or badge that shows:
- Number of fields with conflicting sources
- Which source is being trusted and why
- Option to override (manual user input as highest confidence)

**Where:** `frontend/src/app/properties/[id]/page.tsx` — new tab or section. API: `GET /properties/{id}/conflicts` (endpoint doesn't exist yet).

---

## Dashboard Gaps

### TODO-006: Analysis results not displayed per property
**Priority:** High
**Status:** Open

Only the Financial tab has a working panel (`FinancialPanel.tsx`). The other 9 analysis engines have API endpoints but no dashboard components:
- Tax analysis panel
- Investment projections panel
- Condition / capex panel
- Offer strategy panel
- Stress test panel
- HOA risk panel
- Appraisal / comps panel
- Insurance / risk panel
- Surrounding area panel

**Where:** `frontend/src/components/analysis/` — need 9 more panel components. `frontend/src/app/properties/[id]/page.tsx` — wire into tabs.

### TODO-007: Decision packet not rendered in dashboard
**Priority:** High
**Status:** Open

The 7-section decision packet (`GET /properties/{id}/decision/packet`) returns structured data but has no frontend rendering. This should be the primary view when looking at a property — "Should I pursue this?"

**Where:** `frontend/src/components/decision/DecisionPacket.tsx` (doesn't exist). Should render all 7 sections: Quick Take, Price View, Monthly Cost, Hidden Cost, Community, Current Home Impact, Next Actions.

### TODO-008: Due diligence items not in dashboard
**Priority:** Medium
**Status:** Open

Due diligence items (checklist of things to verify/request) have API endpoints but no UI. Need a checklist component on the property detail page with add/update/resolve functionality.

**Where:** `frontend/src/components/decision/DueDiligenceList.tsx` (doesn't exist).

### TODO-009: No "Refresh" button for county/listing data
**Priority:** Medium
**Status:** Open

APIs exist (`POST /properties/{id}/county/refresh`) but no dashboard button. User should be able to click "Refresh County Data" or "Re-scrape Listing" from the property detail page.

**Where:** `frontend/src/app/properties/[id]/page.tsx` — add refresh buttons that call the APIs.

### TODO-010: Price history chart not rendered
**Priority:** Medium
**Status:** Open

Full price history is captured by Zillow GraphQL scraper (dates, prices, events) and stored in listing_page_snapshot.parsed_fields. Not rendered in any chart or timeline.

**Where:** `frontend/src/components/analysis/PriceHistoryChart.tsx` (doesn't exist).

### TODO-011: Comparison page is basic
**Priority:** Low
**Status:** Open

The comparison page exists but only shows basic scoring. Needs side-by-side decision packets, monthly cost comparison, and "which one should I pursue?" recommendation.

**Where:** `frontend/src/app/comparison/page.tsx`.

---

## Scraping / Data Ingestion

### TODO-012: Redfin and Realtor scrapers not tested on real sites
**Priority:** High
**Status:** Open

The Redfin and Realtor Playwright scrapers are built with estimated CSS selectors but have NOT been tested against real listing pages. Need real-world testing and selector adjustment.

**Where:** `src/pipa/clients/scrapers/redfin.py`, `src/pipa/clients/scrapers/realtor.py`.

### TODO-013: County scrapers not tested on real sites
**Priority:** High
**Status:** Open

Fairfax iCare, Fairfax PLUS, Loudoun parcel DB, and Loudoun LandMARC scrapers are built with estimated selectors. Need real-world testing.

**Where:** `src/pipa/clients/scrapers/fairfax_icare.py`, `fairfax_plus.py`, `loudoun_parcel.py`, `loudoun_landmarc.py`.

### TODO-014: County ArcGIS clients not tested against live endpoints
**Priority:** High
**Status:** Open

Fairfax and Loudoun GIS clients have correct base URLs but layer IDs and field mappings are estimated. Need to test against actual MapServer endpoints.

**Where:** `src/pipa/clients/arcgis/fairfax_gis.py`, `loudoun_gis.py`.

### TODO-015: Zillow scraper CAPTCHA success rate needs monitoring
**Priority:** Medium
**Status:** Open

Press-and-hold CAPTCHA bypass works but is not 100% reliable. Need to track success rate via `ScrapeRun` records and fall back to broker sites (Coldwell Banker, Compass, etc.) when Zillow blocks.

**Where:** `src/pipa/clients/scrapers/zillow.py` — should record success/failure in `ScrapeRun` table. Fallback scraper chain not implemented.

### TODO-016: Broker site scrapers not built
**Priority:** Medium
**Status:** Open

Coldwell Banker, Compass, RE/MAX, Movoto show the same MLS data as Zillow/Redfin but without anti-bot measures. These would be reliable fallbacks when portal scraping fails. WebFetch from Coldwell Banker was confirmed working.

**Where:** `src/pipa/clients/scrapers/` — need `coldwell_banker.py`, `compass.py`, etc.

---

## Enrichment Pipeline

### TODO-017: Split county enrichment into QUICK vs DEEP
**Priority:** Medium
**Status:** Open

Currently county enrichment is one block. Should split into:
- **QUICK** (runs immediately on ingest): parcel lookup, assessment, deed/sale history, zoning, flood basics
- **DEEP** (runs on-demand for shortlisted): permits, plats, legal chain, GIS overlays, surrounding parcels, development cases

**Where:** `src/pipa/services/county_service.py` — add `quick_enrich()` and `deep_enrich()` methods.

### TODO-018: Split surrounding analysis into LIGHT vs HEAVY
**Priority:** Low
**Status:** Open

- **LIGHT**: adjacent parcels, nearest solds/listings, basic turnover/investor clues
- **HEAVY**: deep permit patterns, stability model, development cases, builder cluster analysis

Only run HEAVY on shortlisted homes.

**Where:** `src/pipa/services/nearby_discovery.py`, `micro_market.py`.

### TODO-019: HOA data is manual-only
**Priority:** Medium
**Status:** Open

No automated HOA data source. User must manually enter dues/rules/reserve info or upload HOA docs for extraction. Could potentially scrape HOA management company sites or extract from listing remarks.

---

## Analysis Engine Gaps

### TODO-020: Appraisal comps not auto-sourced
**Priority:** Medium
**Status:** Open

Appraisal analysis requires manually-provided comparable sales. Should auto-source from:
- Zillow GraphQL nearby sold data
- RentCast comparable sales API
- County deed records (nearby recent sales)

**Where:** `src/pipa/services/analysis_service.py` — before running appraisal, query available comp sources.

### TODO-021: Neighborhood analysis not connected to real data
**Priority:** Low
**Status:** Open

Neighborhood analysis (schools, crime, walkability, flood, demographics) has the analysis engine but no service to fetch real data from GreatSchools, FBI Crime, Walk Score, Census APIs and pass it through.

**Where:** `src/pipa/services/analysis_service.py` — need service method that fetches from API clients and feeds the neighborhood analyzer.

### TODO-022: Insurance analysis needs flood zone data
**Priority:** Low
**Status:** Open

Insurance analysis works but flood zone data isn't being fetched from OpenFEMA or county GIS overlays. Currently returns "N/A" for flood insurance.

---

## Current Home Configuration

### TODO-023: Current home financials need real values
**Priority:** High
**Status:** Open

43629 White Cap Ter is configured in `config.yaml` but financial details are placeholder zeros:
- purchase_price: 0 (user needs to provide)
- estimated_value: 0
- remaining_mortgage: 0
- years_as_primary: 0
- estimated_monthly_rent: 0

Sell-vs-rent analysis uses these values — results are meaningless until populated.

**Where:** `config.example.yaml` and `src/pipa/core/config.py` CurrentHome class.

---

## Infrastructure

### TODO-024: Background workers not started by default
**Priority:** Low
**Status:** Open

APScheduler is wired into FastAPI lifespan but workers haven't been tested end-to-end. The scheduler uses a PID file lock for single-writer, but no verification that the scheduled jobs actually execute correctly.

### TODO-025: No database backup/restore strategy
**Priority:** Low
**Status:** Open

SQLite DB is a single file. Need a backup script and documented restore procedure. Important because the DB accumulates scraped data, evidence items, and decision workflow state.

### TODO-026: No SQLite → PostgreSQL migration tested
**Priority:** Low
**Status:** Open

The plan calls for eventual PostgreSQL migration. All SQL goes through SQLAlchemy ORM, so it should be a connection string change + Alembic migration, but this hasn't been tested.

---

## Testing

### TODO-027: Integration tests for scraper → analysis → decision pipeline
**Priority:** Medium
**Status:** Open

No end-to-end test that: ingests a listing URL → stores evidence → runs analysis → generates decision packet. Current tests cover individual units but not the full pipeline.

### TODO-028: No tests for conflict detection + reconciliation
**Priority:** Medium
**Status:** Open

`SourceReconciliationService` has no unit tests. Need tests for:
- Two sources agree → no conflict
- Two sources disagree → conflict flagged, highest rank wins
- County overrides portal data
- Missing source registry entry falls back to heuristic rank

### TODO-029: Scraper tests need recorded responses (VCR)
**Priority:** Low
**Status:** Open

Scraper tests should use recorded HTTP responses (via `respx` or `vcrpy`) so they don't hit real sites. Currently no scraper tests at all.
