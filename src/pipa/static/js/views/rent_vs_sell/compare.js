/**
 * Rent vs Sell — dedicated compare page.
 *
 * Route: #rent-vs-sell/compare?ids=a,b,c — supports 2-4 runs.
 * Fetches all runs via POST /runs/compare and renders a diff table:
 *   run identity row → assumptions diff rows → outputs diff rows.
 */

import { api } from '../../api.js';
import { formatCurrency, escapeHtml } from '../../utils.js';

export async function loadComparePage(container) {
    const m = window.location.hash.match(/ids=([^&]+)/);
    const ids = m ? m[1].split(',').filter(Boolean) : [];
    if (ids.length < 2) {
        container.innerHTML = `
        <div class="p-6 max-w-5xl mx-auto">
            <a href="#rent-vs-sell" class="text-sm text-blue-600 hover:underline">← Back to analysis</a>
            <p class="text-gray-400 mt-4">Select 2-4 runs from the Rent vs Sell analysis page to compare.</p>
        </div>`;
        return;
    }
    container.innerHTML = `
    <div class="p-6 max-w-6xl mx-auto">
        <a href="#rent-vs-sell" class="text-sm text-blue-600 hover:underline">← Back to analysis</a>
        <h1 class="text-xl font-bold mt-2">Comparing ${ids.length} runs</h1>
        <div class="mt-4 text-sm text-gray-500">Loading…</div>
    </div>`;

    try {
        const { runs } = await api.compareRentVsSellRuns(ids);
        container.innerHTML = renderComparePage(runs);
    } catch (e) {
        container.innerHTML = `
        <div class="p-6 max-w-5xl mx-auto">
            <a href="#rent-vs-sell" class="text-sm text-blue-600 hover:underline">← Back to analysis</a>
            <p class="text-red-600 mt-4">Compare failed: ${escapeHtml(e.message)}</p>
        </div>`;
    }
}

function renderComparePage(runs) {
    const assumptionKeys = [
        ['current_home.value_today', 'Value today'],
        ['current_home.loan_balance', 'Loan balance'],
        ['current_home.monthly_rent_base', 'Base rent'],
        ['current_home.total_value_change_5y', '5Y value change'],
        ['current_home.total_rent_change_5y', '5Y rent change'],
        ['refinance.selected_path', 'Refi path'],
        ['reinvestment.invest_monthly_sell_savings', 'Reinvest savings'],
    ];
    const outputKeys = [
        ['strategies.sell_now.net_worth_end', 'Sell 5Y NW', formatCurrency],
        ['strategies.keep_5y.net_worth_end', 'Keep 5Y NW', formatCurrency],
        ['strategies.keep_10y.net_worth_end', 'Keep 10Y NW', formatCurrency],
        ['strategies.rent_then_sell.net_worth_end', 'RTS NW', formatCurrency],
        ['lean', 'Lean', String],
    ];

    const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);

    const headerHtml = `<tr class="bg-gray-50">
        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase">Field</th>
        ${runs.map(r => `<th class="px-3 py-2 text-left text-xs font-semibold text-gray-600">${escapeHtml(r.name)}</th>`).join('')}
    </tr>`;

    const renderSection = (title, keys, source) => {
        const sectionHdr = `<tr><td colspan="${runs.length + 1}" class="px-3 pt-3 pb-1 text-[10px] font-bold text-gray-500 uppercase">${escapeHtml(title)}</td></tr>`;
        const rowsHtml = keys.map(([path, label, formatter]) => {
            const baseVal = get(runs[0][source], path);
            const tds = runs.map(r => {
                const val = get(r[source], path);
                const diff = JSON.stringify(val) !== JSON.stringify(baseVal);
                let formatted;
                if (val == null) {
                    formatted = '—';
                } else if (formatter) {
                    formatted = formatter(val);
                } else if (typeof val === 'number') {
                    formatted = formatCurrency(val);
                } else {
                    formatted = String(val);
                }
                return `<td class="px-3 py-1.5 text-sm ${diff ? 'bg-amber-50 font-medium' : ''}">${escapeHtml(formatted)}</td>`;
            }).join('');
            return `<tr class="border-t border-gray-100"><td class="px-3 py-1.5 text-xs text-gray-500">${escapeHtml(label)}</td>${tds}</tr>`;
        }).join('');
        return sectionHdr + rowsHtml;
    };

    return `
    <div class="p-6 max-w-6xl mx-auto">
        <a href="#rent-vs-sell" class="text-sm text-blue-600 hover:underline">← Back to analysis</a>
        <h1 class="text-xl font-bold mt-2 mb-3">Comparing ${runs.length} runs</h1>
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead>${headerHtml}</thead>
                <tbody>
                    ${renderSection('Assumptions', assumptionKeys, 'assumptions_json')}
                    ${renderSection('Outputs', outputKeys, 'outputs_json')}
                </tbody>
            </table>
        </div>
    </div>`;
}
