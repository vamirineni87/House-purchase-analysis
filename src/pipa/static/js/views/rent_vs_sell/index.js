/**
 * Rent vs Sell — analysis page coordinator.
 *
 * Owns state and orchestrates the 6 split view modules:
 *   inputs.js      — 4 collapsible assumption cards
 *   results.js     — top-line metrics + strategy table + driver bridge
 *   charts.js      — Chart.js line + waterfall wrappers
 *   sensitivity.js — user-triggered heatmap with preset toggles
 *   runs.js        — saved runs drawer
 *   compare.js     — dedicated compare page
 *
 * Routes supported:
 *   #rent-vs-sell
 *   #rent-vs-sell?new_home_property_id=<id>
 *   #rent-vs-sell?run_id=<id>
 *   #rent-vs-sell/compare?ids=a,b,c
 *
 * Compute is server-side via /api/v1/rent-vs-sell/calculate. Input edits
 * trigger a 300ms-debounced recompute; sensitivity is user-triggered only.
 */

import { api } from '../../api.js';
import { showToast } from '../../toast.js';
import { escapeHtml } from '../../utils.js';

import { renderInputs, bindInputs } from './inputs.js';
import { renderResultsPanel, bindResultsPanel } from './results.js';
import { drawAllCharts } from './charts.js';
import { bindSensitivity } from './sensitivity.js';
import { renderSavedRunsDrawer, bindSavedRuns } from './runs.js';
import { loadComparePage } from './compare.js';

// ─── Module state ─────────────────────────────────────────────────

const DEFAULT_INPUTS = () => ({
    current_home: {
        value_today: 790000,
        basis: 478000,
        loan_balance: 295413,
        mortgage_rate: 0.025,
        monthly_principal_interest: 1245,
        monthly_taxes: 620,
        monthly_insurance: 120,
        monthly_hoa: 0,
        monthly_misc_owner_paid: 80,
        sell_cost_pct_now: 0.07,
        current_home_sell_cost_pct_future: 0.07,
        monthly_rent_base: 3500,
        land_pct: 0.2974,
        building_pct: 0.7026,
        move_out_month: '2026-05',
        rent_start_month: '2026-06',
        vacancy_months_per_year_base: 0.5,
        bad_debt_pct_of_gross_rent: 0.005,
        leasing_fee_pct_of_annual_rent: 0.05,
        turnover_cost_per_event: 2500,
        turnover_frequency_months: 24,
        routine_maintenance_pct_of_rent: 0.05,
        maintenance_inflation_annual_pct: 0.03,
        self_manage: true,
        property_management_pct: 0.0,
        insurance_conversion_bump_pct: 0.15,
        initial_lease_up_vacancy_months: 1.0,
        sale_prep_cost_flat: 3000,
        total_value_change_5y: 0.10,
        total_value_change_10y: 0.20,
        total_rent_change_5y: 0.0,
        total_rent_change_10y: 0.0,
    },
    new_home: {
        purchase_price: 1315000,
        base_down_pct: 0.20,
        initial_rate: 0.0646,
        loan_term_years: 30,
        monthly_hoa: 0,
        monthly_taxes: 800,
        monthly_insurance: 150,
    },
    refinance: {
        enabled: false, selected_path: 'none', cost_pct: 0.015,
        year3_rate: 0.055, year5_rate: 0.0475, year7_rate: 0.0425,
    },
    taxes: {
        federal_ordinary_rate: 0.24,
        federal_ltcg_rate: 0.15,
        virginia_rate: 0.0575,
        niit_enabled: false,
        niit_rate: 0.038,
        section_121_mfj: 500000,
        depreciation_recovery_rate: 0.25,
        release_suspended_losses_on_taxable_disposition: true,
    },
    ownership_cost_growth: {
        current_home_tax_growth_annual_pct: 0.03,
        current_home_insurance_growth_annual_pct: 0.05,
        current_home_hoa_growth_annual_pct: 0.03,
        current_home_misc_growth_annual_pct: 0.03,
        new_home_tax_growth_annual_pct: 0.03,
        new_home_insurance_growth_annual_pct: 0.05,
        new_home_hoa_growth_annual_pct: 0.03,
    },
    reinvestment: {
        invest_monthly_sell_savings: true,
        monthly_savings_reinvestment_return_annual_pct: 0.04,
        invest_initial_sale_surplus_cash: false,
    },
    new_home_drag: {
        new_home_maintenance_pct_of_home_value_annual: 0.01,
    },
    modeling: {
        rent_then_sell_date: '2029-05',
    },
});

