/**
 * Property detail coordinator — single scrollable page with collapsible sections.
 *
 * Replaces the old tab-based layout. Loads core data upfront (property, listing,
 * decision, latest pipeline run), renders all sections, then lazy-loads remaining
 * data and re-renders affected sections progressively.
 */

import { api } from '../../api.js';
import { showToast } from '../../toast.js';
import { escapeHtml } from '../../utils.js';
import { renderHeader, bindHeader } from './header.js';
import { renderSectionNav, bindSectionNav } from '../../components/section-nav.js';
import {
    renderCollapsibleSection,
    bindCollapsibleSections,
    setPropertyId,
    getSavedExpanded,
} from '../../components/collapsible-section.js';

// Section modules
import * as summarySection from './sections/summary-actions.js';
import * as pipelineSection from './sections/pipeline-health.js';
import * as priceSection from './sections/price-value.js';
import * as metricsSection from './sections/key-metrics.js';
import * as financialSection from './sections/financial.js';
import * as conditionSection from './sections/condition.js';
import * as schoolsSection from './sections/schools.js';
import * as historySection from './sections/property-history.js';
import * as countySection from './sections/county-details.js';
import * as compsSection from './sections/comps.js';
import * as aiSection from './sections/ai-analysis.js';
import * as notesSection from './sections/notes-actions.js';

/** Ordered list of all content sections. */
const SECTIONS = [
    { mod: summarySection,   collapsible: false },
    { mod: pipelineSection,  collapsible: true },
    { mod: priceSection,     collapsible: true },
    { mod: metricsSection,   collapsible: true },
    { mod: financialSection, collapsible: true },
    { mod: conditionSection, collapsible: true },
    { mod: schoolsSection,   collapsible: true },
    { mod: historySection,   collapsible: true },
    { mod: countySection,    collapsible: true },
    { mod: compsSection,     collapsible: true },
    { mod: aiSection,        collapsible: true },
    { mod: notesSection,     collapsible: true },
];

let _state = {
    propertyId: null,
    property: null,
    watchEntry: null,
    loading: true,
    error: null,
    actionLoading: null,

    // Core data (loaded upfront)
    pipelineRuns: [],
    latestRun: null,
    listingData: {},
    decision: null,

    // Lazy-loaded data
    analysisResults: {},
    packet: null,
    countyData: null,
    quickComp: null,
    deepComp: null,
    conditionData: null,
    freshness: [],
    schools: [],
    notes: [],
};

let _container = null;

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container, params) {
    const propertyId = params.id;
    _container = container;
    _state.propertyId = propertyId;
    _state.loading = true;
    _state.error = null;
    _state.actionLoading = null;

    // Reset lazy caches
    _state.analysisResults = {};
    _state.packet = null;
    _state.countyData = null;
    _state.quickComp = null;
    _state.deepComp = null;
    _state.conditionData = null;
    _state.freshness = [];
    _state.notes = [];

    setPropertyId(propertyId);

    container.innerHTML = '<div class="text-gray-500 text-sm py-8">Loading property...</div>';

    try {
        // Phase 1: Upfront — fast, decision-first
        const [prop, watchlist, listingRes, decision, runs] = await Promise.allSettled([
            api.getProperty(propertyId),
            api.listWatchlist(),
            api.getListingData(propertyId),
            api.getDecision(propertyId),
            api.getPipelineRuns(propertyId, 1),
        ]);

        _state.property = prop.status === 'fulfilled' ? prop.value : null;
        const wl = watchlist.status === 'fulfilled' ? watchlist.value : [];
        _state.watchEntry = wl.find(w => w.property_id === propertyId) || null;

        if (listingRes.status === 'fulfilled') {
            const ld = listingRes.value;
            _state.listingData = ld.listing_data || ld || {};
        }
        _state.decision = decision.status === 'fulfilled' ? decision.value : null;

        if (runs.status === 'fulfilled') {
            const r = runs.value;
            _state.pipelineRuns = Array.isArray(r) ? r : [];
            _state.latestRun = _state.pipelineRuns[0] || null;
        }

        if (!_state.property) {
            _state.error = 'Property not found';
        }
    } catch (err) {
        _state.error = err.message || 'Failed to load property';
    } finally {
        _state.loading = false;
    }

    // Render page
    renderPage(container);
    bindPage(container);

    // Phase 2: Lazy loads (non-blocking)
    lazyLoadAll();
}

