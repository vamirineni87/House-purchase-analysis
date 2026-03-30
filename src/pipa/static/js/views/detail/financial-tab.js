/**
 * Financial tab — input form (list price, HOA), "Run Analysis" button.
 * Results: scenario comparison table, payment breakdown, cash at closing, closing costs.
 * Handles empty: "Enter list price and run analysis."
 */

import { api } from '../../api.js';
import { formatCurrency, escapeHtml } from '../../utils.js';
import { showToast } from '../../toast.js';

let _local = {
    listPrice: '',
    hoaMonthly: '',
    result: null,
    loading: false,
    error: null,
};

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const { result, loading, error, listPrice, hoaMonthly } = _local;

    const errorHtml = error
        ? `<div class="text-sm text-red-600 bg-red-50 rounded px-3 py-2">${escapeHtml(error)}</div>`
        : '';

    // Input form
    const formHtml = `
    <div class="bg-gray-50 rounded-lg p-4 flex flex-wrap gap-4 items-end">
        <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">List Price</label>
            <input id="fin-list-price" type="number" value="${escapeHtml(listPrice)}" placeholder="650000" class="border border-gray-300 rounded px-3 py-2 text-sm w-40" />
        </div>
        <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">HOA/month</label>
            <input id="fin-hoa" type="number" value="${escapeHtml(hoaMonthly)}" placeholder="0" class="border border-gray-300 rounded px-3 py-2 text-sm w-28" />
        </div>
        <button id="fin-run-btn" ${loading ? 'disabled' : ''} class="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50">
            ${loading ? 'Running...' : 'Run Analysis'}
        </button>
    </div>`;

    let resultsHtml = '';
    if (result) {
        // Scenario table
        const scenarioRows = (result.scenarios || []).map(s => {
            const bd = result.payment_breakdowns ? result.payment_breakdowns[s.name] : null;
            const fmtPct = (n) => `${(n * 100).toFixed(1)}%`;
            return `
            <tr class="hover:bg-gray-50">
                <td class="px-3 py-2 font-medium text-gray-900">${escapeHtml(s.name)}</td>
                <td class="px-3 py-2 text-right text-gray-700">${formatCurrency(s.down_payment)} <span class="text-gray-400">(${fmtPct(s.down_payment_pct)})</span></td>
                <td class="px-3 py-2 text-right text-gray-700">${formatCurrency(s.loan_amount)}</td>
                <td class="px-3 py-2 text-right text-gray-700">${s.interest_rate.toFixed(2)}%</td>
                <td class="px-3 py-2 text-right text-gray-700">${s.term_years}yr</td>
                <td class="px-3 py-2 text-right font-semibold text-gray-900">${bd ? formatCurrency(bd.total) : '--'}</td>
            </tr>`;
        }).join('');

        const scenarioTable = `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Loan Scenarios</h3>
            <div class="overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="bg-gray-50 text-gray-600 text-left">
                            <th class="px-3 py-2 font-medium">Scenario</th>
                            <th class="px-3 py-2 font-medium text-right">Down Payment</th>
                            <th class="px-3 py-2 font-medium text-right">Loan Amount</th>
                            <th class="px-3 py-2 font-medium text-right">Rate</th>
                            <th class="px-3 py-2 font-medium text-right">Term</th>
                            <th class="px-3 py-2 font-medium text-right">Monthly Total</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">${scenarioRows}</tbody>
                </table>
            </div>
        </div>`;

        // Payment breakdowns
        const breakdownCards = (result.scenarios || []).map(s => {
            const bd = result.payment_breakdowns ? result.payment_breakdowns[s.name] : null;
            if (!bd) return '';

            const items = [
                { label: 'Principal', value: bd.principal, color: 'bg-blue-500' },
                { label: 'Interest', value: bd.interest, color: 'bg-indigo-400' },
                { label: 'Property Tax', value: bd.property_tax, color: 'bg-amber-400' },
                { label: 'Insurance', value: bd.homeowners_insurance, color: 'bg-green-400' },
                { label: 'PMI', value: bd.pmi, color: 'bg-red-400' },
                { label: 'HOA', value: bd.hoa, color: 'bg-purple-400' },
            ].filter(item => item.value > 0);

            const barSegments = items.map(item =>
                `<div class="${item.color}" style="width:${(item.value / bd.total) * 100}%" title="${item.label}: ${formatCurrency(item.value)}"></div>`
            ).join('');

            const legendItems = items.map(item => `
            <div class="flex items-center gap-1.5">
                <div class="w-2 h-2 rounded-full ${item.color}"></div>
                <span class="text-gray-600">${item.label}</span>
                <span class="ml-auto text-gray-900 font-medium">${formatCurrency(item.value)}</span>
            </div>`).join('');

            return `
            <div class="bg-white border border-gray-200 rounded-lg p-4">
                <div class="flex justify-between items-center mb-3">
                    <h4 class="text-sm font-medium text-gray-900">${escapeHtml(s.name)}</h4>
                    <span class="text-lg font-bold text-gray-900">${formatCurrency(bd.total)}/mo</span>
                </div>
                <div class="flex h-3 rounded-full overflow-hidden mb-3">${barSegments}</div>
                <div class="grid grid-cols-2 gap-1 text-xs">${legendItems}</div>
            </div>`;
        }).join('');

        const breakdownSection = breakdownCards ? `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Monthly Payment Breakdown</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">${breakdownCards}</div>
        </div>` : '';

        // Cash at closing
        let cashSection = '';
        if (result.cash_needed_at_closing) {
            const cashCards = Object.entries(result.cash_needed_at_closing).map(([name, amount]) => `
            <div class="bg-white border border-gray-200 rounded-lg p-4 text-center">
                <div class="text-xs text-gray-500 mb-1">${escapeHtml(name)}</div>
                <div class="text-lg font-bold text-gray-900">${formatCurrency(amount)}</div>
            </div>`).join('');

            cashSection = `
            <div>
                <h3 class="text-sm font-semibold text-gray-700 mb-2">Cash Needed at Closing</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3">${cashCards}</div>
            </div>`;
        }

        // Closing costs
        let closingCostsSection = '';
        if (result.closing_costs) {
            const cc = result.closing_costs;
            const rows = [
                ['Loan origination', cc.loan_origination],
                ['Appraisal fee', cc.appraisal_fee],
                ['Title insurance', cc.title_insurance],
                ['Escrow fees', cc.escrow_fees],
                ['Recording fees', cc.recording_fees],
                ['Prepaid taxes', cc.prepaid_taxes],
                ['Prepaid insurance', cc.prepaid_insurance],
                ['Inspection fees', cc.inspection_fees],
                ['Other', cc.other],
            ].filter(([, v]) => v != null).map(([label, val]) =>
                `<div class="text-gray-600">${label}</div><div class="text-right">${formatCurrency(val)}</div>`
            ).join('');

            closingCostsSection = `
            <div>
                <h3 class="text-sm font-semibold text-gray-700 mb-2">Estimated Closing Costs</h3>
                <div class="bg-white border border-gray-200 rounded-lg p-4">
                    <div class="grid grid-cols-2 gap-2 text-sm">
                        ${rows}
                        <div class="font-semibold text-gray-900 border-t pt-2">Total</div>
                        <div class="font-semibold text-right border-t pt-2">${formatCurrency(cc.total)}</div>
                    </div>
                </div>
            </div>`;
        }

        resultsHtml = `${scenarioTable}${breakdownSection}${cashSection}${closingCostsSection}`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${formHtml}
        ${errorHtml}
        ${resultsHtml || (!_local.result ? '<div class="text-sm text-gray-500 text-center py-8 bg-gray-50 rounded-lg">Enter list price and run analysis to see mortgage scenarios.</div>' : '')}
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container, state) {
    const priceInput = container.querySelector('#fin-list-price');
    const hoaInput = container.querySelector('#fin-hoa');
    const runBtn = container.querySelector('#fin-run-btn');

    if (priceInput) {
        priceInput.addEventListener('input', () => { _local.listPrice = priceInput.value; });
    }
    if (hoaInput) {
        hoaInput.addEventListener('input', () => { _local.hoaMonthly = hoaInput.value; });
    }

    if (runBtn) {
        runBtn.addEventListener('click', async () => {
            const price = parseFloat(_local.listPrice);
            if (isNaN(price) || price <= 0) {
                _local.error = 'Enter a valid list price.';
                render(container, state);
                bind(container, state);
                return;
            }

            _local.error = null;
            _local.loading = true;
            render(container, state);
            bind(container, state);

            try {
                const req = {
                    list_price: price,
                    hoa_monthly: parseFloat(_local.hoaMonthly) || 0,
                    down_payment_pcts: [0.1, 0.2],
                    term_years: [15, 30],
                };
                _local.result = await api.runFinancialAnalysis(state.propertyId, req);
            } catch (err) {
                _local.error = err.message || 'Analysis failed';
            } finally {
                _local.loading = false;
            }

            render(container, state);
            bind(container, state);
        });
    }
}
