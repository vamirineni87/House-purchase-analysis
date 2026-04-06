/**
 * Section §6: Condition
 *
 * Condition score progress bar, component cards (Roof, HVAC, etc.),
 * capex forecast bars. Color-coded remaining life.
 */

import { formatCurrency, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { showToast } from '../../../toast.js';
import { api } from '../../../api.js';

export const TITLE = 'Condition';
export const ID = 'condition';
export const DEFAULT_EXPANDED = true;

// ── Auto-expand logic ──────────────────────────────────────────────

export function shouldAutoExpand(state) {
    const data = _getData(state);
    if (!data) return false;
    // Expand when score is poor
    const score = data.score ?? data.condition_score ?? null;
    if (score != null && score < 60) return true;
    // Expand when any component has remaining life <= 2 years
    const components = data.components || [];
    for (const c of components) {
        if (c.remaining_life != null && c.remaining_life <= 2) return true;
    }
    return false;
}

// ── State badge ────────────────────────────────────────────────────

export function getStateBadge(state) {
    const data = _getData(state);
    if (data) return { label: 'Complete', variant: 'success' };
    return { label: 'Not run', variant: 'muted' };
}

// ── Header extra ───────────────────────────────────────────────────

export function headerExtra(state) {
    const loading = state.actionLoading?.condition;
    return `
        <button data-action="run-condition"
                ${loading ? 'disabled' : ''}
                class="pipa-btn pipa-btn-outline"
        >${loading ? 'Running\u2026' : 'Run Condition'}</button>`;
}

// ── Helpers ────────────────────────────────────────────────────────

function _getData(state) {
    return state.conditionData || state.analysisResults?.condition?.output || null;
}

function scoreColor(score) {
    if (score >= 70) return { text: 'text-green-600', bar: 'bg-green-500', bg: 'bg-green-50' };
    if (score >= 50) return { text: 'text-amber-600', bar: 'bg-amber-500', bg: 'bg-amber-50' };
    return { text: 'text-red-600', bar: 'bg-red-500', bg: 'bg-red-50' };
}

function remainingLifeColor(years) {
    if (years == null) return 'text-gray-400';
    if (years > 5) return 'text-green-600';
    if (years >= 2) return 'text-amber-600';
    return 'text-red-600';
}

function remainingLifeBorder(years) {
    if (years == null) return 'border-gray-200';
    if (years > 5) return 'border-gray-200';
    if (years >= 2) return 'border-amber-300';
    return 'border-red-300';
}

function renderScoreBar(data) {
    const score = data.score ?? data.condition_score ?? 0;
    const sc = scoreColor(score);

    return `
    <div class="flex items-center gap-3">
        <div class="text-2xl font-bold ${sc.text}">${Number(score).toFixed(0)}</div>
        <div class="flex-1">
            <div class="flex items-center justify-between mb-0.5">
                <span class="text-xs text-gray-500">Condition Score</span>
                <span class="text-xs text-gray-400">/100</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-2.5">
                <div class="h-2.5 rounded-full ${sc.bar} transition-all" style="width:${Math.min(score, 100)}%"></div>
            </div>
        </div>
    </div>`;
}

function renderComponentCard(comp) {
    const type = comp.component_type || comp.type || 'unknown';
    const displayName = type.replace(/_/g, ' ');
    const year = comp.estimated_install_year || comp.install_year;
    const currentYear = new Date().getFullYear();
    const age = year ? currentYear - year : null;
    const remaining = comp.remaining_life;
    const replacementCost = comp.replacement_cost;

    const rlColor = remainingLifeColor(remaining);
    const borderColor = remainingLifeBorder(remaining);

    const rows = [];

    if (year) {
        rows.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Installed</span>
                <span class="font-medium text-gray-700">${year}</span>
            </div>`);
    }
    if (age != null) {
        rows.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Age</span>
                <span class="font-medium text-gray-700">${age} yr</span>
            </div>`);
    }
    if (remaining != null) {
        rows.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Remaining</span>
                <span class="font-medium ${rlColor}">${remaining} yr</span>
            </div>`);
    }
    if (replacementCost != null) {
        rows.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Replace cost</span>
                <span class="font-medium text-gray-700">${formatCurrency(replacementCost)}</span>
            </div>`);
    }

    // Status indicator
    let statusDot = 'bg-green-500';
    let statusLabel = 'Good';
    if (remaining != null) {
        if (remaining <= 2) { statusDot = 'bg-red-500'; statusLabel = 'Replace soon'; }
        else if (remaining <= 5) { statusDot = 'bg-amber-500'; statusLabel = 'Monitor'; }
    } else if (age != null) {
        if (age > 20) { statusDot = 'bg-red-500'; statusLabel = 'Replace soon'; }
        else if (age > 12) { statusDot = 'bg-amber-500'; statusLabel = 'Monitor'; }
    }

    return `
    <div class="p-2.5 bg-white border ${borderColor} rounded">
        <div class="flex items-center justify-between mb-1.5">
            <span class="text-sm font-medium text-gray-900 capitalize">${escapeHtml(displayName)}</span>
            <span class="flex items-center gap-1 text-xs text-gray-500">
                <span class="w-1.5 h-1.5 rounded-full ${statusDot}"></span>
                ${statusLabel}
            </span>
        </div>
        <div class="space-y-1 text-xs">${rows.join('')}</div>
    </div>`;
}

