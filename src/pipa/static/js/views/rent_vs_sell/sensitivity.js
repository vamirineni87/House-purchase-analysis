/**
 * Rent vs Sell — sensitivity heatmap.
 *
 * User-triggered refresh only. State lives in state.heatmapState, which
 * carries: { preset, comparator, horizon, grid, stale, loading }.
 */

import { formatCurrency, escapeHtml } from '../../utils.js';

const PRESETS = [
    ['value_x_rent', 'Value × Rent'],
    ['value_x_capex', 'Value × Capex'],
    ['value_x_refi', 'Value × Refi'],
    ['rent_x_vacancy', 'Rent × Vacancy'],
    ['rent_x_reinvest', 'Rent × Reinvestment'],
];

const COMPARATORS = [
    ['sell_vs_keep_5y', 'Sell vs Keep 5Y'],
    ['sell_vs_keep_10y', 'Sell vs Keep 10Y'],
    ['sell_vs_rent_then_sell', 'Sell vs Rent-Then-Sell'],
];

export function renderSensitivity(state) {
    const hs = state.heatmapState;

    const toolbar = `
    <div class="flex flex-wrap items-center gap-2 px-3 py-2 border-b bg-gray-50">
        <select id="rvs-sens-preset" class="text-xs border border-gray-300 rounded px-2 py-1">
            ${PRESETS.map(([k, l]) => `<option value="${k}" ${hs.preset === k ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}
        </select>
        <select id="rvs-sens-comparator" class="text-xs border border-gray-300 rounded px-2 py-1">
            ${COMPARATORS.map(([k, l]) => `<option value="${k}" ${hs.comparator === k ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}
        </select>
        <select id="rvs-sens-horizon" class="text-xs border border-gray-300 rounded px-2 py-1">
            <option value="5y" ${hs.horizon === '5y' ? 'selected' : ''}>5Y</option>
            <option value="10y" ${hs.horizon === '10y' ? 'selected' : ''}>10Y</option>
        </select>
        <button id="rvs-sens-refresh" class="text-xs font-medium px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">
            ${hs.grid ? 'Refresh heatmap' : 'Load heatmap'}
        </button>
        ${hs.stale && hs.grid ? '<span class="text-xs text-amber-700">⚠ Stale — refresh to update</span>' : ''}
    </div>`;

    let body;
    if (hs.loading) {
        body = '<div class="p-4 text-xs text-blue-600">Computing heatmap…</div>';
    } else if (!hs.grid) {
        body = '<div class="p-4 text-xs text-gray-400">Click "Load heatmap" to compute the sensitivity grid.</div>';
    } else {
        // When the grid is stale (inputs have changed since it was computed),
        // dim the whole section so users can visually tell the numbers below
        // don't reflect the current inputs. Breakeven footer is suppressed
        // entirely because those numbers are the most dangerous to mis-read.
        const dimWrapper = hs.stale
            ? '<div class="opacity-40 pointer-events-none">'
            : '<div>';
        body = dimWrapper + renderHeatmapGrid(hs.grid) + '</div>';
        if (!hs.stale) {
            body += renderBreakevenFooter(hs.grid);
        }
    }

    return `
    <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-4">
        <div class="px-3 py-2 border-b bg-gray-50 text-xs font-semibold text-gray-700 uppercase">Sensitivity heatmap</div>
        ${toolbar}
        ${body}
    </div>`;
}

function renderHeatmapGrid(grid) {
    const { cells, x_values, y_values, x_label, y_label } = grid;
    const maxMag = Math.max(1, ...cells.flat().map(c => Math.abs(c.delta)));

    const fmtAxis = (v) => {
        if (typeof v === 'number' && Math.abs(v) <= 1) return `${(v * 100).toFixed(0)}%`;
        if (typeof v === 'number') return formatCurrency(v);
        return String(v ?? '');
    };

    const headerCells = x_values
        .map(x => `<th class="text-[10px] font-medium text-gray-500 px-1.5 py-1">${escapeHtml(fmtAxis(x))}</th>`)
        .join('');
    const rowsHtml = y_values.map((y, yi) => {
        const cellsHtml = cells[yi].map(c => {
            const absK = Math.round(Math.abs(c.delta) / 1000);
            const label = c.delta >= 0 ? `+${absK}k` : `-${absK}k`;
            const intensity = Math.min(1, Math.abs(c.delta) / maxMag);
            const alpha = 0.15 + intensity * 0.55;
            const bg = c.delta > 0
                ? `rgba(34, 197, 94, ${alpha})`
                : `rgba(239, 68, 68, ${alpha})`;
            const title = `${escapeHtml(String(c.winner ?? ''))}: ${formatCurrency(c.delta)}`;
            return `<td class="text-[10px] text-center px-1 py-1" style="background: ${bg}" title="${title}">${label}</td>`;
        }).join('');
        return `<tr><th class="text-[10px] font-medium text-gray-500 px-2 py-1 text-right">${escapeHtml(fmtAxis(y))}</th>${cellsHtml}</tr>`;
    }).join('');

    return `
    <div class="p-3 overflow-x-auto">
        <table class="border-collapse">
            <thead><tr><th class="text-[10px] text-gray-400 px-1 py-1">${escapeHtml(y_label)} ↓ / ${escapeHtml(x_label)} →</th>${headerCells}</tr></thead>
            <tbody>${rowsHtml}</tbody>
        </table>
        <div class="text-[10px] text-gray-400 mt-2">Green = keep wins (positive delta) · Red = sell wins</div>
    </div>`;
}

function renderBreakevenFooter(grid) {
    const beVal = grid.breakeven_value_change_pct;
    const beRent = grid.breakeven_rent_change_pct;
    const beCapex = grid.breakeven_capex_shock_dollars;
    if (beVal == null && beRent == null && beCapex == null) return '';

    const item = (label, value) => `
        <div class="px-3 py-1">
            <span class="text-[10px] text-gray-500">${escapeHtml(label)}:</span>
            <span class="text-[11px] font-semibold text-gray-900 ml-1">${value}</span>
        </div>`;

    const fmtPct = (v) => (v == null ? 'n/a' : `${(v * 100).toFixed(2)}%`);
    const fmtDollars = (v) => (v == null ? 'n/a' : formatCurrency(v));

    return `
    <div class="px-3 py-2 border-t bg-gray-50 flex flex-wrap gap-3 items-center">
        <span class="text-[10px] font-semibold text-gray-500 uppercase">Breakevens:</span>
        ${item('Value change', fmtPct(beVal))}
        ${item('Rent change', fmtPct(beRent))}
        ${item('Capex shock', fmtDollars(beCapex))}
    </div>`;
}

export function bindSensitivity(container, state, handlers) {
    const { onPresetChange, onComparatorChange, onHorizonChange, onRefresh } = handlers;
    const presetSel = container.querySelector('#rvs-sens-preset');
    const compSel = container.querySelector('#rvs-sens-comparator');
    const horSel = container.querySelector('#rvs-sens-horizon');
    const refreshBtn = container.querySelector('#rvs-sens-refresh');
    if (presetSel) presetSel.addEventListener('change', (e) => onPresetChange(e.target.value));
    if (compSel) compSel.addEventListener('change', (e) => onComparatorChange(e.target.value));
    if (horSel) horSel.addEventListener('change', (e) => onHorizonChange(e.target.value));
    if (refreshBtn) refreshBtn.addEventListener('click', onRefresh);
}
