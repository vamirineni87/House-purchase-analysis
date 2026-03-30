/**
 * Property detail coordinator — loads core data, renders header + actions +
 * tab bar + active tab content. Manages tab switching and lazy loading.
 */

import { api } from '../../api.js';
import { showToast } from '../../toast.js';
import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderHeader } from './header.js';
import { renderActionBar } from './actions.js';
import { renderTabBar } from './tabs.js';
import * as summaryTab from './summary-tab.js';
import * as pipelineTab from './pipeline-tab.js';
import * as financialTab from './financial-tab.js';
import * as compsTab from './comps-tab.js';
import * as conditionTab from './condition-tab.js';
import * as countyTab from './county-tab.js';
import * as listingTab from './listing-tab.js';
import * as schoolsTab from './schools-tab.js';
import * as aiTab from './ai-tab.js';
import * as notesTab from './notes-tab.js';

const TAB_MODULES = {
    'Summary':         summaryTab,
    'Pipeline':        pipelineTab,
    'Financial':       financialTab,
    'Value/Comps':     compsTab,
    'Condition':       conditionTab,
    'County':          countyTab,
    'Listing History': listingTab,
    'Schools':         schoolsTab,
    'AI Analysis':     aiTab,
    'Notes & DD':      notesTab,
};

let _state = {
    propertyId: null,
    property: null,
    watchEntry: null,
    activeTab: 'Summary',
    loading: true,
    error: null,
    actionLoading: null,

    // Data loaded once
    pipelineRuns: [],
    latestRun: null,
    listingData: {},
    analysisResults: {},
    decision: null,
    packet: null,

    // Lazy loaded per-tab data caches
    countyData: null,
    quickComp: null,
    deepComp: null,
    conditionData: null,
    freshness: [],
    schools: [],
    notes: [],
};

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container, params) {
    const propertyId = params.id;
    _state.propertyId = propertyId;
    _state.loading = true;
    _state.error = null;
    _state.activeTab = 'Summary';

    // Reset caches
    _state.countyData = null;
    _state.quickComp = null;
    _state.deepComp = null;
    _state.conditionData = null;
    _state.freshness = [];
    _state.notes = [];

    renderShell(container);

    try {
        const [prop, watchlist] = await Promise.all([
            api.getProperty(propertyId),
            api.listWatchlist(),
        ]);
        _state.property = prop;
        _state.watchEntry = watchlist.find(w => w.property_id === propertyId) || null;

        // Pipeline runs
        try {
            const runs = await api.getPipelineRuns(propertyId, 10);
            _state.pipelineRuns = runs;
            _state.latestRun = runs.length > 0 ? runs[0] : null;
        } catch { _state.pipelineRuns = []; _state.latestRun = null; }

        // Listing data
        try {
            const ld = await api.getListingData(propertyId);
            _state.listingData = ld.listing_data || ld || {};
        } catch { _state.listingData = {}; }

        // Analysis results
        try {
            const ar = await api.getAnalysisResults(propertyId);
            _state.analysisResults = ar.analyses || {};
        } catch { _state.analysisResults = {}; }

        // Decision
        try {
            _state.decision = await api.getDecision(propertyId);
        } catch { _state.decision = null; }

        // Decision packet
        try {
            _state.packet = await api.getDecisionPacket(propertyId);
        } catch { _state.packet = null; }

    } catch (err) {
        _state.error = err.message || 'Failed to load property';
    } finally {
        _state.loading = false;
    }

    renderShell(container);
    renderActiveTab(container);
    bindShell(container);
}

// ---------------------------------------------------------------
// Render outer shell (header, actions, tabs)
// ---------------------------------------------------------------

function renderShell(container) {
    if (_state.loading) {
        container.innerHTML = '<div class="text-gray-500 text-sm">Loading property...</div>';
        return;
    }

    if (_state.error || !_state.property) {
        container.innerHTML = `<div class="text-red-600 text-sm">${escapeHtml(_state.error || 'Property not found')}</div>`;
        return;
    }

    const headerHtml = renderHeader(_state.property, _state.listingData, _state.watchEntry, _state.latestRun, _state.decision, _state.packet);
    const actionsHtml = renderActionBar(_state.actionLoading);
    const tabBarHtml = renderTabBar(_state.activeTab);

    container.innerHTML = `
    <div>
        ${headerHtml}
        ${actionsHtml}
        ${tabBarHtml}
        <div id="tab-content"></div>
    </div>`;
}

