/**
 * Section §6: Condition
 *
 * Condition score progress bar, component cards (Roof, HVAC, etc.),
 * capex forecast bars. Color-coded remaining life.
 */

import { formatCurrency, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { api } from '../../../api.js';
import { showToast } from '../../../toast.js';

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
//
// No section-level "Run Condition" button. Condition is computed by the
// pipeline orchestrator from resolver-merged AI/county/listing data, so
// the only correct way to refresh it is to rerun the pipeline (or the
// rerun_ai_pass_2 sub-pipeline). A standalone button used to exist that
// hit AnalysisService.run_condition, but that path read directly from
// the ComponentSystem table and produced stale year-built defaults
// instead of the AI-extracted years — see the Fairhunt HVAC=2007 vs
// 2021 incident.
export function headerExtra(state) {
    return '';
}

// ── Helpers ────────────────────────────────────────────────────────

function _getData(state) {
    const raw = state.conditionData || state.analysisResults?.condition?.output || null;
    if (!raw) return null;
    // Apply manual overrides on read so they survive page refreshes
    // even before the next pipeline run rewrites the stored condition.
    const overrides = state.componentOverrides || {};
    if (!Object.keys(overrides).length || !Array.isArray(raw.components)) {
        return raw;
    }
    return {
        ...raw,
        components: raw.components.map(c => {
            const ov = overrides[c.canonical_key];
            if (!ov || ov.year == null) return c;
            return _recomputeComponent(c, ov.year);
        }),
    };
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
    const canonicalKey = comp.canonical_key || '';
    const isDefaulted = comp.is_defaulted || comp.source === 'default_year_built';
    const isManual = comp.source === 'manual_override';

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

    const yearText = year != null ? String(year) : '?';
    let yearBadge = '';
    if (isManual) {
        yearBadge = '<span class="text-[9px] text-blue-500 ml-1" title="Manual override">[manual]</span>';
    } else if (isDefaulted) {
        yearBadge = '<span class="text-[9px] text-gray-400 ml-1" title="Defaulted to year built — no specific install year extracted">(est)</span>';
    } else if (comp.source === 'ai_extracted') {
        yearBadge = '<span class="text-[9px] text-green-500 ml-1" title="From AI / permits">[ai]</span>';
    }

    // Year cell becomes a click target if we know the canonical key.
    // Two-state: display vs editor (the editor is hidden by default
    // and toggled in bind() via data-component-edit handlers).
    const yearCell = canonicalKey ? `
        <div data-component-row="${escapeHtml(canonicalKey)}" class="inline-flex items-center gap-1">
            <span data-year-display="${escapeHtml(canonicalKey)}" class="cursor-pointer hover:text-blue-600" title="Click to edit install year">
                ${yearText}${yearBadge}
            </span>
            <button data-year-edit="${escapeHtml(canonicalKey)}" type="button"
                    class="text-gray-300 hover:text-blue-500 text-[10px] leading-none"
                    title="Edit install year">&#9998;</button>
            ${isManual ? `<button data-year-clear="${escapeHtml(canonicalKey)}" type="button"
                    class="text-gray-300 hover:text-red-500 text-[10px] leading-none"
                    title="Clear manual override (revert to automatic)">&times;</button>` : ''}
            <span data-year-editor="${escapeHtml(canonicalKey)}" class="hidden items-center gap-1">
                <input data-year-input="${escapeHtml(canonicalKey)}" type="number" min="1800" max="2100"
                    value="${year != null ? year : ''}"
                    class="w-16 px-1 py-0 text-xs border border-blue-400 rounded font-mono" />
                <button data-year-save="${escapeHtml(canonicalKey)}" type="button"
                    class="text-green-600 hover:text-green-700 text-xs">&#10003;</button>
                <button data-year-cancel="${escapeHtml(canonicalKey)}" type="button"
                    class="text-gray-400 hover:text-gray-600 text-xs">&times;</button>
            </span>
        </div>
    ` : `${yearText}${yearBadge}`;

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

    const rowClass = isManual ? 'bg-blue-50/40' : '';

    return `
    <tr class="hover:bg-gray-50 transition-colors ${rowClass}">
        <td class="px-2 py-1 text-xs">
            <div class="flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full ${status.dot} shrink-0"></span>
                <span class="font-medium text-gray-900 capitalize">${escapeHtml(displayName)}</span>
            </div>
        </td>
        <td class="px-2 py-1 text-xs text-gray-700 text-right font-mono">${yearCell}</td>
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
    const noted = summary.noted_improvements_count ?? (data.noted_improvements || []).length;
    const total10yr = summary.total_capex_10yr ?? null;

    const pills = [];
    if (total != null) pills.push(`<span class="text-gray-600">${total} tracked</span>`);
    if (urgent > 0)    pills.push(`<span class="text-red-600 font-medium">${urgent} urgent</span>`);
    if (monitor > 0)   pills.push(`<span class="text-amber-600 font-medium">${monitor} monitor</span>`);
    if (defaulted > 0) pills.push(`<span class="text-gray-400">${defaulted} est. from year built</span>`);
    if (noted > 0)     pills.push(`<span class="text-gray-500">${noted} noted (no year)</span>`);
    if (total10yr != null && total10yr > 0) {
        pills.push(`<span class="text-gray-700">10yr capex: <span class="font-semibold">${formatCurrency(total10yr)}</span></span>`);
    }
    if (pills.length === 0) return '';

    return `
    <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
        ${pills.join('<span class="text-gray-300">·</span>')}
    </div>`;
}

/**
 * Year-less upgrades the AI extracted from the listing description
 * (e.g. "in-ground sprinkler system", "custom shades", "resurfaced
 * driveway"). Shown as a compact list — no age math because we have
 * no install date.
 */
function renderNotedImprovements(items) {
    if (!items || items.length === 0) return '';
    const rows = items.map(it => {
        const conf = it.confidence || 'low';
        const confColor = conf === 'high' ? 'text-green-600'
            : conf === 'medium' ? 'text-amber-600'
            : 'text-gray-400';
        const details = it.details
            ? `<span class="text-gray-500"> &middot; ${escapeHtml(it.details)}</span>`
            : '';
        return `
        <li class="flex items-start gap-2 py-1 text-xs">
            <span class="${confColor} mt-0.5">&bull;</span>
            <div class="flex-1">
                <span class="font-medium text-gray-800">${escapeHtml(it.name)}</span>${details}
            </div>
            <span class="text-[10px] uppercase tracking-wide ${confColor} shrink-0">${conf}</span>
        </li>`;
    }).join('');

    return `
    <div>
        <div class="flex items-center justify-between mb-1.5">
            <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                Other Noted Improvements
            </h4>
            <span class="text-[10px] text-gray-400">${items.length} from listing &mdash; no install year</span>
        </div>
        <div class="bg-white border border-gray-200 rounded p-2">
            <ul class="divide-y divide-gray-100">${rows}</ul>
        </div>
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
    const noted = data.noted_improvements || [];

    return `
    <div class="space-y-3">
        ${renderScoreBar(data)}
        ${renderSummaryBar(data)}
        ${renderComponentsTable(components)}
        ${renderNotedImprovements(noted)}
        ${renderCapexForecast(data)}
    </div>`;
}

// ── Bind ────────────────────────────────────────────────────────────

/**
 * Recompute a single component row in-place using the same lifespan/cost
 * constants the backend uses. Avoids a full pipeline rerun for what is
 * pure local arithmetic — the user just gets snappy feedback when they
 * type a year. The next pipeline run will re-derive everything from
 * stored overrides anyway.
 */
function _recomputeComponent(comp, newYear) {
    const updated = { ...comp };
    updated.estimated_install_year = newYear;
    updated.source = 'manual_override';
    updated.is_defaulted = false;
    if (newYear != null) {
        updated.age = new Date().getFullYear() - newYear;
        if (updated.lifespan != null) {
            updated.remaining_life = Math.max(0, updated.lifespan - updated.age);
        }
    }
    return updated;
}

function _enterEditMode(container, key) {
    const display = container.querySelector(`[data-year-display="${key}"]`);
    const editBtn = container.querySelector(`[data-year-edit="${key}"]`);
    const clearBtn = container.querySelector(`[data-year-clear="${key}"]`);
    const editor = container.querySelector(`[data-year-editor="${key}"]`);
    const input = container.querySelector(`[data-year-input="${key}"]`);
    if (!display || !editor) return;
    display.classList.add('hidden');
    if (editBtn) editBtn.classList.add('hidden');
    if (clearBtn) clearBtn.classList.add('hidden');
    editor.classList.remove('hidden');
    editor.classList.add('inline-flex');
    if (input) {
        input.focus();
        input.select();
    }
}

function _exitEditMode(container, key) {
    const display = container.querySelector(`[data-year-display="${key}"]`);
    const editBtn = container.querySelector(`[data-year-edit="${key}"]`);
    const clearBtn = container.querySelector(`[data-year-clear="${key}"]`);
    const editor = container.querySelector(`[data-year-editor="${key}"]`);
    if (!display || !editor) return;
    display.classList.remove('hidden');
    if (editBtn) editBtn.classList.remove('hidden');
    if (clearBtn) clearBtn.classList.remove('hidden');
    editor.classList.add('hidden');
    editor.classList.remove('inline-flex');
}

export function bind(container, state, actions) {
    // Inline edit handlers for component install years.
    //
    // Updates are saved to AppSetting via the component-overrides API.
    // The override is applied at rank 100 by the resolver on the next
    // pipeline run, beating county/AI/year_built defaults. We also
    // recompute the row in place so the user sees immediate feedback
    // without having to wait for a full rerun.
    if (!container) return;
    if (!state.propertyId) return;

    // GUARD: rerenderSection calls bind() again on the same DOM element
    // every time the section refreshes. Without this guard each refresh
    // stacks another click listener and a single edit fires N requests
    // in parallel — which races past the upsert and (used to) trip the
    // UNIQUE constraint. We tag the container so subsequent binds skip.
    if (container.dataset.conditionBound === 'true') return;
    container.dataset.conditionBound = 'true';

    // Important: read state.propertyId INSIDE each handler invocation,
    // not via outer closure. The dataset.conditionBound guard prevents
    // re-binding, so if SPA navigation reuses the section element across
    // properties the closure would otherwise write overrides to the
    // WRONG property. `state` is captured by reference; `state.propertyId`
    // tracks the live value.
    container.addEventListener('click', async (e) => {
        const propertyId = state.propertyId;
        if (!propertyId) return;
        const editBtn = e.target.closest('[data-year-edit], [data-year-display]');
        if (editBtn) {
            const key = editBtn.getAttribute('data-year-edit') || editBtn.getAttribute('data-year-display');
            _enterEditMode(container, key);
            return;
        }
        const cancelBtn = e.target.closest('[data-year-cancel]');
        if (cancelBtn) {
            _exitEditMode(container, cancelBtn.getAttribute('data-year-cancel'));
            return;
        }
        const saveBtn = e.target.closest('[data-year-save]');
        if (saveBtn) {
            const key = saveBtn.getAttribute('data-year-save');
            const input = container.querySelector(`[data-year-input="${key}"]`);
            const yearStr = input?.value || '';
            const year = parseInt(yearStr, 10);
            if (!year || year < 1800 || year > 2100) {
                showToast('Enter a valid year between 1800 and 2100', 'error');
                return;
            }
            try {
                await api.setComponentOverride(propertyId, key, year);
                // Stash the override on state so _getData picks it up
                // on every subsequent render (and after page refresh
                // once lazyLoadAll re-fetches the override list).
                if (!state.componentOverrides) state.componentOverrides = {};
                state.componentOverrides[key] = {
                    year,
                    notes: null,
                    set_at: new Date().toISOString(),
                };
                showToast(`${key} install year set to ${year}`, 'success');
                if (typeof actions?.rerenderSection === 'function') {
                    actions.rerenderSection('condition');
                }
            } catch (err) {
                showToast(`Failed to save: ${err.message}`, 'error');
            }
            return;
        }
        const clearBtn = e.target.closest('[data-year-clear]');
        if (clearBtn) {
            const key = clearBtn.getAttribute('data-year-clear');
            if (!confirm(`Clear manual override for ${key}? It will revert to the automatic value on the next pipeline run.`)) return;
            try {
                await api.deleteComponentOverride(propertyId, key);
                if (state.componentOverrides) {
                    delete state.componentOverrides[key];
                }
                showToast(`${key} override cleared — rerun pipeline for full refresh`, 'success');
                if (typeof actions?.rerenderSection === 'function') {
                    actions.rerenderSection('condition');
                }
            } catch (err) {
                showToast(`Failed to clear: ${err.message}`, 'error');
            }
            return;
        }
    });

    // Allow Enter to save / Esc to cancel inside the year input
    container.addEventListener('keydown', (e) => {
        const input = e.target.closest('[data-year-input]');
        if (!input) return;
        const key = input.getAttribute('data-year-input');
        if (e.key === 'Enter') {
            e.preventDefault();
            const saveBtn = container.querySelector(`[data-year-save="${key}"]`);
            saveBtn?.click();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            _exitEditMode(container, key);
        }
    });
}
