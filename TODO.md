# PIPA — TODO / Known Gaps

Updated: March 30, 2026

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