// ---------------------------------------------------------------
// Render full page
// ---------------------------------------------------------------

function renderPage(container) {
    if (_state.error || !_state.property) {
        container.innerHTML = `<div class="text-red-600 text-sm py-8">${escapeHtml(_state.error || 'Property not found')}</div>`;
        return;
    }

    const headerHtml = renderHeader(_state);
    const navHtml = renderSectionNav();

    const sectionsHtml = SECTIONS.map(({ mod, collapsible }) => {
        const content = mod.render(_state);
        if (!collapsible) {
            return `<div data-section-id="${mod.ID}" class="bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-4">${content}</div>`;
        }

        // Determine expanded state: saved > auto-expand > default
        const saved = getSavedExpanded(mod.ID);
        let expanded;
        if (saved !== null) {
            expanded = saved;
        } else if (mod.shouldAutoExpand(_state)) {
            expanded = true;
        } else {
            expanded = mod.DEFAULT_EXPANDED;
        }

        const stateBadge = mod.getStateBadge ? mod.getStateBadge(_state) : null;
        const extra = mod.headerExtra ? mod.headerExtra(_state) : '';

        return renderCollapsibleSection(mod.ID, mod.TITLE, content, {
            expanded,
            headerExtra: extra,
            stateBadge,
        });
    }).join('');

    container.innerHTML = `
<div class="px-6">
  ${headerHtml}
</div>
${navHtml}
<div class="px-6 space-y-4 pt-4 pb-8">
  ${sectionsHtml}
</div>`;
}

// ---------------------------------------------------------------
// Bind all events
// ---------------------------------------------------------------

function bindPage(container) {
    const headerEl = container.querySelector('#detail-header');

    // Header actions
    bindHeader(container, _state, {
        onAction: (actionId) => handleAction(actionId, container),
        onStageChange: (stage) => handleStageChange(stage),
    });

    // Section nav
    bindSectionNav(container, headerEl);

    // Collapsible sections
    bindCollapsibleSections(container);

    // Each section's own bindings
    const actions = { rerenderSection, state: _state };
    for (const { mod } of SECTIONS) {
        if (mod.bind) {
            const sectionEl = container.querySelector(`[data-section-id="${mod.ID}"]`);
            if (sectionEl) {
                mod.bind(sectionEl, _state, actions);
            }
        }
    }

    // Scroll to section if ?section= in URL
    const urlParams = new URLSearchParams(window.location.hash.split('?')[1] || '');
    const targetSection = urlParams.get('section');
    if (targetSection) {
        setTimeout(() => {
            const el = container.querySelector(`[data-section-id="${targetSection}"]`);
            if (el) {
                const offset = (headerEl?.offsetHeight || 0) + 50;
                const top = el.getBoundingClientRect().top + window.scrollY - offset;
                window.scrollTo({ top, behavior: 'smooth' });
            }
        }, 100);
    }
}

// ---------------------------------------------------------------
// Re-render a single section
// ---------------------------------------------------------------

function rerenderSection(sectionId) {
    if (!_container) return;
    const section = SECTIONS.find(s => s.mod.ID === sectionId);
    if (!section) return;

    const bodyEl = _container.querySelector(`[data-section-body="${sectionId}"]`);
    if (bodyEl) {
        bodyEl.innerHTML = section.mod.render(_state);
    } else {
        // Non-collapsible section (summary)
        const sectionEl = _container.querySelector(`[data-section-id="${sectionId}"]`);
        if (sectionEl) {
            sectionEl.innerHTML = section.mod.render(_state);
        }
    }

    // Update state badge
    if (section.mod.getStateBadge) {
        const badge = section.mod.getStateBadge(_state);
        const badgeEl = _container.querySelector(`[data-section-id="${sectionId}"] .section-state-badge`);
        if (badgeEl && badge) {
            const variants = {
                'not-run': 'bg-gray-100 text-gray-500',
                'loading': 'bg-blue-100 text-blue-600',
                'partial': 'bg-amber-100 text-amber-700',
                'stale': 'bg-amber-100 text-amber-700',
                'complete': 'bg-green-100 text-green-700',
            };
            badgeEl.className = `section-state-badge text-[10px] px-1.5 py-0.5 rounded font-medium ${variants[badge.variant] || variants['not-run']}`;
            badgeEl.textContent = badge.label;
        }
    }

    // Re-bind section events
    if (section.mod.bind) {
        const sectionEl = _container.querySelector(`[data-section-id="${sectionId}"]`);
        if (sectionEl) {
            section.mod.bind(sectionEl, _state, { rerenderSection, state: _state });
        }
    }
}

