/**
 * PIPA SPA entry point.
 *
 * Registers all routes, initialises the router, and keeps the sidebar
 * active-link highlight in sync with the current route.
 *
 * Top-level views (dashboard, properties, alerts, comparison, settings)
 * delegate to their dedicated modules under views/.
 *
 * Property detail is handled inline here because the detail sub-modules
 * (tab renderers) are loaded progressively — this coordinator provides
 * the working fallback.
 */

import { initRouter, navigate } from './router.js';
import { on } from './events.js';
import { api } from './api.js';
import { showToast } from './toast.js';
import { Store, updateStore, clearViewState } from './store.js';
import {
    formatCurrency, formatDate, formatDateTime, formatDuration,
    escapeHtml, renderTable, badge,
} from './utils.js';
import { TAB_IDS, STATUS_COLORS, SEVERITY_COLORS } from './constants.js';

// ── Existing view modules ───────────────────────────────────────────

import * as dashboardView from './views/dashboard.js';
import * as propertiesView from './views/properties.js';
import * as alertsView from './views/alerts.js';
import * as comparisonView from './views/comparison.js';
import * as settingsView from './views/settings.js';
import * as rentVsSellView from './views/rent_vs_sell/index.js';

// ── DOM refs ────────────────────────────────────────────────────────

const appEl = () => document.getElementById('app');
const navLinks = () => document.querySelectorAll('#sidebar-nav .nav-link');

// ── Route registration ──────────────────────────────────────────────

initRouter({
    'dashboard':             (params, query) => dashboardView.load(appEl()),
    'properties':            (params, query) => propertiesView.load(appEl()),
    'property/:id':          renderPropertyDetail,
    'alerts':                (params, query) => alertsView.load(appEl()),
    'comparison':            (params, query) => comparisonView.load(appEl()),
    'settings':              (params, query) => settingsView.load(appEl()),
    'rent-vs-sell':          (params, query) => rentVsSellView.load(appEl(), query),
    'rent-vs-sell/compare':  (params, query) => rentVsSellView.load(appEl(), query),
});

// ── Sidebar active-link highlight ───────────────────────────────────

on('route:changed', ({ name }) => {
    const base = name.split('/')[0];
    navLinks().forEach((link) => {
        const route = link.dataset.route;
        const active = route === base || (route === 'properties' && base === 'property');
        link.classList.toggle('bg-blue-50', active);
        link.classList.toggle('text-blue-700', active);
        link.classList.toggle('font-medium', active);
    });
});

// ── Re-export navigate for external use ─────────────────────────────

export { navigate };

// ====================================================================
// Property Detail — inline coordinator
// ====================================================================

/**
 * Load and render the property detail page.  Tries to import the
 * full detail coordinator (views/detail/index.js) first; if that fails
 * (because sub-modules aren't built yet) it falls back to the inline
 * implementation below.
 */
async function renderPropertyDetail(params, query) {
    const el = appEl();
    const id = params.id;
    const requestedTab = query.tab || 'Summary';

    // Try the full detail coordinator if its sub-modules exist
    try {
        const detailView = await import('./views/detail/index.js');
        detailView.load(el, params);
        return;
    } catch {
        // Fall through to inline implementation
    }

    // ── Inline fallback ─────────────────────────────────────────────

    clearViewState('propertyDetail');
    updateStore('views.propertyDetail.propertyId', id);
    updateStore('views.propertyDetail.activeTab', requestedTab);

    el.innerHTML = `
        <div id="pd-header" class="mb-4">
            <a href="#properties" class="text-sm text-blue-600 hover:underline">&larr; All Properties</a>
            <h2 class="text-2xl font-bold mt-2 text-gray-400">Loading...</h2>
        </div>
        <div id="pd-actions" class="flex flex-wrap gap-2 mb-4"></div>
        <div id="pd-tabs" class="border-b border-gray-200 mb-4"></div>
        <div id="pd-content" class="text-sm text-gray-500">Loading...</div>
    `;

    try {
        const property = await api.getProperty(id);
        updateStore('views.propertyDetail.property', property);

        // Header
        const headerEl = document.getElementById('pd-header');
        const addr = property.addresses?.[0]?.normalized_address || 'Unnamed property';
        const county = property.addresses?.[0]?.county || '';
        const parcel = property.parcel_identifiers?.[0]?.identifier_value || '';
        headerEl.innerHTML = `
            <a href="#properties" class="text-sm text-blue-600 hover:underline">&larr; All Properties</a>
            <h2 class="text-2xl font-bold mt-2">${escapeHtml(addr)}</h2>
            <div class="text-sm text-gray-500 mt-1">
                ${escapeHtml(property.property_type?.replace(/_/g, ' ') || '')}
                ${county ? ` &middot; ${escapeHtml(county)}` : ''}
                ${parcel ? ` &middot; ${escapeHtml(parcel)}` : ''}
            </div>
        `;

        // Action buttons
        const actionsEl = document.getElementById('pd-actions');
        actionsEl.innerHTML = `
            <button id="btn-run-pipeline" class="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50">Run Pipeline</button>
            <button id="btn-refresh-all" class="px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200 transition-colors disabled:opacity-50">Refresh Data</button>
            <button id="btn-delete-prop" class="px-3 py-2 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors">Delete</button>
        `;

        _bindActionButtons(id);

        // Tabs
        _renderTabs(id, requestedTab);

        // Load initial tab content
        _loadTabContent(id, requestedTab);

    } catch (err) {
        el.innerHTML = `
            <a href="#properties" class="text-sm text-blue-600 hover:underline">&larr; All Properties</a>
            <p class="text-red-600 mt-4">Failed to load property: ${escapeHtml(err.message)}</p>
        `;
    }
}

