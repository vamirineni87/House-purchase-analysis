/**
 * Comparison view — select 2-5 properties and compare side-by-side.
 * Ranking table, price benchmarks, category scores with progress bars.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { formatCurrency, escapeHtml } from '../utils.js';
import { renderBadge } from '../components/badge.js';

const CATEGORIES = ['financial', 'condition', 'location', 'risk', 'hoa', 'surrounding'];

let _data = {
    properties: [],
    selected: new Set(),
    result: null,
    packets: {},
    loading: false,
    propertiesLoading: true,
    error: null,
};

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container) {
    _data.propertiesLoading = true;
    render(container);

    try {
        _data.properties = (await api.listProperties()) || [];
    } catch {
        _data.properties = [];
    } finally {
        _data.propertiesLoading = false;
    }

    render(container);
    bind(container);
}

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function formatScore(n) {
    return Number(n).toFixed(1);
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container) {
    const { properties, selected, result, packets, loading, propertiesLoading, error } = _data;

    // Property selector
    let selectorBody;
    if (propertiesLoading) {
        selectorBody = '<div class="text-sm text-gray-500">Loading properties...</div>';
    } else if (properties.length === 0) {
        selectorBody = '<div class="text-sm text-gray-500">No properties available. Add some first.</div>';
    } else {
        selectorBody = `
        <div class="space-y-2 max-h-60 overflow-y-auto">
            ${properties.map(p => {
                const checked = selected.has(p.id);
                const disabledAttr = (!checked && selected.size >= 5) ? 'disabled' : '';
                const bg = checked ? 'bg-blue-50' : '';
                const countyBadge = p.county ? renderBadge(p.county, p.county === 'fairfax' ? 'info' : 'warning') : '';
                return `
                <label class="flex items-center gap-3 p-2 rounded cursor-pointer hover:bg-gray-50 ${bg}">
                    <input type="checkbox" data-comp-id="${escapeHtml(p.id)}" ${checked ? 'checked' : ''} ${disabledAttr} class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    <span class="text-sm text-gray-900 flex-1">${escapeHtml(p.address || 'No address')}</span>
                    ${countyBadge}
                </label>`;
            }).join('')}
        </div>`;
    }

    const errorHtml = error
        ? `<div class="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">${escapeHtml(error)}</div>`
        : '';

    // Results
    let resultsHtml = '';
    if (result) {
        // Ranking cards
        const rankCards = result.properties.map(ps => {
            const ring = ps.rank === 1 ? 'border-blue-300 ring-2 ring-blue-100' : 'border-gray-200';
            return `
            <a href="#property/${escapeHtml(ps.property_id)}" class="bg-white border rounded-lg p-4 text-center hover:shadow-sm transition-shadow ${ring}">
                <div class="text-2xl font-bold text-gray-300 mb-1">#${ps.rank}</div>
                <div class="text-sm font-medium text-gray-900 mb-1 truncate">${escapeHtml(ps.address || ps.property_id.slice(0, 8))}</div>
                <div class="text-xl font-bold text-blue-600">${formatScore(ps.total_score)}</div>
                <div class="text-xs text-gray-500">out of 100</div>
            </a>`;
        }).join('');

        const rankingHtml = `
        <div class="mb-6">
            <h2 class="text-sm font-semibold text-gray-700 mb-3">Overall Ranking</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">${rankCards}</div>
        </div>`;

        // Price benchmarks table
        let benchmarkHtml = '';
        if (Object.keys(packets).length > 0) {
            const headers = result.properties.map(ps => `
                <th class="px-3 py-2 font-medium text-center">
                    <div class="truncate max-w-32">${escapeHtml((ps.address || '').split(',')[0] || ps.property_id.slice(0, 8))}</div>
                </th>`).join('');

            const metrics = [
                { label: 'List Price', key: 'list_price' },
                { label: 'Comp Estimate', key: 'comp_estimate' },
                { label: 'Assessment', key: 'assessment_value' },
                { label: 'Max Offer', key: 'max_offer' },
            ];

            const metricRows = metrics.map(m => {
                const cells = result.properties.map(ps => {
                    const pkt = packets[ps.property_id];
                    const val = pkt?.price_view?.[m.key];
                    return `<td class="px-3 py-2 text-center">${val ? formatCurrency(val) : '--'}</td>`;
                }).join('');
                return `<tr><td class="px-3 py-2 font-medium text-gray-700">${m.label}</td>${cells}</tr>`;
            }).join('');

            const monthlyCells = result.properties.map(ps => {
                const pkt = packets[ps.property_id];
                const val = pkt?.monthly_cost?.all_in_monthly;
                return `<td class="px-3 py-2 text-center">${val ? formatCurrency(val) + '/mo' : '--'}</td>`;
            }).join('');

            benchmarkHtml = `
            <div class="mb-6">
                <h2 class="text-sm font-semibold text-gray-700 mb-3">Price Benchmarks</h2>
                <div class="bg-white border border-gray-200 rounded-lg overflow-x-auto">
                    <table class="min-w-full text-sm">
                        <thead>
                            <tr class="bg-gray-50 text-gray-600 text-left">
                                <th class="px-3 py-2 font-medium">Metric</th>
                                ${headers}
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100">
                            ${metricRows}
                            <tr><td class="px-3 py-2 font-medium text-gray-700">Monthly Cost</td>${monthlyCells}</tr>
                        </tbody>
                    </table>
                </div>
            </div>`;
        }

        // Category scores
        const catHeaders = result.properties.map(ps => `
            <th class="px-3 py-2 font-medium text-center">
                <div class="truncate max-w-32">${escapeHtml((ps.address || '').split(',')[0] || ps.property_id.slice(0, 8))}</div>
            </th>`).join('');

        const catRows = CATEGORIES.map(cat => {
            const weightPct = Math.round((result.weights_used[cat] || 0) * 100);
            const cells = result.properties.map(ps => {
                const score = ps.category_scores[cat] ?? 50;
                return `
                <td class="px-3 py-2 text-center">
                    <div class="flex flex-col items-center">
                        <span class="font-medium text-gray-900">${formatScore(score)}</span>
                        <div class="w-16 h-1.5 bg-gray-100 rounded-full mt-1">
                            <div class="h-full bg-blue-500 rounded-full" style="width:${score}%"></div>
                        </div>
                    </div>
                </td>`;
            }).join('');
            return `
            <tr>
                <td class="px-3 py-2 font-medium capitalize text-gray-700">${cat}<span class="text-xs text-gray-400 ml-1">(${weightPct}%)</span></td>
                ${cells}
            </tr>`;
        }).join('');

        const totalCells = result.properties.map(ps =>
            `<td class="px-3 py-2 text-center text-blue-600">${formatScore(ps.total_score)}</td>`
        ).join('');

        const categoryHtml = `
        <div>
            <h2 class="text-sm font-semibold text-gray-700 mb-3">Category Scores</h2>
            <div class="bg-white border border-gray-200 rounded-lg overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="bg-gray-50 text-gray-600 text-left">
                            <th class="px-3 py-2 font-medium">Category</th>
                            ${catHeaders}
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">
                        ${catRows}
                        <tr class="bg-gray-50 font-semibold">
                            <td class="px-3 py-2 text-gray-900">Total</td>
                            ${totalCells}
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>`;

        resultsHtml = `<div class="space-y-6">${rankingHtml}${benchmarkHtml}${categoryHtml}</div>`;
    }

    container.innerHTML = `
    <div>
        <h1 class="text-2xl font-bold mb-6">Compare Properties</h1>

        <div class="bg-white border border-gray-200 rounded-lg p-4 mb-6">
            <h2 class="text-sm font-semibold text-gray-700 mb-3">Select 2-5 properties (${selected.size} selected)</h2>
            ${selectorBody}
            <div class="mt-4">
                <button id="compare-btn" ${selected.size < 2 || loading ? 'disabled' : ''} class="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50">
                    ${loading ? 'Comparing...' : 'Compare Selected'}
                </button>
            </div>
        </div>

        ${errorHtml}
        ${resultsHtml}
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container) {
    // Checkbox toggles
    container.querySelectorAll('[data-comp-id]').forEach(cb => {
        cb.addEventListener('change', () => {
            const id = cb.getAttribute('data-comp-id');
            if (cb.checked) {
                if (_data.selected.size < 5) _data.selected.add(id);
            } else {
                _data.selected.delete(id);
            }
            _data.result = null;
            render(container);
            bind(container);
        });
    });

    // Compare button
    const compareBtn = container.querySelector('#compare-btn');
    if (compareBtn) {
        compareBtn.addEventListener('click', async () => {
            if (_data.selected.size < 2) {
                _data.error = 'Select at least 2 properties to compare.';
                render(container);
                bind(container);
                return;
            }

            _data.error = null;
            _data.loading = true;
            render(container);
            bind(container);

            try {
                const data = await api.compareProperties({
                    property_ids: Array.from(_data.selected),
                });
                _data.result = data;

                // Load decision packets
                const packetMap = {};
                await Promise.allSettled(
                    Array.from(_data.selected).map(async (pid) => {
                        try {
                            const pkt = await api.getDecisionPacket(pid);
                            packetMap[pid] = pkt;
                        } catch { /* skip */ }
                    })
                );
                _data.packets = packetMap;
            } catch (err) {
                _data.error = err.message || 'Comparison failed';
            } finally {
                _data.loading = false;
            }

            render(container);
            bind(container);
        });
    }
}