// ---------------------------------------------------------------
// Lazy load remaining data
// ---------------------------------------------------------------

async function lazyLoadAll() {
    const pid = _state.propertyId;

    // Fire all lazy loads in parallel
    const loads = [
        api.getDecisionPacket(pid).then(d => {
            _state.packet = d;
            rerenderSection('summary');
            rerenderSection('price-value');
        }).catch(() => {}),

        api.getAnalysisResults(pid).then(d => {
            _state.analysisResults = d.analyses || d || {};
            if (_state.analysisResults.condition?.output) {
                _state.conditionData = _state.analysisResults.condition.output;
            }
            rerenderSection('summary');
            rerenderSection('condition');
            rerenderSection('financial');
            rerenderSection('pipeline-health');
            rerenderSection('ai-analysis');
        }).catch(() => {}),

        api.getCountyData(pid).then(d => {
            _state.countyData = d;
            rerenderSection('summary');
            rerenderSection('key-metrics');
            rerenderSection('price-value');
            rerenderSection('property-history');
            rerenderSection('county-details');
        }).catch(() => {}),

        api.getPipelineRuns(pid, 10).then(d => {
            _state.pipelineRuns = Array.isArray(d) ? d : [];
            _state.latestRun = _state.pipelineRuns[0] || _state.latestRun;
            rerenderSection('pipeline-health');
        }).catch(() => {}),

        api.getComps(pid).then(d => {
            if (d?.quick_comp) _state.quickComp = d.quick_comp;
            if (d?.deep_comp) _state.deepComp = d.deep_comp;
            rerenderSection('summary');
            rerenderSection('price-value');
            rerenderSection('comps');
        }).catch(() => {}),

        api.listNotes(pid).then(d => {
            _state.notes = Array.isArray(d) ? d : [];
            rerenderSection('notes');
        }).catch(() => {}),
    ];

    await Promise.allSettled(loads);
}

// ---------------------------------------------------------------
// Action handlers
// ---------------------------------------------------------------

async function handleAction(actionId, container) {
    const actionMap = {
        'action-run-pipeline': async () => {
            const run = await api.runPipeline(_state.propertyId, 'full_pipeline');
            _state.latestRun = run;
            _state.pipelineRuns = [run, ..._state.pipelineRuns];
            showToast('Pipeline started', 'success');
        },
        'action-refresh-listing': async () => {
            await api.refreshSource(_state.propertyId, 'zillow');
            const ld = await api.getListingData(_state.propertyId);
            _state.listingData = ld.listing_data || ld || {};
            showToast('Listing refreshed', 'success');
        },
        'action-refresh-county': async () => {
            await api.refreshCountyData(_state.propertyId);
            _state.countyData = await api.getCountyData(_state.propertyId);
            showToast('County data refreshed', 'success');
        },
        'action-deep-comp': async () => {
            const result = await api.runCompsDeep(_state.propertyId);
            _state.deepComp = result;
            showToast('Deep comp complete', 'success');
        },
        'action-rerun-ai': async () => {
            const run = await api.runPipeline(_state.propertyId, 'rerun_ai');
            _state.latestRun = run;
            _state.pipelineRuns = [run, ..._state.pipelineRuns];
            showToast('AI rerun started', 'success');
        },
    };

    const fn = actionMap[actionId];
    if (!fn) return;

    _state.actionLoading = actionId;
    renderPage(container);
    bindPage(container);

    try {
        await fn();
    } catch (err) {
        showToast(err.message || 'Action failed', 'error');
    } finally {
        _state.actionLoading = null;
        renderPage(container);
        bindPage(container);
    }
}

async function handleStageChange(stage) {
    try {
        if (_state.watchEntry) {
            _state.watchEntry = await api.updateWatchlistStage(_state.watchEntry.id, stage);
        } else {
            _state.watchEntry = await api.addToWatchlist({ property_id: _state.propertyId, stage });
        }
        showToast(`Moved to ${stage}`, 'success');
    } catch {
        showToast('Failed to update stage', 'error');
    }
}

// ---------------------------------------------------------------
// Public accessors for sub-modules
// ---------------------------------------------------------------

export function getState() { return _state; }
export function setState(updates) { Object.assign(_state, updates); }