function _bindActionButtons(id) {
    document.getElementById('btn-run-pipeline')?.addEventListener('click', async function () {
        this.disabled = true;
        this.textContent = 'Running...';
        try {
            updateStore('ui.actionLoading', 'pipeline');
            const run = await api.runPipeline(id);
            showToast('Pipeline started', 'success');
            _renderPipelineStatus(run);
        } catch (err) {
            showToast(`Pipeline error: ${err.message}`, 'error');
        } finally {
            this.disabled = false;
            this.textContent = 'Run Pipeline';
            updateStore('ui.actionLoading', null);
        }
    });

    document.getElementById('btn-refresh-all')?.addEventListener('click', async function () {
        this.disabled = true;
        try {
            await api.refreshAll(id);
            showToast('Data refresh triggered', 'success');
        } catch (err) {
            showToast(`Refresh failed: ${err.message}`, 'error');
        } finally {
            this.disabled = false;
        }
    });

    document.getElementById('btn-delete-prop')?.addEventListener('click', async () => {
        if (!confirm('Delete this property? This cannot be undone.')) return;
        try {
            await api.deleteProperty(id);
            showToast('Property deleted', 'info');
            navigate('properties');
        } catch (err) {
            showToast(`Delete failed: ${err.message}`, 'error');
        }
    });
}

// ── Tab bar ─────────────────────────────────────────────────────────

function _renderTabs(propertyId, activeTab) {
    const tabsEl = document.getElementById('pd-tabs');
    if (!tabsEl) return;

    tabsEl.innerHTML = `<nav class="flex gap-1 overflow-x-auto -mb-px">${TAB_IDS.map((tab) => {
        const active = tab === activeTab;
        const cls = active
            ? 'border-blue-600 text-blue-700 font-medium'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300';
        return `<button data-tab="${escapeHtml(tab)}" class="tab-btn px-3 py-2 text-sm border-b-2 whitespace-nowrap transition-colors ${cls}">${escapeHtml(tab)}</button>`;
    }).join('')}</nav>`;

    tabsEl.querySelectorAll('.tab-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            updateStore('views.propertyDetail.activeTab', tab);
            window.history.replaceState(null, '', `#property/${propertyId}?tab=${tab}`);
            _renderTabs(propertyId, tab);
            _loadTabContent(propertyId, tab);
        });
    });
}

// ── Tab content loader ──────────────────────────────────────────────

