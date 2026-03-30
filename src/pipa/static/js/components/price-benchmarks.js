/**
 * Price benchmarks component — compares asking price against
 * Zestimate, assessment, assessment+7%, and comp estimate.
 * Green if below, red if above.
 */

import { formatCurrency } from '../utils.js';

function formatPct(n) {
    const sign = n > 0 ? '+' : '';
    return `${sign}${(n * 100).toFixed(1)}%`;
}

function diffColor(diff) {
    if (diff < -0.02) return 'text-green-600';
    if (diff > 0.02) return 'text-red-600';
    return 'text-gray-600';
}

function diffBg(diff) {
    if (diff < -0.02) return 'bg-green-50 border-green-200';
    if (diff > 0.02) return 'bg-red-50 border-red-200';
    return 'bg-gray-50 border-gray-200';
}

function benchmarkCard(label, benchmark, askPrice) {
    if (!benchmark) {
        return `
        <div class="border border-gray-200 rounded-lg p-3 bg-gray-50">
            <div class="text-xs text-gray-500 mb-1">${esc(label)}</div>
            <div class="text-sm text-gray-400">No data</div>
        </div>`;
    }

    const diff = (askPrice - benchmark) / benchmark;
    const hint = diff > 0.02 ? 'Ask is above' : diff < -0.02 ? 'Ask is below' : 'Near parity';

    return `
    <div class="border rounded-lg p-3 ${diffBg(diff)}">
        <div class="text-xs text-gray-500 mb-1">${esc(label)}</div>
        <div class="text-lg font-bold text-gray-900">${formatCurrency(benchmark)}</div>
        <div class="flex items-center gap-2 mt-1">
            <span class="text-sm font-medium ${diffColor(diff)}">${formatPct(diff)}</span>
            <span class="text-xs text-gray-500">${hint}</span>
        </div>
    </div>`;
}

/**
 * Render price benchmarks grid.
 * @param {number} askPrice
 * @param {number} zestimate
 * @param {number} assessedValue
 * @param {number} assessedPlus7  - Computed if not provided (assessed * 1.07).
 * @param {number} compEstimate
 * @returns {string} HTML string
 */
export function renderPriceBenchmarks(askPrice, zestimate, assessedValue, assessedPlus7, compEstimate) {
    if (!askPrice) {
        return '<div class="text-sm text-gray-500">No list price available for benchmarks.</div>';
    }

    const ap7 = assessedPlus7 || (assessedValue ? Math.round(assessedValue * 1.07) : undefined);

    return `
    <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-3">Price Benchmarks vs Ask (${formatCurrency(askPrice)})</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            ${benchmarkCard('Zestimate', zestimate, askPrice)}
            ${benchmarkCard('Assessed Value', assessedValue, askPrice)}
            ${benchmarkCard('Assessed + 7%', ap7, askPrice)}
            ${benchmarkCard('Comp Estimate', compEstimate, askPrice)}
        </div>
    </div>`;
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
