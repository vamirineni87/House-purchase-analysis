# PIPA — TODO / Known Gaps

Updated: April 8, 2026

## Status Legend
- DONE = implemented and tested
- PARTIAL = implemented but needs work
- OPEN = not started

---

## Critical: Pipeline & Data Flow

### TODO-001: Pipeline resolver uses reconciled values
**Priority:** High | **Status:** DONE
Pipeline step 3 (resolver) merges county > listing > AI-extracted sources by confidence rank.
Analysis engines run on canonical resolved values, not raw listing data.

### TODO-002: Conflicts flagged in warnings
**Priority:** High | **Status:** PARTIAL
The resolver detects conflicts (e.g., sqft mismatch). The warning engine surfaces them.
AI Pass 2 explains them in plain English. But the decision packet endpoint doesn't
always include them — needs wiring from pipeline results to the /decision/packet API.

### TODO-003: Auto-alerts on county vs portal conflicts
**Priority:** Medium | **Status:** OPEN
When county enrichment runs, compare against existing portal evidence.
Create AlertEvent for significant differences.

### TODO-004: Listing ingest conflict check
**Priority:** Medium | **Status:** OPEN
When re-scraping Zillow, compare new data against existing evidence.
Flag if price changed, sqft changed, status changed.

---

## Scrapers

### TODO-005: Redfin scraper tested on real site
**Priority:** High | **Status:** OPEN
Built with estimated selectors. Needs real-world testing.

### TODO-006: Realtor.com scraper tested on real site
**Priority:** Medium | **Status:** OPEN
Same as Redfin — untested.

### TODO-007: Fairfax County scrapers tested
**Priority:** Medium | **Status:** OPEN
Fairfax iCare and PLUS scrapers built but untested.
Only Loudoun County scrapers have been tested on live sites.

### TODO-008: Broker site scrapers (Coldwell Banker, Compass)
**Priority:** Low | **Status:** OPEN
Reliable Zillow fallback when CAPTCHA blocks. WebFetch confirmed working.

### TODO-009: Zillow CAPTCHA reliability
**Priority:** Medium | **Status:** PARTIAL
Press-and-hold bypass works ~70% of time with non-headless browser.
Need ScrapeRun tracking to monitor success rate over time.

---

## Dashboard / SPA

### TODO-010: SPA views need real-world testing
**Priority:** High | **Status:** PARTIAL
SPA built with 36 JS files. Dashboard loads, property list works.
Property detail needs thorough tab-by-tab testing.
Known issues may exist in module imports and data binding.

### TODO-011: Pipeline polling for running tasks
**Priority:** Medium | **Status:** OPEN
Dashboard should poll every 3s while a pipeline is running.
Currently requires manual page refresh to see results.

### TODO-012: Toast notifications for action results
**Priority:** Medium | **Status:** PARTIAL
Toast system built (toast.js). Need to verify it fires on all actions.

### TODO-013: Add Property modal testing
**Priority:** High | **Status:** OPEN
Modal built but not tested with real Zillow URL ingest flow from SPA.

---

## Analysis Engines