let _state = {
    inputs: null,
    outputs: null,
    savedRuns: [],
    activeRunId: null,
    activeRunName: 'Untitled',
    scenarioLabel: 'base',
    targetPropertyId: null,
    activeLens: '5y',                 // 5y | 10y | rts
    bridgeComparison: 'keep_5y',      // keep_5y | keep_10y | rent_then_sell
    expanded: { current_home: true, new_home: true, market: false, advanced: false },
    heatmapState: {
        preset: 'value_x_rent',
        comparator: 'sell_vs_keep_5y',
        horizon: '5y',
        grid: null,
        stale: false,
        loading: false,
    },
    computeTimer: null,
    computeSeq: 0,
    loading: false,
    container: null,
};

// ─── Entry ─────────────────────────────────────────────────────────

export async function load(container, query = {}) {
    // Compare page is a sub-route
    if (window.location.hash.startsWith('#rent-vs-sell/compare')) {
        return loadComparePage(container);
    }
    _state.inputs = DEFAULT_INPUTS();
    _state.outputs = null;
    _state.loading = true;
    _state.container = container;
    renderShell(container);

    const targetId = query.new_home_property_id || null;
    const runId = query.run_id || null;
    try {
        const [runs, profile] = await Promise.all([
            api.listRentVsSellRuns().catch(() => []),
            api.listCurrentHomeProfiles().then(list => list?.[0] || null).catch(() => null),
        ]);
        _state.savedRuns = runs || [];
        if (profile && profile.config_json) {
            Object.assign(_state.inputs.current_home, profile.config_json);
        }
        if (targetId) {
            try {
                const prefill = await api.rentVsSellPrefill(targetId);
                if (prefill?.new_home) {
                    Object.assign(_state.inputs.new_home, prefill.new_home);
                }
                _state.targetPropertyId = targetId;
            } catch (e) {
                console.warn('Prefill failed:', e);
            }
        }
        if (runId) {
            try {
                const run = await api.getRentVsSellRun(runId);
                if (run) {
                    _state.activeRunId = run.id;
                    _state.activeRunName = run.name;
                    _state.scenarioLabel = run.scenario_label || 'base';
                    _state.inputs = run.assumptions_json;
                    _state.outputs = run.outputs_json;
                    _state.targetPropertyId = run.target_property_id;
                    if (run.recomputed) {
                        showToast('Refreshed saved run from new engine version', 'info');
                    }
                }
            } catch (e) {
                console.warn('Load run failed:', e);
            }
        }
    } finally {
        _state.loading = false;
    }

    // Second full shell render now that we have inputs + saved runs
    renderShell(container);
    bindShell(container);
    if (!_state.outputs) {
        await compute();
    } else {
        renderResultsPanelIntoShell();
        drawAllCharts(container, _state);
    }
}

function scheduleRecompute() {
    if (_state.computeTimer) clearTimeout(_state.computeTimer);
    _state.computeTimer = setTimeout(() => compute(), 300);
}

async function compute() {
    const seq = ++_state.computeSeq;
    _state.loading = true;
    updateLoadingIndicator();
    try {
        const outputs = await api.computeRentVsSell(_state.inputs);
        if (seq !== _state.computeSeq) return;
        _state.outputs = outputs;
        if (_state.heatmapState.grid !== null) {
            _state.heatmapState.stale = true;
        }
    } catch (e) {
        if (seq !== _state.computeSeq) return;
        showToast(`Calculation failed: ${e.message}`, 'error');
    } finally {
        if (seq === _state.computeSeq) {
            _state.loading = false;
            updateLoadingIndicator();
            renderResultsPanelIntoShell();
            drawAllCharts(_state.container, _state);
        }
    }
}

function updateLoadingIndicator() {
    if (!_state.container) return;
    const el = _state.container.querySelector('#rvs-loading-indicator');
    if (el) el.textContent = _state.loading ? 'Computing…' : '';
}

// ─── Render ────────────────────────────────────────────────────────