async function _loadTabContent(propertyId, tab) {
    const el = document.getElementById('pd-content');
    if (!el) return;
    el.innerHTML = '<p class="text-gray-400 py-8 text-center">Loading...</p>';

    try {
        switch (tab) {
            case 'Summary':   await _tabSummary(el, propertyId); break;
            case 'Financial': await _tabFinancial(el, propertyId); break;
            case 'County':    await _tabCounty(el, propertyId); break;
            case 'Condition': await _tabCondition(el, propertyId); break;
            case 'Comps':     await _tabComps(el, propertyId); break;
            case 'Offer':     await _tabOffer(el, propertyId); break;
            case 'Stress':    await _tabStress(el, propertyId); break;
            case 'Decision':  await _tabDecision(el, propertyId); break;
            case 'Notes':     await _tabNotes(el, propertyId); break;
            default:          el.innerHTML = `<p class="text-gray-400">Unknown tab: ${escapeHtml(tab)}</p>`;
        }
    } catch (err) {
        el.innerHTML = `<p class="text-red-600">Error loading ${escapeHtml(tab)}: ${escapeHtml(err.message)}</p>`;
    }
}

// ── Helper: key-value pair ──────────────────────────────────────────

function _kv(label, value) {
    return `<div><div class="text-xs text-gray-400">${escapeHtml(label)}</div><div class="font-medium">${escapeHtml(String(value ?? '\u2014'))}</div></div>`;
}

// ── Helper: section wrapper ─────────────────────────────────────────

function _section(title, innerHtml) {
    return `<div class="bg-white rounded-lg border border-gray-200 p-4 mb-4"><h3 class="font-semibold mb-3">${escapeHtml(title)}</h3>${innerHtml}</div>`;
}

// ── Helper: "run analysis" CTA ──────────────────────────────────────

function _analysisCta(el, id, tab, label, btnId, runFn) {
    el.innerHTML = `
        <p class="text-gray-400 mb-4">No ${escapeHtml(label.toLowerCase())} yet.</p>
        <button id="${escapeHtml(btnId)}" class="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700">Run ${escapeHtml(label)}</button>
    `;
    document.getElementById(btnId)?.addEventListener('click', async () => {
        try {
            showToast(`Running ${label.toLowerCase()}...`, 'info');
            await runFn();
            _loadTabContent(id, tab);
        } catch (err) { showToast(err.message, 'error'); }
    });
}

// ── Tab: Summary ────────────────────────────────────────────────────

async function _tabSummary(el, id) {
    const [listing, freshness, runs] = await Promise.allSettled([
        api.getListingData(id),
        api.getFreshness(id),
        api.getPipelineRuns(id, 3),
    ]);

    let html = '';

    const ld = listing.status === 'fulfilled' ? listing.value : null;
    if (ld?.listing_data) {
        const d = ld.listing_data;
        html += _section('Listing Summary', `
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                ${_kv('Price', formatCurrency(d.price || d.list_price))}
                ${_kv('Beds', d.beds ?? d.bedrooms)}
                ${_kv('Baths', d.baths ?? d.bathrooms)}
                ${_kv('Sqft', d.sqft ?? d.living_area)}
                ${_kv('Year Built', d.year_built)}
                ${_kv('Lot', d.lot_size || d.lot_acres)}
                ${_kv('DOM', d.days_on_market ?? d.dom)}
                ${_kv('Source', ld.source)}
            </div>
        `);
    } else {
        html += '<div class="bg-white rounded-lg border border-gray-200 p-4 mb-4 text-gray-400 text-sm">No listing data yet. Run the pipeline to fetch data.</div>';
    }

    const fr = freshness.status === 'fulfilled' ? freshness.value : null;
    if (fr?.length) {
        html += _section('Data Freshness', renderTable(
            ['Source', 'Last Fetched', 'TTL', 'Status'],
            fr.map((s) => [s.source, formatDate(s.last_fetched), `${s.ttl_hours}h`, s.is_stale ? 'Stale' : 'Fresh']),
            { compact: true }
        ));
    }

    const pr = runs.status === 'fulfilled' ? runs.value : null;
    if (pr?.length) {
        html += _section('Recent Pipeline Runs', renderTable(
            ['Status', 'Type', 'Started', 'Duration'],
            pr.map((r) => [
                r.status, r.run_type, formatDateTime(r.started_at),
                formatDuration(r.completed_at && r.started_at ? new Date(r.completed_at) - new Date(r.started_at) : null),
            ]),
            { compact: true }
        ));
    }

    el.innerHTML = html || '<p class="text-gray-400">No summary data available.</p>';
}

// ── Tab: Financial ──────────────────────────────────────────────────

