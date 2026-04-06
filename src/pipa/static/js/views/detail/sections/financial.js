/**
 * Section §5: Financial Analysis
 *
 * Monthly payment breakdown, loan scenario comparison, cash at closing,
 * closing costs. Input form when no data exists.
 */

import { formatCurrency, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { showToast } from '../../../toast.js';
import { api } from '../../../api.js';

export const TITLE = 'Financial Analysis';
export const ID = 'financial';
export const DEFAULT_EXPANDED = true;

// ── Auto-expand logic ──────────────────────────────────────────────

export function shouldAutoExpand(state) {
    const fin = state.analysisResults?.financial?.output;
    if (!fin) return false;
    // Expand when stress tests have failures
    if (fin.stress_failures && fin.stress_failures > 0) return true;
    // Expand when total monthly payment is very high (> $5k)
    const breakdowns = fin.payment_breakdowns || {};
    for (const bd of Object.values(breakdowns)) {
        if (bd.total && bd.total > 5000) return true;
    }
    return false;
}

// ── State badge ────────────────────────────────────────────────────

export function getStateBadge(state) {
    const fin = state.analysisResults?.financial?.output;
    if (fin) return { label: 'Complete', variant: 'success' };
    return { label: 'Not run', variant: 'muted' };
}

// ── Header extra (Run Analysis button) ─────────────────────────────

export function headerExtra(state) {
    const loading = state.actionLoading?.financial;
    return `
        <button data-action="run-financial"
                ${loading ? 'disabled' : ''}
                class="pipa-btn pipa-btn-outline"
        >${loading ? 'Running\u2026' : 'Run Analysis'}</button>`;
}

// ── Helpers ────────────────────────────────────────────────────────

function fmtPct(n) {
    if (n == null) return '\u2014';
    return `${(n * 100).toFixed(1)}%`;
}

function renderInputForm(state) {
    const prop = state.property || {};
    const ld = state.listingData || {};
    const defaultPrice = ld.price || prop.list_price || ld.list_price || '';
    const defaultHOA = ld.hoa_monthly || ld.hoa || prop.hoa_monthly || '';

    return `
    <div class="bg-ink-50 border border-ink-200 rounded p-3">
        <div class="flex flex-wrap gap-3 items-end">
            <div>
                <label class="data-label block mb-0.5">List Price</label>
                <input data-fin="list-price" type="number" value="${escapeHtml(String(defaultPrice))}"
                       placeholder="650000"
                       class="border border-ink-200 rounded px-2.5 py-1.5 text-sm font-mono w-36 bg-white focus:ring-1 focus:ring-gold-400 focus:border-gold-400" />
            </div>
            <div>
                <label class="data-label block mb-0.5">HOA/mo</label>
                <input data-fin="hoa" type="number" value="${escapeHtml(String(defaultHOA))}"
                       placeholder="0"
                       class="border border-ink-200 rounded px-2.5 py-1.5 text-sm font-mono w-24 bg-white focus:ring-1 focus:ring-gold-400 focus:border-gold-400" />
            </div>
            <div>
                <label class="data-label block mb-0.5">Rate %</label>
                <input data-fin="rate" type="number" step="0.01" value=""
                       placeholder="6.75"
                       class="border border-ink-200 rounded px-2.5 py-1.5 text-sm font-mono w-20 bg-white focus:ring-1 focus:ring-gold-400 focus:border-gold-400" />
            </div>
            <button data-action="run-financial-inline" class="pipa-btn pipa-btn-primary">
                Run Analysis
            </button>
        </div>
    </div>`;
}

function renderPaymentSummary(fin) {
    // Use the first scenario's breakdown as the primary display
    const breakdowns = fin.payment_breakdowns || {};
    const scenarios = fin.scenarios || [];
    const primary = scenarios[0];
    const bd = primary ? breakdowns[primary.name] : null;

    if (!bd) return '';

    const items = [
        ['P&I',       bd.principal != null && bd.interest != null ? (bd.principal + bd.interest) : bd.pi,     'text-blue-700'],
        ['Taxes',     bd.property_tax,     'text-amber-700'],
        ['Insurance', bd.homeowners_insurance, 'text-green-700'],
        ['HOA',       bd.hoa,              'text-purple-700'],
        ['PMI',       bd.pmi,              'text-red-700'],
    ].filter(([, v]) => v != null && v > 0);

    const rows = items.map(([label, value, color]) => `
        <div class="flex justify-between text-xs">
            <span class="text-gray-500">${label}</span>
            <span class="font-medium ${color}">${formatCurrency(value)}</span>
        </div>`).join('');

    return `
    <div class="bg-white border border-gray-200 rounded p-3">
        <div class="flex items-center justify-between mb-2">
            <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide">Monthly Payment</h4>
            <span class="text-lg font-bold text-gray-900">${formatCurrency(bd.total)}</span>
        </div>
        <div class="space-y-1">${rows}</div>
        <div class="border-t border-gray-100 mt-2 pt-2 flex justify-between text-xs font-semibold">
            <span class="text-gray-700">Total</span>
            <span class="text-gray-900">${formatCurrency(bd.total)}</span>
        </div>
    </div>`;
}

function renderScenarioTable(fin) {
    const scenarios = fin.scenarios || [];
    const breakdowns = fin.payment_breakdowns || {};
    if (scenarios.length === 0) return '';

    const rows = scenarios.map(s => {
        const bd = breakdowns[s.name];
        return `
        <tr class="hover:bg-gray-50">
            <td class="px-2 py-1.5 text-xs font-medium text-gray-900">${escapeHtml(s.name)}</td>
            <td class="px-2 py-1.5 text-xs text-right text-gray-700">${formatCurrency(s.down_payment)}</td>
            <td class="px-2 py-1.5 text-xs text-right text-gray-500">${fmtPct(s.down_payment_pct)}</td>
            <td class="px-2 py-1.5 text-xs text-right text-gray-700">${formatCurrency(s.loan_amount)}</td>
            <td class="px-2 py-1.5 text-xs text-right text-gray-700">${s.interest_rate != null ? s.interest_rate.toFixed(2) + '%' : '\u2014'}</td>
            <td class="px-2 py-1.5 text-xs text-right text-gray-700">${s.term_years ?? '\u2014'}yr</td>
            <td class="px-2 py-1.5 text-xs text-right font-semibold text-gray-900">${bd ? formatCurrency(bd.total) : '\u2014'}</td>
        </tr>`;
    }).join('');

    return `
    <div>
        <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">Loan Scenarios</h4>
        <div class="overflow-x-auto border border-gray-200 rounded">
            <table class="min-w-full text-xs">
                <thead>
                    <tr class="bg-gray-50 text-gray-500 text-left">
                        <th class="px-2 py-1.5 font-medium">Scenario</th>
                        <th class="px-2 py-1.5 font-medium text-right">Down</th>
                        <th class="px-2 py-1.5 font-medium text-right">%</th>
                        <th class="px-2 py-1.5 font-medium text-right">Loan</th>
                        <th class="px-2 py-1.5 font-medium text-right">Rate</th>
                        <th class="px-2 py-1.5 font-medium text-right">Term</th>
                        <th class="px-2 py-1.5 font-medium text-right">Monthly</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${rows}</tbody>
            </table>
        </div>
    </div>`;
}

function renderCashAtClosing(fin) {
    const cash = fin.cash_needed_at_closing;
    if (!cash || Object.keys(cash).length === 0) return '';

    const cards = Object.entries(cash).map(([name, amount]) => `
        <div class="bg-white border border-gray-200 rounded p-2.5 text-center">
            <div class="text-xs text-gray-500 truncate">${escapeHtml(name)}</div>
            <div class="text-sm font-bold text-gray-900 mt-0.5">${formatCurrency(amount)}</div>
        </div>`).join('');

    return `
    <div>
        <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">Cash at Closing</h4>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">${cards}</div>
    </div>`;
}

function renderClosingCosts(fin) {
    const cc = fin.closing_costs;
    if (!cc) return '';

    const items = [
        ['Loan origination',  cc.loan_origination],
        ['Appraisal',         cc.appraisal_fee],
        ['Title insurance',   cc.title_insurance],
        ['Escrow',            cc.escrow_fees],
        ['Recording',         cc.recording_fees],
        ['Prepaid taxes',     cc.prepaid_taxes],
        ['Prepaid insurance', cc.prepaid_insurance],
        ['Inspection',        cc.inspection_fees],
        ['Other',             cc.other],
    ].filter(([, v]) => v != null && v > 0);

    if (items.length === 0) return '';

    const rows = items.map(([label, val]) => `
        <div class="flex justify-between text-xs">
            <span class="text-gray-500">${label}</span>
            <span class="text-gray-700">${formatCurrency(val)}</span>
        </div>`).join('');

    return `
    <div>
        <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">Closing Costs</h4>
        <div class="bg-white border border-gray-200 rounded p-3">
            <div class="space-y-1">${rows}</div>
            <div class="border-t border-gray-100 mt-2 pt-2 flex justify-between text-xs font-semibold">
                <span class="text-gray-700">Total</span>
                <span class="text-gray-900">${formatCurrency(cc.total)}</span>
            </div>
        </div>
    </div>`;
}

// ── Render ──────────────────────────────────────────────────────────

export function render(state) {
    const fin = state.analysisResults?.financial?.output;

    if (!fin || Object.keys(fin).length === 0) {
        return `
        <div class="space-y-3">
            ${renderInputForm(state)}
            <div class="text-xs text-gray-400 text-center py-4">
                Enter list price and run analysis to see mortgage scenarios and closing costs.
            </div>
        </div>`;
    }

    return `
    <div class="space-y-4">
        ${renderInputForm(state)}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            ${renderPaymentSummary(fin)}
            <div class="space-y-3">
                ${renderCashAtClosing(fin)}
            </div>
        </div>
        ${renderScenarioTable(fin)}
        ${renderClosingCosts(fin)}
    </div>`;
}

// ── Bind ────────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    // Wire inline Run Analysis button
    const inlineBtn = container.querySelector('[data-action="run-financial-inline"]');
    if (inlineBtn) {
        inlineBtn.addEventListener('click', () => runAnalysis(container, state, actions));
    }

    // Wire header Run Analysis button
    const headerBtn = container.querySelector('[data-action="run-financial"]');
    if (headerBtn) {
        headerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            runAnalysis(container, state, actions);
        });
    }
}

