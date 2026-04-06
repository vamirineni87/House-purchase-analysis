/**
 * Section §10: Comparable Sales.
 *
 * Quick Comp and Deep Comp sub-sections with confidence badges,
 * value bands, warnings, filtered comps tables, and conflicts.
 */

import { formatCurrency, formatDate, formatNumber, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { showToast } from '../../../toast.js';
import { api } from '../../../api.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Comparable Sales';
export const ID = 'comps';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(state) {
    return !!state.deepComp;
}

export function getStateBadge(state) {
    if (state.deepComp) return { label: 'Complete', variant: 'success' };
    if (state.quickComp) return { label: 'Partial', variant: 'warning' };
    return { label: 'Not run', variant: 'not-run' };
}

export function headerExtra(state) {
    const qLoading = state.actionLoading?.quickComp;
    const dLoading = state.actionLoading?.deepComp;
    return `
    <div class="flex gap-1.5">
        <button class="comps-quick-btn px-2.5 py-1 text-xs font-medium rounded border transition-colors
            ${qLoading ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed' : 'bg-white text-blue-600 border-blue-300 hover:bg-blue-50'}"
            ${qLoading ? 'disabled' : ''}>
            ${qLoading ? 'Running...' : 'Quick Comp'}
        </button>
        <button class="comps-deep-btn px-2.5 py-1 text-xs font-medium rounded border transition-colors
            ${dLoading ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed' : 'bg-white text-blue-600 border-blue-300 hover:bg-blue-50'}"
            ${dLoading ? 'disabled' : ''}>
            ${dLoading ? 'Running...' : 'Deep Comp'}
        </button>
    </div>`;
}

// ── Helpers ────────────────────────────────────────────────────────

function confidenceVariant(conf) {
    if (!conf) return 'muted';
    const c = String(conf).toLowerCase();
    if (c === 'high') return 'success';
    if (c === 'medium' || c === 'moderate') return 'warning';
    return 'critical';
}

function renderCompTable(comps, isDeep) {
    if (!comps || comps.length === 0) return '';

    // Sort by similarity score descending
    const sorted = [...comps].sort((a, b) => (b.similarity_score ?? 0) - (a.similarity_score ?? 0));

    const rows = sorted.map((c, i) => {
        const bg = i % 2 === 1 ? 'bg-gray-50' : '';
        const address = c.address || 'Unknown';
        const price = c.price ?? c.sale_price;
        const sqft = c.sqft ?? c.sqft_above_grade;
        const beds = c.beds ?? c.bedrooms ?? '';
        const baths = c.baths ?? c.bathrooms ?? '';
        const bedsAndBaths = [beds, baths].filter(v => v !== '' && v != null).join('/');
        const score = c.similarity_score;
        const date = c.date ?? c.sale_date ?? '';

        return `
        <tr class="${bg} hover:bg-gray-100 transition-colors">
            <td class="px-2 py-1 text-xs text-gray-900 truncate max-w-40">${escapeHtml(address)}</td>
            <td class="px-2 py-1 text-xs text-right font-medium text-gray-700">${price != null ? formatCurrency(price) : '\u2014'}</td>
            <td class="px-2 py-1 text-xs text-gray-600 whitespace-nowrap">${formatDate(date)}</td>
            <td class="px-2 py-1 text-xs text-right text-gray-600">${sqft != null ? formatNumber(sqft) : '\u2014'}</td>
            <td class="px-2 py-1 text-xs text-center text-gray-600">${bedsAndBaths || '\u2014'}</td>
            <td class="px-2 py-1 text-xs text-right font-medium">${score != null ? `<span class="${score >= 80 ? 'text-green-600' : score >= 60 ? 'text-amber-600' : 'text-gray-500'}">${score.toFixed(0)}</span>` : '\u2014'}</td>
        </tr>`;
    }).join('');

    return `
    <div class="overflow-x-auto rounded-lg border border-gray-200">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Address</th>
                    <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Price</th>
                    <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                    <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Sqft</th>
                    <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500 uppercase">Bed/Bath</th>
                    <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Score</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-100">${rows}</tbody>
        </table>
    </div>`;
}

function renderValueBand(band, label) {
    if (!band) return '';
    return `
    <div class="bg-white border border-gray-200 rounded-lg p-3">
        <div class="text-xs text-gray-500 mb-1.5">${escapeHtml(label)}</div>
        <div class="flex items-center gap-4 text-xs">
            <span class="text-green-600 font-medium">Low: ${formatCurrency(band.low)}</span>
            <span class="text-blue-600 font-bold">Mid: ${formatCurrency(band.mid)}</span>
            <span class="text-red-600 font-medium">High: ${formatCurrency(band.high)}</span>
        </div>
    </div>`;
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const { quickComp, deepComp } = state;

    if (!quickComp && !deepComp) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">No comp data available. Run <strong>Quick Comp</strong> to find comparable sales.</p>
        </div>`;
    }

    const parts = [];

    // ── Quick Comp ────────────────────────────────────────────────
    if (quickComp) {
        const confBadge = renderBadge(
            String(quickComp.quick_confidence || 'unknown'),
            confidenceVariant(quickComp.quick_confidence),
            'sm'
        );
        const askVsComps = quickComp.asking_vs_comps
            ? `<span class="text-xs text-gray-600">Ask vs Comps: <strong>${escapeHtml(String(quickComp.asking_vs_comps))}</strong></span>`
            : '';

        const valueBand = renderValueBand(quickComp.rough_value_band, 'Value Band');

        let warningsHtml = '';
        if (quickComp.warnings?.length) {
            const items = quickComp.warnings.map(w => `<li class="text-xs text-amber-700">! ${escapeHtml(w)}</li>`).join('');
            warningsHtml = `
            <div class="bg-amber-50 border border-amber-200 rounded-lg p-2.5">
                <ul class="space-y-0.5">${items}</ul>
            </div>`;
        }

        const compTable = renderCompTable(quickComp.filtered_comps, false);
        const compCount = quickComp.filtered_comps?.length || 0;

        parts.push(`
        <div>
            <div class="flex items-center gap-2 mb-2">
                <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide">Quick Comp</h4>
                ${confBadge}
                ${askVsComps}
            </div>
            <div class="space-y-2.5">
                ${valueBand}
                ${warningsHtml}
                ${compTable ? `<div><div class="text-xs text-gray-500 mb-1">${compCount} comparable${compCount !== 1 ? 's' : ''}</div>${compTable}</div>` : ''}
            </div>
        </div>`);
    }

    // ── Deep Comp ─────────────────────────────────────────────────
    if (deepComp) {
        const confBadge = renderBadge(
            String(deepComp.confidence || 'unknown'),
            confidenceVariant(deepComp.confidence),
            'sm'
        );

        const valueRange = renderValueBand(deepComp.value_range, 'Adjusted Value Range');

        const soldComps = deepComp.sold_comps || [];
        let soldTableHtml = '';
        if (soldComps.length > 0) {
            soldTableHtml = `
            <div>
                <div class="text-xs text-gray-500 mb-1">County-Verified Sold Comps (${soldComps.length})</div>
                ${renderCompTable(soldComps, true)}
            </div>`;
        }

        let conflictsHtml = '';
        const conflicts = deepComp.conflicts || [];
        if (conflicts.length > 0) {
            const items = conflicts.map(c => {
                const msg = typeof c === 'string' ? c : (c.message || c.description || JSON.stringify(c));
                return `<li class="text-xs text-red-700">! ${escapeHtml(msg)}</li>`;
            }).join('');
            conflictsHtml = `
            <div class="bg-red-50 border border-red-200 rounded-lg p-2.5">
                <div class="text-xs font-medium text-red-700 mb-1">Conflicts</div>
                <ul class="space-y-0.5">${items}</ul>
            </div>`;
        }

        parts.push(`
        <div>
            <div class="flex items-center gap-2 mb-2">
                <h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide">Deep Comp</h4>
                ${confBadge}
            </div>
            <div class="space-y-2.5">
                ${valueRange}
                ${soldTableHtml}
                ${conflictsHtml}
            </div>
        </div>`);
    }

    return `<div class="space-y-5">${parts.join('')}</div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    const quickBtn = container.querySelector('.comps-quick-btn');
    if (quickBtn) {
        quickBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (quickBtn.disabled) return;

            quickBtn.disabled = true;
            quickBtn.textContent = 'Running...';

            try {
                const result = await api.runCompsQuick(state.property.id);
                state.quickComp = result;
                showToast('Quick comp complete', 'success');
                if (actions?.rerenderSection) {
                    actions.rerenderSection(ID);
                } else if (actions?.reload) {
                    actions.reload();
                }
            } catch (err) {
                showToast('Quick comp failed: ' + (err.message || 'unknown'), 'error');
                quickBtn.disabled = false;
                quickBtn.textContent = 'Quick Comp';
            }
        });
    }

    const deepBtn = container.querySelector('.comps-deep-btn');
    if (deepBtn) {
        deepBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (deepBtn.disabled) return;

            deepBtn.disabled = true;
            deepBtn.textContent = 'Running...';

            try {
                const result = await api.runCompsDeep(state.property.id);
                state.deepComp = result;
                showToast('Deep comp complete', 'success');
                if (actions?.rerenderSection) {
                    actions.rerenderSection(ID);
                } else if (actions?.reload) {
                    actions.reload();
                }
            } catch (err) {
                showToast('Deep comp failed: ' + (err.message || 'unknown'), 'error');
                deepBtn.disabled = false;
                deepBtn.textContent = 'Deep Comp';
            }
        });
    }
}