// ---------------------------------------------------------------
// Render active tab content
// ---------------------------------------------------------------

function renderActiveTab(container) {
    const tabContainer = container.querySelector('#tab-content');
    if (!tabContainer) return;

    const mod = TAB_MODULES[_state.activeTab];
    if (!mod) {
        tabContainer.innerHTML = '<div class="text-gray-500 text-sm">Unknown tab.</div>';
        return;
    }

    // Pass the full state to each tab's render
    mod.render(tabContainer, _state);
    if (mod.bind) mod.bind(tabContainer, _state, { reload: () => renderActiveTab(container), reloadShell: () => { renderShell(container); renderActiveTab(container); bindShell(container); } });

    // Lazy load data for certain tabs
    lazyLoadTabData(container);
}

// ---------------------------------------------------------------
// Lazy-load tab-specific data
// ---------------------------------------------------------------

async function lazyLoadTabData(container) {
    const { activeTab, propertyId } = _state;

    if (activeTab === 'County' && !_state.countyData) {
        try {
            _state.countyData = await api.getCountyData(propertyId);
            renderActiveTab(container);
        } catch { /* no data */ }
    }

    if (activeTab === 'Value/Comps' && !_state.quickComp && !_state.deepComp) {
        try {
            const data = await api.getComps(propertyId);
            if (data.quick_comp) _state.quickComp = data.quick_comp;
            if (data.deep_comp) _state.deepComp = data.deep_comp;
            renderActiveTab(container);
        } catch { /* no data */ }
    }

    if (activeTab === 'Pipeline' && _state.freshness.length === 0) {
        try {
            _state.freshness = await api.getFreshness(propertyId);
            renderActiveTab(container);
        } catch { /* no data */ }
    }

    if (activeTab === 'Condition' && !_state.conditionData) {
        try {
            const ar = await api.getAnalysisResults(propertyId);
            const condition = ar.analyses?.condition;
            if (condition?.output) {
                _state.conditionData = condition.output;
                renderActiveTab(container);
            }
        } catch { /* no data */ }
    }

    if (activeTab === 'Notes & DD' && _state.notes.length === 0) {
        try {
            _state.notes = await api.listNotes(propertyId);
            renderActiveTab(container);
        } catch { /* no data */ }
    }
}

// ---------------------------------------------------------------
// Actions
// ---------------------------------------------------------------

async function handleAction(actionKey, actionFn, container) {
    _state.actionLoading = actionKey;
    renderShell(container);
    renderActiveTab(container);
    bindShell(container);

    try {
        await actionFn();
    } catch (err) {
        showToast(err.message || 'Action failed', 'error');
    } finally {
        _state.actionLoading = null;
        renderShell(container);
        renderActiveTab(container);
        bindShell(container);
    }
}

// ---------------------------------------------------------------
// Bind shell-level events
// ---------------------------------------------------------------

function bindShell(container) {
    // Tab switching
    container.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            _state.activeTab = btn.getAttribute('data-tab');
            renderShell(container);
            renderActiveTab(container);
            bindShell(container);
        });
    });

    // Stage dropdown
    const stageSelect = container.querySelector('#stage-select');
    if (stageSelect) {
        stageSelect.addEventListener('change', async () => {
            const stage = stageSelect.value;
            if (!stage) return;
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
        });
    }

    // Action buttons
    const actions = {
        'action-run-pipeline': async () => {
            const run = await api.runPipeline(_state.propertyId, 'full_pipeline');
            _state.latestRun = run;
            _state.pipelineRuns = [run, ..._state.pipelineRuns];
            showToast('Pipeline started', 'success');
        },
        'action-refresh-listing': async () => {
            await api.refreshSource(_state.propertyId, 'zillow');
            showToast('Listing refresh started', 'success');
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

    for (const [id, fn] of Object.entries(actions)) {
        const btn = container.querySelector(`#${id}`);
        if (btn) {
            btn.addEventListener('click', () => handleAction(id, fn, container));
        }
    }
}

/**
 * Expose state getter for sub-modules that need to trigger actions.
 */
export function getState() {
    return _state;
}

export function setState(updates) {
    Object.assign(_state, updates);
}