async function _tabFinancial(el, id) {
    const results = await api.getAnalysisResults(id);
    const fin = results?.analyses?.financial;
    if (!fin) {
        _analysisCta(el, id, 'Financial', 'Financial Analysis', 'btn-run-financial',
            () => api.runFinancialAnalysis(id, {}));
        return;
    }

    let html = '<div class="space-y-4">';

    if (fin.payment_breakdowns) {
        let inner = '';
        for (const [name, bd] of Object.entries(fin.payment_breakdowns)) {
            inner += `<div class="mb-3"><h4 class="text-sm font-medium text-gray-600">${escapeHtml(name)}</h4>`;
            inner += '<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mt-1">';
            inner += _kv('Total', formatCurrency(bd.total));
            inner += _kv('P&I', formatCurrency((bd.principal || 0) + (bd.interest || 0)));
            inner += _kv('Tax', formatCurrency(bd.property_tax));
            inner += _kv('Insurance', formatCurrency(bd.homeowners_insurance));
            if (bd.pmi) inner += _kv('PMI', formatCurrency(bd.pmi));
            if (bd.hoa) inner += _kv('HOA', formatCurrency(bd.hoa));
            inner += '</div></div>';
        }
        html += _section('Monthly Payments', inner);
    }

    if (fin.closing_costs) {
        html += _section('Closing Costs',
            `<div class="text-2xl font-bold text-gray-900">${formatCurrency(fin.closing_costs.total)}</div>`);
    }

    html += '</div>';
    el.innerHTML = html;
}

// ── Tab: County ─────────────────────────────────────────────────────

async function _tabCounty(el, id) {
    const data = await api.getCountyData(id);
    let html = '';

    if (data.assessments?.length) {
        html += _section('Assessments', renderTable(
            ['Year', 'Land', 'Improvement', 'Total', 'Tax Rate', 'Annual Tax'],
            data.assessments.map((a) => [a.tax_year, formatCurrency(a.land_value), formatCurrency(a.improvement_value), formatCurrency(a.total_value), a.tax_rate ?? '\u2014', formatCurrency(a.annual_tax)]),
            { compact: true }
        ));
    }

    if (data.permits?.length) {
        html += _section('Permits', renderTable(
            ['Type', 'Description', 'Est. Cost', 'Issued', 'Status'],
            data.permits.map((p) => [p.type, p.description || '\u2014', formatCurrency(p.estimated_cost), formatDate(p.issue_date), p.status || '\u2014']),
            { compact: true }
        ));
    }

    if (data.deeds?.length) {
        html += _section('Deed / Sale History', renderTable(
            ['Date', 'Price', 'Grantor', 'Grantee', 'Type'],
            data.deeds.map((d) => [formatDate(d.sale_date || d.recorded_date), formatCurrency(d.sale_price), d.grantor || '\u2014', d.grantee || '\u2014', d.deed_type || '\u2014']),
            { compact: true }
        ));
    }

    el.innerHTML = html || '<p class="text-gray-400">No county data available. Try refreshing.</p>';
}

// ── Tab: Condition ──────────────────────────────────────────────────

async function _tabCondition(el, id) {
    const results = await api.getAnalysisResults(id);
    const cond = results?.analyses?.condition;
    if (!cond) {
        // No standalone "Run Condition" button anymore — condition is
        // produced by the pipeline orchestrator from resolver-merged
        // data. Tell the user to run the pipeline.
        el.innerHTML = `
            <p class="text-gray-400 py-8 text-center">
                No condition data yet. Run the pipeline from the property header
                to extract component install years from the listing and county records.
            </p>`;
        return;
    }

    let html = '<div class="space-y-4">';
    html += _section('Condition Score', `
        <div class="text-3xl font-bold">${cond.condition_score ?? '\u2014'}</div>
        <div class="text-sm text-gray-500 mt-1">${cond.components_analyzed ?? 0} components analyzed</div>
    `);

    if (cond.capex_forecast && Object.keys(cond.capex_forecast).length) {
        html += _section('CapEx Forecast', renderTable(
            ['Year', 'Estimated Cost'],
            Object.entries(cond.capex_forecast).map(([yr, cost]) => [yr, formatCurrency(cost)]),
            { compact: true }
        ));
    }

    html += '</div>';
    el.innerHTML = html;
}

// ── Tab: Comps ──────────────────────────────────────────────────────

