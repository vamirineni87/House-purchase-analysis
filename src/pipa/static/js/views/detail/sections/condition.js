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
export const DEFAULT_EXPANDED = false;

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

function _statusForComp(comp) {
    const remaining = comp.remaining_life;
    const age = comp.age ?? (comp.estimated_install_year
        ? new Date().getFullYear() - comp.estimated_install_year
        : null);
    if (remaining != null) {
        if (remaining <= 2) return { dot: 'bg-red-500',   label: 'Replace soon', tone: 'red' };
        if (remaining <= 5) return { dot: 'bg-amber-500', label: 'Monitor',      tone: 'amber' };
        return { dot: 'bg-green-500', label: 'Good', tone: 'green' };
    }
    if (age != null) {
        if (age > 20) return { dot: 'bg-red-500',   label: 'Replace soon', tone: 'red' };
        if (age > 12) return { dot: 'bg-amber-500', label: 'Monitor',      tone: 'amber' };
    }
    return { dot: 'bg-green-500', label: 'Good', tone: 'green' };
}

/** Compact single-row component renderer (table row). */
function renderComponentRow(comp) {
    const displayName = comp.display_name
        || (comp.component_type || comp.type || 'unknown').replace(/_/g, ' ');
    const year = comp.estimated_install_year || comp.install_year;
    const age = comp.age ?? (year ? new Date().getFullYear() - year : null);
    const lifespan = comp.lifespan;
    const remaining = comp.remaining_life;
    const cost = comp.replacement_cost;
    const isDefaulted = comp.is_defaulted || comp.source === 'default_year_built';

    const status = _statusForComp(comp);
    const rlColor = remainingLifeColor(remaining);

    // Inline life progress bar: width = % of lifespan remaining
    const lifePct = (lifespan && remaining != null)
        ? Math.max(0, Math.min(100, (remaining / lifespan) * 100))
        : null;
    const barColor = status.tone === 'red'
        ? 'bg-red-500'
        : status.tone === 'amber'
            ? 'bg-amber-500'
            : 'bg-green-500';

    const yearCell = year != null ? String(year) : '<span class="text-gray-300">?</span>';
    const yearNote = isDefaulted
        ? '<span class="text-[9px] text-gray-400 ml-1" title="Defaulted to year built — no specific install year extracted">(est)</span>'
        : '';
    const ageCell = age != null ? `${age}y` : '&mdash;';
    const lifeCell = lifespan != null ? `${lifespan}y` : '&mdash;';
    const remainingCell = remaining != null
        ? `<span class="${rlColor} font-semibold">${remaining}y</span>`
        : '<span class="text-gray-300">&mdash;</span>';
    const costCell = cost != null && cost > 0
        ? formatCurrency(cost)
        : '<span class="text-gray-300">&mdash;</span>';

    const barHtml = lifePct != null
        ? `<div class="w-16 h-1 bg-gray-100 rounded-full overflow-hidden">
             <div class="h-full ${barColor}" style="width:${lifePct}%"></div>
           </div>`
        : '<div class="w-16"></div>';

    return `
    <tr class="hover:bg-gray-50 transition-colors">
        <td class="px-2 py-1 text-xs">
            <div class="flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full ${status.dot} shrink-0"></span>
                <span class="font-medium text-gray-900 capitalize">${escapeHtml(displayName)}</span>
            </div>
        </td>
        <td class="px-2 py-1 text-xs text-gray-700 text-right font-mono">${yearCell}${yearNote}</td>
        <td class="px-2 py-1 text-xs text-gray-600 text-right font-mono">${ageCell}</td>
        <td class="px-2 py-1 text-xs text-gray-500 text-right font-mono">${lifeCell}</td>
        <td class="px-2 py-1 text-xs text-right font-mono">${remainingCell}</td>
        <td class="px-2 py-1">${barHtml}</td>
        <td class="px-2 py-1 text-xs text-gray-700 text-right font-mono">${costCell}</td>
        <td class="px-2 py-1 text-[10px] text-gray-500">${status.label}</td>
    </tr>`;
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

function renderSummaryBar(data) {
    const summary = data.summary || {};
    const total = summary.total_components ?? (data.components || []).length;
    const urgent = summary.urgent_count ?? 0;
    const monitor = summary.monitor_count ?? 0;
    const defaulted = summary.defaulted_count ?? 0;
    const total10yr = summary.total_capex_10yr ?? null;

    const pills = [];
    if (total != null) pills.push(`<span class="text-gray-600">${total} tracked</span>`);
    if (urgent > 0)    pills.push(`<span class="text-red-600 font-medium">${urgent} urgent</span>`);
    if (monitor > 0)   pills.push(`<span class="text-amber-600 font-medium">${monitor} monitor</span>`);
    if (defaulted > 0) pills.push(`<span class="text-gray-400">${defaulted} est. from year built</span>`);
    if (total10yr != null && total10yr > 0) {
        pills.push(`<span class="text-gray-700">10yr capex: <span class="font-semibold">${formatCurrency(total10yr)}</span></span>`);
    }
    if (pills.length === 0) return '';

    return `
    <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
        ${pills.join('<span class="text-gray-300">·</span>')}
    </div>`;
}

function renderComponentsTable(components) {
    if (!components || components.length === 0) return '';
    const rows = components.map(c => renderComponentRow(c)).join('');
    return `
    <div>
        <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">
            Components
        </h4>
        <div class="bg-white border border-gray-200 rounded overflow-hidden">
            <table class="w-full text-xs">
                <thead class="bg-gray-50 text-[10px] uppercase tracking-wide text-gray-500">
                    <tr>
                        <th class="px-2 py-1 text-left">Component</th>
                        <th class="px-2 py-1 text-right">Year</th>
                        <th class="px-2 py-1 text-right">Age</th>
                        <th class="px-2 py-1 text-right">Life</th>
                        <th class="px-2 py-1 text-right">Left</th>
                        <th class="px-2 py-1"></th>
                        <th class="px-2 py-1 text-right">Replace</th>
                        <th class="px-2 py-1 text-left">Status</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${rows}</tbody>
            </table>
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

    return `
    <div class="space-y-3">
        ${renderScoreBar(data)}
        ${renderSummaryBar(data)}
        ${renderComponentsTable(components)}
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