function renderShell(container) {
    const activeLens = _state.activeLens;
    container.innerHTML = `
    <div class="p-4 lg:p-6 max-w-7xl mx-auto">
        <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
                <h1 class="text-xl font-bold text-gray-900">Rent vs Sell Analysis</h1>
                <div class="text-xs text-gray-500 mt-0.5">Planning math, not tax advice</div>
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <input id="rvs-run-name" type="text" value="${escapeHtml(_state.activeRunName)}"
                       class="px-3 py-1.5 text-sm border border-gray-300 rounded-md" placeholder="Run name" />
                <select id="rvs-scenario-label" class="px-2 py-1.5 text-sm border border-gray-300 rounded-md">
                    ${['base','recession','bull','custom'].map(s =>
                        `<option value="${s}" ${_state.scenarioLabel === s ? 'selected' : ''}>${escapeHtml(s)}</option>`
                    ).join('')}
                </select>
                <button id="rvs-save-run" class="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700">Save</button>
                ${_state.activeRunId ? '<button id="rvs-duplicate-run" class="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200">Duplicate</button>' : ''}
            </div>
        </div>

        <div id="rvs-loading-indicator" class="text-xs text-blue-600 mb-2 min-h-[1rem]"></div>

        ${_state.targetPropertyId ? `
        <div class="text-xs inline-block px-2 py-1 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 mb-3">
            Target property: <code>${escapeHtml(_state.targetPropertyId)}</code>
            <button id="rvs-clear-target" class="ml-2 text-indigo-500 hover:text-indigo-800">×</button>
        </div>` : ''}

        <div class="flex border-b border-gray-200 mb-3">
            ${[['5y','5-Year'],['10y','10-Year'],['rts','Rent-Then-Sell']].map(([lens, label]) => {
                const active = activeLens === lens;
                return `<button data-rvs-lens="${lens}" class="px-4 py-2 text-sm font-medium border-b-2 ${active ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'}">${escapeHtml(label)}</button>`;
            }).join('')}
        </div>

        <div id="rvs-results"></div>
        <div id="rvs-inputs">${renderInputs(_state)}</div>
        <div id="rvs-saved-runs">${renderSavedRunsDrawer(_state)}</div>
    </div>`;
    updateLoadingIndicator();
}

function renderResultsPanelIntoShell() {
    if (!_state.container) return;
    const panel = _state.container.querySelector('#rvs-results');
    if (!panel) return;
    panel.innerHTML = renderResultsPanel(_state);
    bindResultsPanelAll();
}

function renderInputsPanelIntoShell() {
    if (!_state.container) return;
    const el = _state.container.querySelector('#rvs-inputs');
    if (!el) return;
    el.innerHTML = renderInputs(_state);
    bindInputsInto(el);
}

function renderSavedRunsPanelIntoShell() {
    if (!_state.container) return;
    const el = _state.container.querySelector('#rvs-saved-runs');
    if (!el) return;
    el.innerHTML = renderSavedRunsDrawer(_state);
    bindSavedRunsInto(el);
}

// ─── Bind ──────────────────────────────────────────────────────────

function bindShell(container) {
    container.querySelectorAll('[data-rvs-lens]').forEach(btn => {
        btn.addEventListener('click', () => {
            _state.activeLens = btn.dataset.rvsLens;
            // Update tab highlight in place
            container.querySelectorAll('[data-rvs-lens]').forEach(b => {
                const active = b.dataset.rvsLens === _state.activeLens;
                b.className = `px-4 py-2 text-sm font-medium border-b-2 ${active ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`;
            });
            renderResultsPanelIntoShell();
            drawAllCharts(container, _state);
        });
    });

    const nameInput = container.querySelector('#rvs-run-name');
    if (nameInput) nameInput.addEventListener('change', (e) => { _state.activeRunName = e.target.value; });
    const scenSel = container.querySelector('#rvs-scenario-label');
    if (scenSel) scenSel.addEventListener('change', (e) => { _state.scenarioLabel = e.target.value; });

    const saveBtn = container.querySelector('#rvs-save-run');
    if (saveBtn) saveBtn.addEventListener('click', async () => {
        try {
            saveBtn.disabled = true;
            const payload = {
                name: _state.activeRunName || 'Untitled',
                scenario_label: _state.scenarioLabel,
                target_property_id: _state.targetPropertyId,
                comparison_horizon_years: _state.activeLens === '10y' ? 10 : 5,
                assumptions_json: _state.inputs,
                created_from_property_detail: !!_state.targetPropertyId,
                source_prefill_version: _state.targetPropertyId ? '1.0.0' : null,
            };
            let run;
            if (_state.activeRunId) {
                run = await api.updateRentVsSellRun(_state.activeRunId, payload);
            } else {
                run = await api.createRentVsSellRun(payload);
                _state.activeRunId = run.id;
            }
            _state.savedRuns = await api.listRentVsSellRuns();
            showToast('Saved', 'success');
            renderSavedRunsPanelIntoShell();
        } catch (e) {
            showToast(`Save failed: ${e.message}`, 'error');
        } finally {
            saveBtn.disabled = false;
        }
    });

    const dupBtn = container.querySelector('#rvs-duplicate-run');
    if (dupBtn) dupBtn.addEventListener('click', async () => {
        if (!_state.activeRunId) return;
        try {
            await api.duplicateRentVsSellRun(_state.activeRunId);
            _state.savedRuns = await api.listRentVsSellRuns();
            showToast('Duplicated', 'success');
            renderSavedRunsPanelIntoShell();
        } catch (e) {
            showToast(`Duplicate failed: ${e.message}`, 'error');
        }
    });

    const clearTarget = container.querySelector('#rvs-clear-target');
    if (clearTarget) clearTarget.addEventListener('click', () => {
        _state.targetPropertyId = null;
        renderShell(container);
        bindShell(container);
        renderResultsPanelIntoShell();
        drawAllCharts(container, _state);
    });

    // Sub-panels
    bindInputsInto(container.querySelector('#rvs-inputs'));
    bindSavedRunsInto(container.querySelector('#rvs-saved-runs'));
}