async function _tabComps(el, id) {
    const data = await api.getComps(id);
    if (!data?.quick_comp && !data?.deep_comp) {
        el.innerHTML = `
            <p class="text-gray-400 mb-4">No comp data yet.</p>
            <div class="flex gap-2">
                <button id="btn-quick-comp" class="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700">Quick Comps</button>
                <button id="btn-deep-comp" class="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700">Deep Comps</button>
            </div>
        `;
        document.getElementById('btn-quick-comp')?.addEventListener('click', async () => {
            try { showToast('Running quick comps...', 'info'); await api.runCompsQuick(id); _loadTabContent(id, 'Comps'); } catch (err) { showToast(err.message, 'error'); }
        });
        document.getElementById('btn-deep-comp')?.addEventListener('click', async () => {
            try { showToast('Running deep comps...', 'info'); await api.runCompsDeep(id); _loadTabContent(id, 'Comps'); } catch (err) { showToast(err.message, 'error'); }
        });
        return;
    }

    let html = '';
    if (data.quick_comp) {
        const qc = data.quick_comp;
        let inner = `<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            ${_kv('Sold', qc.sold_count)}
            ${_kv('Active', qc.active_count)}
            ${_kv('Pending', qc.pending_count)}
            ${_kv('Confidence', qc.quick_confidence)}
        </div>`;
        if (qc.rough_value_band) {
            inner += `<div class="mt-3 text-sm"><span class="font-medium">Value Band:</span> ${formatCurrency(qc.rough_value_band.low)} &ndash; ${formatCurrency(qc.rough_value_band.high)} (mid: ${formatCurrency(qc.rough_value_band.mid)})</div>`;
        }
        html += _section('Quick Comp Summary', inner);
    }

    if (data.deep_comp) {
        const dc = data.deep_comp;
        let inner = '';
        if (dc.value_range) {
            inner += `<div class="text-sm mb-3"><span class="font-medium">Value Range:</span> ${formatCurrency(dc.value_range.low)} &ndash; ${formatCurrency(dc.value_range.high)} (mid: ${formatCurrency(dc.value_range.mid)})</div>`;
        }
        inner += `<div class="text-sm text-gray-500">Confidence: ${escapeHtml(dc.confidence || '\u2014')}</div>`;
        html += _section('Deep Comp Analysis', inner);
    }

    el.innerHTML = html;
}

// ── Tab: Offer ──────────────────────────────────────────────────────

async function _tabOffer(el, id) {
    const results = await api.getAnalysisResults(id);
    const offer = results?.analyses?.offer;
    if (!offer) {
        _analysisCta(el, id, 'Offer', 'Offer Analysis', 'btn-run-offer',
            () => api.runOfferAnalysis(id, {}));
        return;
    }

    let inner = '<div class="grid grid-cols-2 gap-3 text-sm">';
    if (offer.walk_away_price != null) inner += _kv('Walk-Away Price', formatCurrency(offer.walk_away_price));
    if (offer.max_bid) inner += _kv('Max Bid', typeof offer.max_bid === 'object' ? JSON.stringify(offer.max_bid) : formatCurrency(offer.max_bid));
    inner += '</div>';
    el.innerHTML = _section('Offer Strategy', inner);
}

// ── Tab: Stress ─────────────────────────────────────────────────────

async function _tabStress(el, id) {
    const results = await api.getAnalysisResults(id);
    const stress = results?.analyses?.stress;
    if (!stress) {
        _analysisCta(el, id, 'Stress', 'Stress Test', 'btn-run-stress',
            () => api.runStressTest(id, {}));
        return;
    }

    let html = '<div class="space-y-4">';
    for (const [scenario, data] of Object.entries(stress)) {
        html += _section(
            scenario.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
            `<pre class="text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`
        );
    }
    html += '</div>';
    el.innerHTML = html;
}

// ── Tab: Decision ───────────────────────────────────────────────────