function renderCapexForecast(data) {
    const capex = data.capex_forecast || {};
    const entries = Object.entries(capex)
        .map(([year, cost]) => ({ year: parseInt(year), cost }))
        .sort((a, b) => a.year - b.year);

    if (entries.length === 0) return '';

    const maxCost = Math.max(...entries.map(e => e.cost));
    const total = entries.reduce((sum, e) => sum + e.cost, 0);

    const bars = entries.map(({ year, cost }) => {
        const barColor = cost > 5000 ? 'bg-red-400' : cost > 2000 ? 'bg-amber-400' : 'bg-green-400';
        const width = maxCost > 0 ? (cost / maxCost) * 100 : 0;
        return `
        <div class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-9 text-right font-mono">${year}</span>
            <div class="flex-1 h-4 bg-gray-100 rounded relative">
                <div class="h-full rounded ${barColor}" style="width:${width}%;min-width:${cost > 0 ? '2px' : '0'}"></div>
            </div>
            <span class="text-xs font-medium text-gray-700 w-16 text-right">${formatCurrency(cost)}</span>
        </div>`;
    }).join('');

    return `
    <div>
        <div class="flex items-center justify-between mb-1.5">
            <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide">Capex Forecast</h4>
            <span class="text-xs font-medium text-gray-500">Total: ${formatCurrency(total)}</span>
        </div>
        <div class="bg-white border border-gray-200 rounded p-3 space-y-1.5">
            ${bars}
        </div>
    </div>`;
}

// ── Render ──────────────────────────────────────────────────────────

export function render(state) {
    const data = _getData(state);

    if (!data) {
        return `
        <div class="text-xs text-gray-400 text-center py-6 bg-gray-50 rounded-lg">
            Run pipeline to generate condition analysis.
        </div>`;
    }

    const components = data.components || [];

    const componentsHtml = components.length > 0
        ? `<div>
               <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">Components</h4>
               <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                   ${components.map(c => renderComponentCard(c)).join('')}
               </div>
           </div>`
        : '';

    return `
    <div class="space-y-4">
        ${renderScoreBar(data)}
        ${componentsHtml}
        ${renderCapexForecast(data)}
    </div>`;
}

// ── Bind ────────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    // Wire header Run Condition button
    const headerBtn = container.querySelector('[data-action="run-condition"]');
    if (headerBtn) {
        headerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            runCondition(state, actions);
        });
    }
}

async function runCondition(state, actions) {
    try {
        showToast('Running condition analysis\u2026', 'info');
        await api.runConditionAnalysis(state.property.id);
        showToast('Condition analysis complete', 'success');
        if (actions?.rerenderSection) {
            actions.rerenderSection('condition');
        }
    } catch (err) {
        showToast(err.message || 'Condition analysis failed', 'error');
    }
}