function bindInputsInto(panelEl) {
    if (!panelEl) return;
    bindInputs(panelEl, _state, {
        onToggleCard(key) {
            _state.expanded[key] = !_state.expanded[key];
            renderInputsPanelIntoShell();
        },
        onFieldChange(group, key, val) {
            if (!_state.inputs[group]) _state.inputs[group] = {};
            _state.inputs[group][key] = val;
            scheduleRecompute();
        },
    });
}

function bindSavedRunsInto(panelEl) {
    if (!panelEl) return;
    bindSavedRuns(panelEl, _state, {
        async onDuplicate(id) {
            try {
                await api.duplicateRentVsSellRun(id);
                _state.savedRuns = await api.listRentVsSellRuns();
                renderSavedRunsPanelIntoShell();
            } catch (e) {
                showToast(`Duplicate failed: ${e.message}`, 'error');
            }
        },
        async onDelete(id) {
            if (!confirm('Delete this saved run?')) return;
            try {
                await api.deleteRentVsSellRun(id);
                _state.savedRuns = await api.listRentVsSellRuns();
                renderSavedRunsPanelIntoShell();
            } catch (e) {
                showToast(`Delete failed: ${e.message}`, 'error');
            }
        },
        onCompareSelected(ids) {
            if (ids.length < 2) {
                showToast('Select 2-4 runs to compare', 'info');
                return;
            }
            if (ids.length > 4) {
                showToast('Max 4 runs', 'info');
                return;
            }
            window.location.hash = `#rent-vs-sell/compare?ids=${ids.join(',')}`;
        },
    });
}

function bindResultsPanelAll() {
    const container = _state.container;
    if (!container) return;
    const panel = container.querySelector('#rvs-results');
    if (!panel) return;
    // Driver bridge dropdown
    bindResultsPanel(panel, _state, {
        onBridgeCompareChange(value) {
            _state.bridgeComparison = value;
            drawAllCharts(container, _state);
        },
    });
    // Sensitivity toolbar
    bindSensitivity(panel, _state, {
        onPresetChange(v) { _state.heatmapState.preset = v; },
        onComparatorChange(v) { _state.heatmapState.comparator = v; },
        onHorizonChange(v) { _state.heatmapState.horizon = v; },
        async onRefresh() {
            _state.heatmapState.loading = true;
            _state.heatmapState.stale = false;
            renderResultsPanelIntoShell();
            drawAllCharts(container, _state);
            try {
                const grid = await api.computeRentVsSellSensitivity(
                    _state.inputs,
                    _state.heatmapState.preset,
                    _state.heatmapState.comparator,
                    _state.heatmapState.horizon,
                );
                _state.heatmapState.grid = grid;
            } catch (e) {
                showToast(`Heatmap failed: ${e.message}`, 'error');
            } finally {
                _state.heatmapState.loading = false;
                renderResultsPanelIntoShell();
                drawAllCharts(container, _state);
            }
        },
    });
}