async function runAnalysis(container, state, actions) {
    const priceEl = container.querySelector('[data-fin="list-price"]');
    const hoaEl = container.querySelector('[data-fin="hoa"]');
    const rateEl = container.querySelector('[data-fin="rate"]');

    const price = parseFloat(priceEl?.value);
    if (isNaN(price) || price <= 0) {
        showToast('Enter a valid list price.', 'error');
        return;
    }

    const payload = {
        list_price: price,
        hoa_monthly: parseFloat(hoaEl?.value) || 0,
        down_payment_pcts: [0.1, 0.2],
        term_years: [15, 30],
    };
    const rate = parseFloat(rateEl?.value);
    if (!isNaN(rate) && rate > 0) {
        payload.interest_rate = rate / 100;
    }

    try {
        showToast('Running financial analysis\u2026', 'info');
        const result = await api.runFinancialAnalysis(state.property.id, payload);

        // Update state so rerender sees the data
        if (result) {
            if (!state.analysisResults) state.analysisResults = {};
            state.analysisResults.financial = { output: result };
        }

        // Also re-fetch from API to ensure we have the persisted version
        try {
            const fresh = await api.getAnalysisResults(state.property.id);
            if (fresh?.analyses) {
                Object.assign(state.analysisResults, fresh.analyses);
            }
        } catch (_) { /* ignore refresh failure */ }

        showToast('Financial analysis complete', 'success');
        if (actions?.rerenderSection) {
            actions.rerenderSection('financial');
        }
    } catch (err) {
        showToast(err.message || 'Financial analysis failed', 'error');
    }
}