async function _tabDecision(el, id) {
    let decision;
    try { decision = await api.getDecision(id); } catch { decision = null; }

    if (!decision) {
        el.innerHTML = `
            <p class="text-gray-400 mb-4">No decision case yet.</p>
            <button id="btn-create-decision" class="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700">Create Decision Case</button>
        `;
        document.getElementById('btn-create-decision')?.addEventListener('click', async () => {
            try {
                await api.createDecision(id);
                showToast('Decision case created', 'success');
                _loadTabContent(id, 'Decision');
            } catch (err) { showToast(err.message, 'error'); }
        });
        return;
    }

    let html = `<div class="space-y-4">`;
    html += _section('Decision Case', `
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            ${_kv('Stage', decision.stage)}
            ${_kv('Status', decision.decision_status)}
            ${_kv('Priority', decision.priority)}
            ${_kv('Pursue Score', decision.pursue_score)}
            ${_kv('Max Offer', formatCurrency(decision.max_offer_current))}
            ${_kv('Walk-Away', formatCurrency(decision.walk_away_price))}
            ${_kv('Confidence', decision.confidence_level)}
        </div>
        ${decision.status_summary ? `<p class="mt-3 text-sm text-gray-600">${escapeHtml(decision.status_summary)}</p>` : ''}
    `);

    try {
        const packet = await api.getDecisionPacket(id);
        if (packet?.quick_take) {
            const rec = packet.quick_take.recommendation;
            const recColor = rec === 'pursue' ? 'bg-green-100 text-green-700'
                : rec === 'pass' ? 'bg-red-100 text-red-700'
                : 'bg-yellow-100 text-yellow-700';
            html += _section('Quick Take', `
                <div class="mb-2">${badge(rec, recColor)}</div>
                ${packet.quick_take.bullets?.length ? `<ul class="list-disc list-inside text-sm text-gray-600 space-y-1">${packet.quick_take.bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join('')}</ul>` : ''}
            `);
        }
    } catch { /* packet not available */ }

    html += '</div>';
    el.innerHTML = html;
}

// ── Tab: Notes ──────────────────────────────────────────────────────

async function _tabNotes(el, id) {
    const notes = await api.listNotes(id);

    let html = `
        <div class="mb-4">
            <form id="note-form" class="flex gap-2">
                <input name="content" placeholder="Add a note..." required class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                <select name="note_type" class="px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="general">General</option>
                    <option value="tour">Tour</option>
                    <option value="concern">Concern</option>
                    <option value="positive">Positive</option>
                </select>
                <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">Add</button>
            </form>
        </div>
    `;

    if (notes.length) {
        html += `<div class="space-y-2">${notes.map((n) => `
            <div class="bg-white rounded-lg border border-gray-200 p-3 flex items-start justify-between">
                <div>
                    <span class="text-xs text-gray-400">${formatDate(n.created_at)} &middot; ${escapeHtml(n.note_type)}</span>
                    <p class="text-sm mt-1">${escapeHtml(n.content)}</p>
                </div>
                <button data-note-id="${escapeHtml(n.id)}" class="btn-delete-note text-gray-300 hover:text-red-500 text-lg ml-3 leading-none">&times;</button>
            </div>
        `).join('')}</div>`;
    } else {
        html += '<p class="text-gray-400 text-sm">No notes yet.</p>';
    }

    el.innerHTML = html;

    document.getElementById('note-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const content = fd.get('content')?.toString().trim();
        if (!content) return;
        try {
            await api.createNote(id, { content, note_type: fd.get('note_type') || 'general' });
            _loadTabContent(id, 'Notes');
        } catch (err) { showToast(err.message, 'error'); }
    });

    el.querySelectorAll('.btn-delete-note').forEach((btn) => {
        btn.addEventListener('click', async () => {
            try {
                await api.deleteNote(id, btn.dataset.noteId);
                _loadTabContent(id, 'Notes');
            } catch (err) { showToast(err.message, 'error'); }
        });
    });
}

// ── Pipeline status (shown after triggering a run) ──────────────────

function _renderPipelineStatus(run) {
    const contentEl = document.getElementById('pd-content');
    if (!contentEl) return;

    let inner = `<div class="text-sm mb-2">Status: ${badge(run.status, STATUS_COLORS[run.status] || 'bg-gray-100 text-gray-700')}</div>`;

    if (run.tasks?.length) {
        inner += renderTable(
            ['Task', 'Status', 'Duration', 'Error'],
            run.tasks.map((t) => [
                t.task_name, t.status,
                formatDuration(t.duration_ms),
                t.error_details || '\u2014',
            ]),
            { compact: true }
        );
    }

    contentEl.innerHTML = _section(`Pipeline: ${run.run_type}`, inner);
}
