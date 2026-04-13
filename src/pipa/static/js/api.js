/**
 * API client for the PIPA backend.
 *
 * Vanilla JS port of frontend/src/lib/api.ts.  Every method returns a
 * Promise that resolves to the parsed JSON body or rejects with an Error
 * whose message is the `detail` field from the backend.
 *
 * Base URL is same-origin: /api/v1
 */

const BASE_URL = '/api/v1';

// ── Core request wrapper ────────────────────────────────────────────

/**
 * Make an HTTP request against the PIPA API.
 *
 * @param {string} path     Path relative to BASE_URL, e.g. "/properties"
 * @param {RequestInit} [options]
 * @returns {Promise<*>}
 */
async function request(path, options) {
    const url = `${BASE_URL}${path}`;
    const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        ...options,
    });

    if (!res.ok) {
        let detail = res.statusText;
        try {
            const body = await res.json();
            if (body.detail) detail = body.detail;
        } catch { /* ignore parse errors */ }
        throw new Error(detail || `HTTP ${res.status}`);
    }

    if (res.status === 204) return undefined;
    return res.json();
}

// ── Public API ──────────────────────────────────────────────────────

export const api = {

    // ================================================================
    // Properties
    // ================================================================

    /** List all property summaries. */
    listProperties() {
        return request('/properties');
    },

    /** Get a single property with full detail. */
    getProperty(id) {
        return request(`/properties/${id}`);
    },

    /** Get raw listing data scraped for a property. */
    getListingData(id) {
        return request(`/properties/${id}/listing-data`);
    },

    /** Get stored analysis results for a property. */
    getAnalysisResults(id) {
        return request(`/properties/${id}/analysis-results`);
    },

    /** Create a property manually. */
    createProperty(data) {
        return request('/properties', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /** Delete a property by ID. */
    deleteProperty(id) {
        return request(`/properties/${id}`, { method: 'DELETE' });
    },

    /** Ingest a property from a listing URL or address. */
    ingestProperty(data) {
        return request('/properties/ingest', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    // ================================================================
    // Pipeline
    // ================================================================

    /** Kick off a full pipeline run (or a specific run_type). */
    runPipeline(propertyId, runType = 'full_pipeline') {
        return request(`/properties/${propertyId}/pipeline/run`, {
            method: 'POST',
            body: JSON.stringify({ run_type: runType, initiated_by: 'user' }),
        });
    },

    /** Run a single pipeline task by name. */
    runTask(propertyId, taskName) {
        return request(`/properties/${propertyId}/pipeline/run-task`, {
            method: 'POST',
            body: JSON.stringify({ task_name: taskName }),
        });
    },

    /** Cancel a running pipeline for a property. */
    cancelPipeline(propertyId) {
        return request(`/properties/${propertyId}/pipeline/cancel`, {
            method: 'POST',
        });
    },

    /** List pipeline runs for a property. */
    getPipelineRuns(propertyId, limit = 10) {
        return request(`/properties/${propertyId}/pipeline/runs?limit=${limit}`);
    },

    /** Get a specific pipeline run by its own ID. */
    getPipelineRun(runId) {
        return request(`/pipeline-runs/${runId}`);
    },

    /** Re-run a single task within an existing pipeline run. */
    rerunTask(runId, taskName) {
        return request(`/pipeline-runs/${runId}/rerun-task`, {
            method: 'POST',
            body: JSON.stringify({ task_name: taskName }),
        });
    },

    // ================================================================
    // Watchlist
    // ================================================================

    /** List watchlist entries, optionally filtered by stage. */
    listWatchlist(stage) {
        const qs = stage ? `?stage=${encodeURIComponent(stage)}` : '';
        return request(`/watchlist${qs}`);
    },

    /** Add a property to the watchlist. */
    addToWatchlist(data) {
        return request('/watchlist', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /** Update the stage of a watchlist entry. */
    updateWatchlistStage(id, stage) {
        return request(`/watchlist/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ stage }),
        });
    },

    /** Remove a property from the watchlist. */
    removeFromWatchlist(id) {
        return request(`/watchlist/${id}`, { method: 'DELETE' });
    },

    // ================================================================
    // Analysis
    // ================================================================

    /** Run financial analysis with custom parameters. */
    runFinancialAnalysis(propertyId, data) {
        return request(`/properties/${propertyId}/analysis/financial`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /** Run offer strategy analysis. */
    runOfferAnalysis(propertyId, data) {
        return request(`/properties/${propertyId}/analysis/offer`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /** Run stress test scenarios. */
    runStressTest(propertyId, data) {
        return request(`/properties/${propertyId}/analysis/stress`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /** Run all analysis modules at once. */
    runFullAnalysis(propertyId, data) {
        return request(`/properties/${propertyId}/analysis/full`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    // ================================================================
    // Comps
    // ================================================================

    /** Quick comp search (listing-level). */
    runCompsQuick(propertyId) {
        return request(`/properties/${propertyId}/comps/quick`, {
            method: 'POST',
        });
    },

    /** Deep comp analysis (county-enriched). */
    runCompsDeep(propertyId) {
        return request(`/properties/${propertyId}/comps/deep`, {
            method: 'POST',
        });
    },

    /** Get previously computed comp results. */
    getComps(propertyId) {
        return request(`/properties/${propertyId}/comps`);
    },

    // ================================================================
    // Refresh / Freshness
    // ================================================================

    /** Refresh all data sources for a property. */
    refreshAll(propertyId) {
        return request(`/properties/${propertyId}/refresh`, {
            method: 'POST',
        });
    },

    /** Refresh a single data source. */
    refreshSource(propertyId, source) {
        return request(`/properties/${propertyId}/refresh/${encodeURIComponent(source)}`, {
            method: 'POST',
        });
    },

    /** Get freshness status for each data source. */
    getFreshness(propertyId) {
        return request(`/properties/${propertyId}/freshness`);
    },

    /** Cross-reference data sources and find conflicts. */
    crossReference(propertyId) {
        return request(`/properties/${propertyId}/cross-reference`);
    },

    // ================================================================
    // Decision
    // ================================================================

    /** Get the decision case for a property. */
    getDecision(propertyId) {
        return request(`/properties/${propertyId}/decision`);
    },

    /** Create a new decision case. */
    createDecision(propertyId) {
        return request(`/properties/${propertyId}/decision`, {
            method: 'POST',
        });
    },

    /** Update a decision case with partial data. */
    updateDecision(propertyId, data) {
        return request(`/properties/${propertyId}/decision`, {
            method: 'PATCH',
            body: JSON.stringify(data),
        });
    },

    /** Get the full decision packet (all 7 sections). */
    getDecisionPacket(propertyId) {
        return request(`/properties/${propertyId}/decision/packet`);
    },

    /** Get AI-generated recommendations. */
    getRecommendations(propertyId) {
        return request(`/properties/${propertyId}/decision/recommendations`);
    },

    // ================================================================
    // County
    // ================================================================

    /** Get all county data (assessments, permits, deeds). */
    getCountyData(propertyId) {
        return request(`/properties/${propertyId}/county`);
    },

    /** Get assessment snapshots. */
    getAssessments(propertyId) {
        return request(`/properties/${propertyId}/county/assessments`);
    },

    /** Get permit records. */
    getPermits(propertyId) {
        return request(`/properties/${propertyId}/county/permits`);
    },

    /** Get deed / sale records. */
    getDeeds(propertyId) {
        return request(`/properties/${propertyId}/county/deeds`);
    },

    /** Trigger a refresh of county data. */
    refreshCountyData(propertyId) {
        return request(`/properties/${propertyId}/county/refresh`, {
            method: 'POST',
        });
    },

    // ================================================================
    // Notes
    // ================================================================

    /** List notes for a property. */
    listNotes(propertyId) {
        return request(`/properties/${propertyId}/notes`);
    },

    /** Create a note on a property. */
    createNote(propertyId, data) {
        return request(`/properties/${propertyId}/notes`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /** Delete a note. */
    deleteNote(propertyId, noteId) {
        return request(`/properties/${propertyId}/notes/${noteId}`, {
            method: 'DELETE',
        });
    },

    // ================================================================
    // Component overrides — manual install-year corrections
    // ================================================================

    /** List all manual component overrides for a property. */
    listComponentOverrides(propertyId) {
        const pid = encodeURIComponent(propertyId);
        return request(`/properties/${pid}/component-overrides`);
    },

    /**
     * Set or update a manual component install-year override.
     * @param {string} propertyId
     * @param {string} canonicalKey  e.g. 'hvac', 'water_heater', 'roof'
     * @param {number} year          Install year (1800..2100)
     * @param {string} [notes]       Optional context
     */
    setComponentOverride(propertyId, canonicalKey, year, notes) {
        const pid = encodeURIComponent(propertyId);
        const key = encodeURIComponent(canonicalKey);
        return request(`/properties/${pid}/component-overrides/${key}`, {
            method: 'PUT',
            body: JSON.stringify({ year, notes: notes || null }),
        });
    },

    /** Remove a manual override (revert to AI/county/year_built default). */
    deleteComponentOverride(propertyId, canonicalKey) {
        const pid = encodeURIComponent(propertyId);
        const key = encodeURIComponent(canonicalKey);
        return request(`/properties/${pid}/component-overrides/${key}`, {
            method: 'DELETE',
        });
    },

    // ================================================================
    // Alerts
    // ================================================================

    /** List alerts with optional filters. */
    listAlerts(opts) {
        const params = new URLSearchParams();
        if (opts?.unread_only) params.set('unread_only', 'true');
        if (opts?.property_id) params.set('property_id', opts.property_id);
        if (opts?.limit) params.set('limit', String(opts.limit));
        const qs = params.toString();
        return request(`/alerts${qs ? `?${qs}` : ''}`);
    },

    /** Mark a single alert as read. */
    markAlertRead(alertId, isRead = true) {
        return request(`/alerts/${alertId}`, {
            method: 'PATCH',
            body: JSON.stringify({ is_read: isRead }),
        });
    },

    /** Mark all alerts as read. */
    markAllAlertsRead() {
        return request('/alerts/mark-all-read', { method: 'POST' });
    },

    // ================================================================
    // Comparison
    // ================================================================

    /** Compare multiple properties by ID with optional weights. */
    compareProperties(data) {
        return request('/comparison', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    // ================================================================
    // Rates
    // ================================================================

    /** Get current mortgage rates. */
    getMortgageRates() {
        return request('/rates/mortgage');
    },

    /** Get tax rates for a county. */
    getTaxRate(county) {
        return request(`/rates/tax/${encodeURIComponent(county)}`);
    },

    // ================================================================
    // Settings
    // ================================================================

    /** Get all settings grouped by category. */
    getSettings() {
        return request('/settings');
    },

    /** Save a single setting. */
    saveSetting(key, value, category = 'ui_defaults') {
        return request('/settings', {
            method: 'POST',
            body: JSON.stringify({ key, value, category }),
        });
    },

    /** Reset all settings to defaults. */
    resetSettings() {
        return request('/settings/reset', { method: 'POST' });
    },

    // ================================================================
    // Surrounding
    // ================================================================

    /** Get surrounding / neighborhood data for a property. */
    getSurrounding(propertyId) {
        return request(`/properties/${propertyId}/surrounding`);
    },

    // ================================================================
    // HOA
    // ================================================================

    /** Get HOA data for a property. */
    getHOA(propertyId) {
        return request(`/properties/${propertyId}/hoa`);
    },

    // ================================================================
    // Documents
    // ================================================================

    /** List documents for a property. */
    listDocuments(propertyId) {
        return request(`/properties/${propertyId}/documents`);
    },

    // ================================================================
    // Rent vs Sell
    // ================================================================

    /** Compute all four strategies from an assumption set. */
    computeRentVsSell(assumptions) {
        return request('/rent-vs-sell/calculate', {
            method: 'POST',
            body: JSON.stringify({ assumptions }),
        });
    },

    /** Compute a sensitivity heatmap (server-side LRU cached). */
    computeRentVsSellSensitivity(assumptions, preset, comparator, horizon) {
        return request('/rent-vs-sell/sensitivity', {
            method: 'POST',
            body: JSON.stringify({
                assumptions,
                preset: preset || 'value_x_rent',
                comparator: comparator || 'sell_vs_keep_5y',
                horizon: horizon || '5y',
            }),
        });
    },

    /** Pull new_home fields prefilled from a PIPA property. */
    rentVsSellPrefill(propertyId) {
        const pid = encodeURIComponent(propertyId);
        return request(`/rent-vs-sell/prefill/${pid}`);
    },

    /** List current-home profiles. */
    listCurrentHomeProfiles() {
        return request('/rent-vs-sell/current-home-profiles');
    },

    createCurrentHomeProfile(data) {
        return request('/rent-vs-sell/current-home-profiles', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    updateCurrentHomeProfile(id, data) {
        const pid = encodeURIComponent(id);
        return request(`/rent-vs-sell/current-home-profiles/${pid}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    deleteCurrentHomeProfile(id) {
        const pid = encodeURIComponent(id);
        return request(`/rent-vs-sell/current-home-profiles/${pid}`, {
            method: 'DELETE',
        });
    },

    bootstrapDefaultCurrentHomeProfile() {
        return request('/rent-vs-sell/current-home-profiles/bootstrap-default', {
            method: 'POST',
        });
    },

    listRentVsSellRuns() {
        return request('/rent-vs-sell/runs');
    },

    getRentVsSellRun(id) {
        const rid = encodeURIComponent(id);
        return request(`/rent-vs-sell/runs/${rid}`);
    },

    createRentVsSellRun(data) {
        return request('/rent-vs-sell/runs', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    updateRentVsSellRun(id, data) {
        const rid = encodeURIComponent(id);
        return request(`/rent-vs-sell/runs/${rid}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    deleteRentVsSellRun(id) {
        const rid = encodeURIComponent(id);
        return request(`/rent-vs-sell/runs/${rid}`, {
            method: 'DELETE',
        });
    },

    duplicateRentVsSellRun(id) {
        const rid = encodeURIComponent(id);
        return request(`/rent-vs-sell/runs/${rid}/duplicate`, {
            method: 'POST',
        });
    },

    compareRentVsSellRuns(runIds) {
        return request('/rent-vs-sell/runs/compare', {
            method: 'POST',
            body: JSON.stringify({ run_ids: runIds }),
        });
    },

    // ================================================================
    // Health
    // ================================================================

    /** Backend health check. */
    health() {
        return request('/../../health');
    },
};