### TODO-014: Current home financials need real values
**Priority:** High | **Status:** OPEN
43629 White Cap Ter (user's current home) has placeholder values:
purchase_price, estimated_value, remaining_mortgage all need real numbers.
Sell-vs-rent analysis meaningless without them.

### TODO-015: Auto-source comps from Zillow nearby sold
**Priority:** Medium | **Status:** PARTIAL
Quick comp runs but finds 0 candidates because Zillow GraphQL
nearby_sold data isn't reliably captured (CAPTCHA interference).

### TODO-016: Neighborhood analysis not connected
**Priority:** Low | **Status:** OPEN
Neighborhood analysis engine exists but no service to fetch real data
from GreatSchools, FBI Crime, Walk Score, Census APIs and pass it through.

---

## Data Quality

### TODO-017: Cross-reference all sources automatically
**Priority:** Medium | **Status:** PARTIAL
DataRefreshService.cross_reference_all() exists but needs testing.
Should run after every county refresh.

### TODO-018: Document extraction via upload
**Priority:** Low | **Status:** OPEN
Document upload endpoint exists. Text extraction (PyMuPDF) exists.
Not wired to the SPA upload UI.

### TODO-019: Comp sourcing from county neighborhood sales
**Priority:** Medium | **Status:** OPEN
Loudoun County "Neighborhood Sales" tab has 18-month sold data.
Not being parsed into comp candidates yet.

---

## Infrastructure

### TODO-020: Source health checker URLs fixed
**Priority:** High | **Status:** DONE
Fixed incorrect URLs for fairfax_gis, loudoun_parcel_db, loudoun_landmarc.

### TODO-021: Background workers need monitoring
**Priority:** Low | **Status:** PARTIAL
APScheduler runs 4 jobs (county_refresh, listing_monitor, alert_evaluator,
source_health_checker). Basic functionality works but no monitoring UI.

### TODO-022: Database backup strategy
**Priority:** Low | **Status:** OPEN
SQLite DB is single file. Need documented backup/restore procedure.

### TODO-023: Settings persistence in SPA
**Priority:** Medium | **Status:** PARTIAL
AppSetting model + API created. SPA settings page built.
Need to verify save/load works end-to-end.

---

## Deferred

### TODO-024: PostgreSQL migration
SQLAlchemy ORM makes this a connection string change. Not urgent for single-user.

### TODO-025: HTML/PDF report export
Report generator exists. Need SPA button to trigger export.

### TODO-026: Full test coverage
99 tests passing but coverage is uneven. Need integration tests for
scraper → pipeline → dashboard flow.

### TODO-027: Fairfax County support
Only Loudoun County scrapers tested. Fairfax iCare/PLUS need testing.
Most properties in user's search area are Loudoun.

---

## Known gaps from April 8 2026 code review

### TODO-028: Resolver `set_canonical` conflicts have no `severity` field
**Priority:** Medium | **Status:** OPEN
The rank-merge conflict detector in `_resolve_canonical` produces conflict
dicts without a `severity` key, while the new explicit cross-checks I added
(parcel_id, lot_sqft, above_grade_sqft, total_livable_area) DO set severity.
The UI / warning engine has to fall back to "warning" when severity is
missing. Should normalize so every conflict has a severity field.

### TODO-029: Duplicate parcel_id conflict detection
**Priority:** Low | **Status:** OPEN
When listing parcel_id ≠ county parcel_id, BOTH `set_canonical`'s rank
merge AND the explicit critical-severity check fire. Resolver returns
two conflict entries with the same `field="parcel_id"`. Cosmetic but
the UI sees it as two separate issues. Dedupe by field name.

### TODO-030: `_create_parcel_identifier` doesn't read from normalized `parcel_number`
**Priority:** Medium | **Status:** OPEN
`listing_ingest._create_parcel_identifier` only checks `scraped["parcel_number"]`
which is the legacy direct extraction. The new `_normalize_facts()` parser
sets `parcel_number` from the Details category — same key, so this
*should* work — but the parsing flow only writes `parcel_number` when
GraphQL didn't already set `parcel_id`. Need to verify both paths
populate the ParcelIdentifier table on a Loudoun ingest.

### TODO-031: Heating / Cooling fact parsing only reads items[0]
**Priority:** Low | **Status:** OPEN
`_normalize_facts` heating/cooling sections assume the entire feature
list is concatenated into a single string at `items[0]`. If Zillow ever
splits the list across multiple `<li>` items in the HTML, we'd silently
miss everything after the first one. Defensive fix: iterate the items
list and extend `heating_features` from each.

### TODO-032: Detail page auto-refresh during background pipeline
**Priority:** High | **Status:** OPEN
Now that ingest returns 100ms with a placeholder and runs the full
chain (Zillow scrape → county → schools → quick_comp → AI pipeline)
in the background, the detail page is empty for the first ~3 minutes.
Add a polling mechanism: every 10s while the latest pipeline_run for
this property has status `running` or `queued`, refetch property /
listing / decision data. Stop polling when status is terminal.

### TODO-033: Pipeline-running indicator on the property detail page
**Priority:** Medium | **Status:** OPEN
The property card / detail header should show a "Analyzing..." spinner
or progress bar while the background ingest chain is running. Pulls
from `pipeline_run.status` of the most-recent run.

### TODO-034: Resolver-detected conflicts not surfaced in UI
**Priority:** Medium | **Status:** OPEN
The resolver produces a list of conflicts in `step3_conflicts` and
they're stored on the pipeline run summary. There's no UI section
that displays them — the user has to look at AI Pass 2's text
narrative to see discrepancies. Add a "Listing vs County
Discrepancies" panel to the property detail page that reads
`pipeline_run.summary_json["conflicts"]`.

### TODO-035: AI Pass 1 component extraction is now partly redundant
**Priority:** Low | **Status:** OPEN
With `_normalize_facts` producing typed `roof_material`, `foundation_type`,
`heating_features`, etc. directly from the listing, AI Pass 1's
`extract_components_from_text` is doing duplicate work for material
type — but it's still needed for *age* extraction ("HVAC replaced in
2021"). Could split the prompt: skip the type-extraction part when
the structured fields already exist, only ask for ages and red flags.
Saves ~30s per ingest.

### TODO-036: Redfin / Realtor URL slug parsers for instant ingest
**Priority:** Medium | **Status:** OPEN
`create_placeholder_from_url` only handles Zillow URLs because
`_parse_zillow_url_slug` is the only parser. Redfin and Realtor
listings throw `"Instant ingest currently only supports Zillow URLs"`.
Add equivalent slug parsers for the other two so all source sites
get the instant 100ms response path.

### TODO-037: Verify `dependencies.py:logs/server.log` cleanup
**Priority:** Low | **Status:** OPEN
We added `logs/server.log` to .gitignore but the existing
`logs/backend.log` is still tracked and accumulates indefinitely.
Should `git rm --cached logs/backend.log` and add `logs/*.log` to
.gitignore so the log file isn't carried in every commit.

### TODO-038: pipa.db-shm / pipa.db-wal still tracked
**Priority:** Low | **Status:** OPEN
Both files are SQLite WAL runtime files that change on every server
run, polluting `git status` and creating commit noise. Should
`git rm --cached pipa.db-shm pipa.db-wal` and rely on the existing
`*.db` gitignore (or add explicit `pipa.db*`).

### TODO-039: Floor-plan visualization for the rooms layout
**Priority:** Low | **Status:** OPEN
The Zillow scrape now produces 17 rooms with width × length per room.
Currently displayed as a table on the listing tab. Could be rendered
as a rough floor-plan grid grouped by level (Lower / Main / Upper)
to give buyers a visual sense of the layout.

### TODO-040: Old `lot_sqft_listing` field name overlap with `lot_sqft`
**Priority:** Low | **Status:** OPEN
GraphQL extraction sets `lot_sqft` (top-level Zillow field). The
new `_normalize_facts` Lot section sets `lot_sqft_listing`. Both can
exist simultaneously. The pipeline's listing_map uses `lot_sqft` (old
key); the resolver passthrough uses `lot_sqft_listing`. Should
consolidate to one canonical name to avoid confusion downstream.
