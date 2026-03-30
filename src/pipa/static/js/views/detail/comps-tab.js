/**
 * Value/Comps tab — Quick Comp and Deep Comp sections.
 * Quick shows confidence, value band, warnings, comp table.
 * Deep shows county-verified comps, value range, conflicts.
 * Handles states: never run, insufficient data, complete.
 */

import { api } from '../../api.js';
import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';
import { renderMetricCard } from '../../components/metric-card.js';
import { showToast } from '../../toast.js';

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const quickComp = state.quickComp;
    const deepComp = state.deepComp;

    // Quick Comp section
    let quickBody;
    if (quickComp) {
        const metricsHtml = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            ${renderMetricCard('Confidence', quickComp.quick_confidence || 'unknown')}
            ${renderMetricCard('Ask vs Comps', quickComp.asking_vs_comps || '--')}
            ${renderMetricCard('Sold Comps', String(quickComp.sold_count ?? 0))}
            ${renderMetricCard('Active', String(quickComp.active_count ?? 0))}
        </div>`;

        let valueBandHtml = '';
        if (quickComp.rough_value_band) {
            const vb = quickComp.rough_value_band;
            valueBandHtml = `
            <div class="bg-white border border-gray-200 rounded-lg p-4">
                <h4 class="text-xs text-gray-500 mb-2">Value Band</h4>
                <div class="flex items-center gap-4 text-sm">
                    <span class="text-green-600 font-medium">Low: ${formatCurrency(vb.low)}</span>
                    <span class="text-blue-600 font-bold">Mid: ${formatCurrency(vb.mid)}</span>
                    <span class="text-red-600 font-medium">High: ${formatCurrency(vb.high)}</span>
                </div>
            </div>`;
        }

        let warningsHtml = '';
        if (quickComp.warnings && quickComp.warnings.length > 0) {
            warningsHtml = `
            <div class="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div class="text-xs text-amber-700 space-y-1">
                    ${quickComp.warnings.map(w => `<div>! ${escapeHtml(w)}</div>`).join('')}
                </div>
            </div>`;
        }

        let compTableHtml = '';
        if (quickComp.filtered_comps && quickComp.filtered_comps.length > 0) {
            const rows = quickComp.filtered_comps.map(c => {
                const statusVariant = c.status === 'sold' ? 'success' : c.status === 'active' ? 'info' : 'warning';
                return `
                <tr>
                    <td class="px-3 py-2 text-gray-900 truncate max-w-48">${escapeHtml(c.address)}</td>
                    <td class="px-3 py-2 text-right">${c.price ? formatCurrency(c.price) : '--'}</td>
                    <td class="px-3 py-2 text-right">${c.sqft ? c.sqft.toLocaleString() : '--'}</td>
                    <td class="px-3 py-2">${renderBadge(c.status, statusVariant, 'sm')}</td>
                    <td class="px-3 py-2 text-right font-medium">${c.similarity_score ? c.similarity_score.toFixed(0) : '--'}</td>
                </tr>`;
            }).join('');

            compTableHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-2">Top Comps (${quickComp.filtered_comps.length})</h4>
                <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                    <table class="min-w-full text-xs">
                        <thead>
                            <tr class="bg-gray-50 text-gray-600 text-left">
                                <th class="px-3 py-2 font-medium">Address</th>
                                <th class="px-3 py-2 font-medium text-right">Price</th>
                                <th class="px-3 py-2 font-medium text-right">Sqft</th>
                                <th class="px-3 py-2 font-medium">Status</th>
                                <th class="px-3 py-2 font-medium text-right">Score</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100">${rows}</tbody>
                    </table>
                </div>
            </div>`;
        }

        quickBody = `
        <div class="space-y-4">
            <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                <div class="text-xs text-blue-700 font-medium">Quick Comp Results</div>
            </div>
            ${metricsHtml}
            ${valueBandHtml}
            ${warningsHtml}
            ${compTableHtml}
        </div>`;
    } else {
        quickBody = `
        <div class="text-sm text-gray-500 text-center py-6 bg-gray-50 rounded-lg">
            No quick comp data. Click "Run Quick Comp" to analyze.
        </div>`;
    }

    // Deep Comp section
    let deepBody;
    if (deepComp) {
        const deepMetrics = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            ${renderMetricCard('Confidence', deepComp.confidence || '--')}
            ${renderMetricCard('Sold Comps', String((deepComp.sold_comps || []).length))}
            ${renderMetricCard('Active', String((deepComp.active_listings || []).length))}
            ${renderMetricCard('Conflicts', String((deepComp.conflicts || []).length))}
        </div>`;

        let valueRangeHtml = '';
        if (deepComp.value_range) {
            const vr = deepComp.value_range;
            valueRangeHtml = `
            <div class="bg-white border border-gray-200 rounded-lg p-4">
                <h4 class="text-xs text-gray-500 mb-2">Adjusted Value Range</h4>
                <div class="flex items-center gap-4 text-sm">
                    <span class="text-green-600 font-medium">Low: ${formatCurrency(vr.low)}</span>
                    <span class="text-blue-600 font-bold">Mid: ${formatCurrency(vr.mid)}</span>
                    <span class="text-red-600 font-medium">High: ${formatCurrency(vr.high)}</span>
                </div>
            </div>`;
        }

        let soldTable = '';
        if (deepComp.sold_comps && deepComp.sold_comps.length > 0) {
            const rows = deepComp.sold_comps.map(c => `
            <tr>
                <td class="px-3 py-2 text-gray-900 truncate max-w-40">${escapeHtml(c.address)}</td>
                <td class="px-3 py-2 text-right font-medium">${formatCurrency(c.sale_price)}</td>
                <td class="px-3 py-2">${escapeHtml(c.sale_date || '--')}</td>
                <td class="px-3 py-2 text-right">${c.sqft_above_grade ? c.sqft_above_grade.toLocaleString() : '--'}</td>
                <td class="px-3 py-2 text-right">${c.full_baths || '--'}</td>
                <td class="px-3 py-2 text-right">${c.year_built || '--'}</td>
                <td class="px-3 py-2">${c.sqft_conflict ? renderBadge('Yes', 'warning', 'sm') : '<span class="text-gray-400">No</span>'}</td>
            </tr>`).join('');

            soldTable = `
            <div>
                <h4 class="text-xs text-gray-500 mb-2">County-Verified Sold Comps</h4>
                <div class="bg-white border border-gray-200 rounded-lg overflow-hidden overflow-x-auto">
                    <table class="min-w-full text-xs">
                        <thead>
                            <tr class="bg-gray-50 text-gray-600 text-left">
                                <th class="px-3 py-2 font-medium">Address</th>
                                <th class="px-3 py-2 font-medium text-right">Sale Price</th>
                                <th class="px-3 py-2 font-medium">Date</th>
                                <th class="px-3 py-2 font-medium text-right">Sqft</th>
                                <th class="px-3 py-2 font-medium text-right">Beds</th>
                                <th class="px-3 py-2 font-medium text-right">Year</th>
                                <th class="px-3 py-2 font-medium">Conflict?</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100">${rows}</tbody>
                    </table>
                </div>
            </div>`;
        }

        let unknownsHtml = '';
        if (deepComp.unresolved_unknowns && deepComp.unresolved_unknowns.length > 0) {
            unknownsHtml = `
            <div class="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <h4 class="text-xs font-medium text-amber-700 mb-1">Unresolved Unknowns</h4>
                <ul class="text-xs text-amber-700 space-y-0.5">
                    ${deepComp.unresolved_unknowns.map(u => `<li>- ${escapeHtml(u)}</li>`).join('')}
                </ul>
            </div>`;
        }

        deepBody = `
        <div class="space-y-4">
            ${deepMetrics}
            ${valueRangeHtml}
            ${soldTable}
            ${unknownsHtml}
        </div>`;
    } else {
        deepBody = `
        <div class="text-sm text-gray-500 text-center py-6 bg-gray-50 rounded-lg">
            No deep comp data. Click "Run Deep Comp" to analyze (~2 min).
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        <div>
            <div class="flex items-center justify-between mb-3">
                <h3 class="text-sm font-semibold text-gray-700">Quick Comp Analysis</h3>
                <button id="run-quick-comp" class="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50">Run Quick Comp</button>
            </div>
            ${quickBody}
        </div>

        <div>
            <div class="flex items-center justify-between mb-3">
                <h3 class="text-sm font-semibold text-gray-700">Deep Comp Analysis</h3>
                <button id="run-deep-comp" class="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50">Run Deep Comp</button>
            </div>
            ${deepBody}
        </div>
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container, state, actions) {
    const quickBtn = container.querySelector('#run-quick-comp');
    if (quickBtn) {
        quickBtn.addEventListener('click', async () => {
            quickBtn.disabled = true;
            quickBtn.textContent = 'Running...';
            try {
                const r = await api.runCompsQuick(state.propertyId);
                state.quickComp = r;
                showToast('Quick comp complete', 'success');
                if (actions?.reload) actions.reload();
            } catch (err) {
                showToast('Quick comp failed: ' + (err.message || 'unknown'), 'error');
                quickBtn.disabled = false;
                quickBtn.textContent = 'Run Quick Comp';
            }
        });
    }

    const deepBtn = container.querySelector('#run-deep-comp');
    if (deepBtn) {
        deepBtn.addEventListener('click', async () => {
            deepBtn.disabled = true;
            deepBtn.textContent = 'Running (~2 min)...';
            try {
                const r = await api.runCompsDeep(state.propertyId);
                state.deepComp = r;
                showToast('Deep comp complete', 'success');
                if (actions?.reload) actions.reload();
            } catch (err) {
                showToast('Deep comp failed: ' + (err.message || 'unknown'), 'error');
                deepBtn.disabled = false;
                deepBtn.textContent = 'Run Deep Comp';
            }
        });
    }
}
