/**
 * Rent vs Sell — results panel.
 *
 * Top-line metric cards, strategy comparison table, landlord drag summary,
 * driver bridge with comparison dropdown, warning badges, and the chart
 * canvases. The heatmap is rendered by sensitivity.js and spliced below.
 */

import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderSensitivity } from './sensitivity.js';

// Human-readable labels for warning codes surfaced by the engine and
// derived heuristics from the plan's warning-badge list.
const WARNING_LABELS = {
    negative_sell_proceeds: ['Negative sell proceeds', 'red'],
    tiny_sell_proceeds: ['Tiny sell proceeds', 'amber'],
    negative_rental_cashflow: ['Negative rental cashflow', 'amber'],
    high_early_capex: ['Capex > $20k in first 2 years', 'amber'],
    suspended_losses_not_released: ['Suspended losses not released', 'amber'],
};

function renderWarningBadge(variant, text) {
    const color = variant === 'red'
        ? 'bg-red-50 text-red-700 border-red-200'
        : 'bg-amber-50 text-amber-800 border-amber-200';
    return `<span class="text-[10px] px-1.5 py-0.5 rounded border ${color}">${escapeHtml(text)}</span>`;
}

function collectWarnings(state) {
    const outputs = state.outputs;
    if (!outputs) return [];
    const warnings = new Set();

    // Engine-emitted per-strategy warnings
    for (const strat of Object.values(outputs.strategies || {})) {
        for (const w of strat.warnings || []) {
            warnings.add(w);
        }
    }

    // Derived heuristics from plan spec (evaluated frontend-side).
    // Guard every nested access because `state.inputs` can arrive here with
    // a malformed / partially-populated assumptions_json (e.g. a saved run
    // loaded from an old schema version).
    const tl = outputs.top_line || {};
    const inputs = state.inputs || {};
    const ch = inputs.current_home || {};
    const nhd = inputs.new_home_drag || {};
    const reinv = inputs.reinvestment || {};

    // §121 window closing within the horizon
    if (tl.section_121_window_status === 'closing') {
        warnings.add('§121 window closing soon');
    }
    if (tl.section_121_window_status === 'closed') {
        warnings.add('§121 window closed');
    }

    // Depreciation recapture > $20k in any strategy
    for (const strat of Object.values(outputs.strategies || {})) {
        const recap = strat.sale_tax_model && strat.sale_tax_model.depreciation_recap_bucket;
        if (recap && recap > 20000) {
            warnings.add('Depreciation recapture > $20k');
            break;
        }
    }

    // Suspended loss accumulation
    for (const strat of Object.values(outputs.strategies || {})) {
        const years = strat.annual_tax_model || [];
        const susp = years.reduce((s, y) => s + (y.suspended_loss_created || 0), 0);
        if (susp > 10000) {
            warnings.add('Suspended passive losses accruing');
            break;
        }
    }

    // New-home maintenance omitted (decoupled from active lens — this is
    // about the input itself, not which tab the user happens to be viewing)
    if ((nhd.new_home_maintenance_pct_of_home_value_annual ?? 0) === 0) {
        warnings.add('New-home maintenance set to 0 (10Y comparisons will be unfair)');
    }

    // Reinvestment disabled — same deal, input-level not lens-level
    if (!reinv.invest_monthly_sell_savings) {
        warnings.add('Sell-case reinvestment disabled (10Y comparisons will be unfair)');
    }

    // Future sale friction much larger than sell-now friction
    const nowPct = ch.sell_cost_pct_now ?? 0.07;
    const futPct = ch.current_home_sell_cost_pct_future ?? nowPct;
    if (futPct > nowPct + 0.01) {
        warnings.add('Future sale friction materially higher than sell-now');
    }

    // High vacancy + turnover combo
    const vac = ch.vacancy_months_per_year_base ?? 0;
    const turn = ch.turnover_frequency_months ?? 24;
    if (vac > 1.5 && turn < 18) {
        warnings.add('High vacancy + turnover combo');
    }

    return Array.from(warnings);
}

export function renderResultsPanel(state) {
    const outputs = state.outputs;
    if (!outputs) {
        return '<div class="text-sm text-gray-400">Waiting for first compute…</div>';
    }
    return [
        renderWarningStrip(state),
        renderTopLine(outputs, state),
        renderStrategyTable(outputs, state),
        renderLandlordDragSummary(outputs),
        renderDriverBridge(outputs, state),
        renderChartsMarkup(),
        renderSensitivity(state),
        renderFormulaNotesPanel(),
    ].join('');
}

function renderWarningStrip(state) {
    const warnings = collectWarnings(state);
    if (warnings.length === 0) return '';
    const badges = warnings.map(w => {
        const meta = WARNING_LABELS[w];
        if (meta) {
            return renderWarningBadge(meta[1], meta[0]);
        }
        return renderWarningBadge('amber', w);
    }).join(' ');
    return `<div class="mb-3 flex flex-wrap gap-1">${badges}</div>`;
}

function renderTopLine(outputs, state) {
    const tl = outputs.top_line || {};
    const lean = outputs.lean || 'too_close';
    const leanLabel = {
        leans_sell: 'Leans Sell',
        leans_keep: 'Leans Keep',
        too_close: 'Too Close to Call',
    }[lean] || lean;
    const leanColor = {
        leans_sell: 'bg-amber-50 text-amber-800 border-amber-200',
        leans_keep: 'bg-green-50 text-green-800 border-green-200',
        too_close: 'bg-gray-50 text-gray-700 border-gray-200',
    }[lean] || 'bg-gray-50 text-gray-700 border-gray-200';

    const card = (label, value, sub = '') => `
        <div class="bg-white border border-gray-200 rounded-lg p-3">
            <div class="text-xs text-gray-500">${escapeHtml(label)}</div>
            <div class="text-lg font-bold mt-0.5">${value}</div>
            ${sub ? `<div class="text-[10px] text-gray-400">${escapeHtml(sub)}</div>` : ''}
        </div>`;

    const windowLabel = {
        open: '<span class="text-green-700">Open</span>',
        closing: '<span class="text-amber-700">Closing soon</span>',
        closed: '<span class="text-red-700">Closed</span>',
    }[tl.section_121_window_status] || '<span class="text-gray-400">—</span>';

    // Lens-aware "winner NW" card — shows the better of the lens's two strategies
    let lensWinnerLabel = '';
    let lensWinnerValue = '—';
    const strat = outputs.strategies || {};
    if (state.activeLens === '5y') {
        const s = strat.sell_now?.net_worth_end;
        const k = strat.keep_5y?.net_worth_end;
        if (s != null && k != null) {
            if (k > s) { lensWinnerLabel = 'Keep 5Y'; lensWinnerValue = formatCurrency(k); }
            else { lensWinnerLabel = 'Sell Now'; lensWinnerValue = formatCurrency(s); }
        }
    } else if (state.activeLens === '10y') {
        const s = strat.sell_now_10y?.net_worth_end;
        const k = strat.keep_10y?.net_worth_end;
        if (s != null && k != null) {
            if (k > s) { lensWinnerLabel = 'Keep 10Y'; lensWinnerValue = formatCurrency(k); }
            else { lensWinnerLabel = 'Sell Now 10Y'; lensWinnerValue = formatCurrency(s); }
        }
    } else {
        const s = strat.sell_now?.net_worth_end;
        const r = strat.rent_then_sell?.net_worth_end;
        if (s != null && r != null) {
            if (r > s) { lensWinnerLabel = 'Rent-Then-Sell'; lensWinnerValue = formatCurrency(r); }
            else { lensWinnerLabel = 'Sell Now'; lensWinnerValue = formatCurrency(s); }
        }
    }

    // Breakeven appreciation — lens-matched. Engine only computes 5Y and
    // 10Y breakevens; RTS doesn't have one because its horizon is user-
    // controlled via rent_then_sell_date, so the bisection bracket would be
    // ambiguous. Show "n/a" on the RTS lens.
    let be = null;
    if (state.activeLens === '5y') {
        be = tl.required_appreciation_to_breakeven_5y;
    } else if (state.activeLens === '10y') {
        be = tl.required_appreciation_to_breakeven_10y;
    }
    const beDisplay = (be == null)
        ? 'n/a'
        : `${(be * 100).toFixed(1)}%`;

    return `
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
        <div class="bg-white border rounded-lg p-3 ${leanColor}">
            <div class="text-xs opacity-70">Verdict</div>
            <div class="text-lg font-bold mt-0.5">${escapeHtml(leanLabel)}</div>
        </div>
        ${card('Monthly Stress Δ', formatCurrency(tl.monthly_stress_delta), 'keep vs sell')}
        ${card('Net Interest Drag', formatCurrency(tl.net_interest_drag_monthly) + '/mo', 'extra new-home interest − cheap old-debt')}
        ${card(`${state.activeLens === '10y' ? '10Y' : state.activeLens === 'rts' ? 'RTS' : '5Y'} NW Winner`, lensWinnerValue, lensWinnerLabel)}
        ${card('Breakeven Appreciation', beDisplay, 'total horizon % for keep to win')}
        <div class="bg-white border border-gray-200 rounded-lg p-3">
            <div class="text-xs text-gray-500">§121 Window</div>
            <div class="text-lg font-bold mt-0.5">${windowLabel}</div>
        </div>
    </div>`;
}

function renderStrategyTable(outputs, state) {
    const s = outputs.strategies || {};
    const lens = state.activeLens;
    const cols = lens === '5y'
        ? [['sell_now', 'Sell Now (5Y)'], ['keep_5y', 'Keep 5Y'], ['rent_then_sell', 'Rent-Then-Sell']]
        : lens === '10y'
            ? [['sell_now_10y', 'Sell Now (10Y)'], ['keep_10y', 'Keep 10Y']]
            : [['sell_now', 'Sell Now'], ['rent_then_sell', 'Rent-Then-Sell']];

    const rows = [
        ['net_worth_end', 'Net Worth at Horizon', formatCurrency],
        ['monthly_stress', 'Monthly Stress', formatCurrency],
        ['monthly_stress_delta_vs_sell', 'Monthly Δ vs Sell', formatCurrency],
    ];

    let saleTaxRow = '<tr><td class="px-3 py-2 text-xs text-gray-500">Tax at Sale</td>';
    cols.forEach(([name]) => {
        const strat = s[name] || {};
        const t = strat.sale_tax_model?.estimated_sale_tax;
        saleTaxRow += `<td class="px-3 py-2 text-sm font-medium text-right">${t != null ? formatCurrency(t) : '—'}</td>`;
    });
    saleTaxRow += '</tr>';

    const headerHtml = `<tr class="bg-gray-50">
        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase">Metric</th>
        ${cols.map(([, label]) => `<th class="px-3 py-2 text-right text-xs font-semibold text-gray-600 uppercase">${escapeHtml(label)}</th>`).join('')}
    </tr>`;

    const bodyHtml = rows.map(([key, label, fmt]) => {
        let tds = '';
        cols.forEach(([name]) => {
            const val = s[name]?.[key];
            tds += `<td class="px-3 py-2 text-sm font-medium text-right">${val != null ? fmt(val) : '—'}</td>`;
        });
        return `<tr class="border-t border-gray-100"><td class="px-3 py-2 text-xs text-gray-500">${escapeHtml(label)}</td>${tds}</tr>`;
    }).join('') + saleTaxRow;

    return `
    <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-4">
        <div class="px-3 py-2 border-b bg-gray-50 text-xs font-semibold text-gray-700 uppercase">Strategy comparison</div>
        <table class="w-full">
            <thead>${headerHtml}</thead>
            <tbody>${bodyHtml}</tbody>
        </table>
    </div>`;
}

function renderLandlordDragSummary(outputs) {
    const keep = outputs.strategies?.keep_5y;
    if (!keep || !keep.rental_ops_model || !keep.rental_ops_model.length) return '';
    const ops = keep.rental_ops_model;
    const mc = keep.maintenance_capex_model || [];
    const sum = (arr, key) => arr.reduce((s, y) => s + (y[key] || 0), 0);
    const vacancy = sum(ops, 'vacancy_loss') + sum(ops, 'bad_debt_loss');
    const leasing = sum(ops, 'leasing_fee') + sum(ops, 'turnover_cost');
    const mgmt = sum(ops, 'management_fee');
    const maint = sum(mc, 'routine_maintenance');
    const capex = sum(mc, 'explicit_capex_total');
    const total = vacancy + leasing + mgmt + maint + capex;

    const item = (label, value) => `
        <div class="px-3 py-2 border-r border-gray-100 last:border-r-0">
            <div class="text-xs text-gray-500">${escapeHtml(label)}</div>
            <div class="text-sm font-semibold text-gray-900">${formatCurrency(value)}</div>
        </div>`;

    return `
    <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-4">
        <div class="px-3 py-2 border-b bg-gray-50 text-xs font-semibold text-gray-700 uppercase">Landlord drag (5Y)</div>
        <div class="grid grid-cols-2 md:grid-cols-6 divide-x divide-gray-100">
            ${item('Vacancy + bad debt', vacancy)}
            ${item('Leasing + turnover', leasing)}
            ${item('Management', mgmt)}
            ${item('Routine maintenance', maint)}
            ${item('Capex', capex)}
            ${item('Total', total)}
        </div>
    </div>`;
}

function renderDriverBridge(outputs, state) {
    const strategies = outputs.strategies || {};
    const selected = state.bridgeComparison || 'keep_5y';
    const strat = strategies[selected];
    if (!strat || !strat.driver_bridge_vs_sell) return '';
    const sellKey = selected === 'keep_10y' ? 'sell_now_10y' : 'sell_now';
    const sell = strategies[sellKey];
    if (!sell) return '';
    const delta = (strat.net_worth_end || 0) - (sell.net_worth_end || 0);
    const deltaColor = delta > 0 ? 'text-green-700' : 'text-red-700';

    const dropdownOptions = [
        ['keep_5y', 'Sell vs Keep 5Y'],
        ['keep_10y', 'Sell vs Keep 10Y'],
        ['rent_then_sell', 'Sell vs Rent-Then-Sell'],
    ];

    return `
    <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-4">
        <div class="px-3 py-2 border-b bg-gray-50 flex items-center justify-between">
            <div class="text-xs font-semibold text-gray-700 uppercase">Why one strategy wins</div>
            <div class="flex items-center gap-2">
                <select id="rvs-bridge-select" class="text-xs border border-gray-300 rounded px-2 py-1">
                    ${dropdownOptions.map(([k, l]) => `<option value="${k}" ${k === selected ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}
                </select>
                <span class="text-xs font-mono ${deltaColor}">Δ: ${formatCurrency(delta)}</span>
            </div>
        </div>
        <div class="p-3">
            <div class="relative w-full" style="height: 360px">
                <canvas id="rvs-chart-bridge"></canvas>
            </div>
        </div>
    </div>`;
}

function renderChartsMarkup() {
    // Each canvas is wrapped in a position-relative box with an EXPLICIT
    // pixel height. Chart.js's responsive+maintainAspectRatio=false mode
    // reads the parent's box; without a stable height it feedback-loops
    // on every destroy/recreate and the charts grow exponentially.
    return `
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <div class="bg-white border border-gray-200 rounded-lg p-3">
            <div class="text-xs font-semibold text-gray-700 uppercase mb-2">Net worth over time</div>
            <div class="relative w-full" style="height: 220px">
                <canvas id="rvs-chart-nw"></canvas>
            </div>
        </div>
        <div class="bg-white border border-gray-200 rounded-lg p-3">
            <div class="text-xs font-semibold text-gray-700 uppercase mb-2">Monthly cash flow</div>
            <div class="relative w-full" style="height: 220px">
                <canvas id="rvs-chart-cf"></canvas>
            </div>
        </div>
    </div>`;
}

function renderFormulaNotesPanel() {
    return `
    <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
        <div class="text-xs font-semibold text-blue-900 uppercase mb-1">Formula notes — planning math, not tax advice</div>
        <ul class="text-[11px] text-blue-800 space-y-0.5 list-disc list-inside">
            <li><strong>Growth inputs</strong> are total horizon changes (e.g. −10%), spread linearly over months, not annual CAGR.</li>
            <li><strong>Sell case</strong> uses base 20% down + net-after-tax proceeds (lands near 53.4% with default assumptions).</li>
            <li><strong>Section 121</strong> excludes up to $500k MFJ if the 2-of-5-year test still holds; sale within 36 months of move-out keeps the window open.</li>
            <li><strong>Depreciation</strong> uses min(adjusted basis, FMV at conversion) × building pct / 27.5, mid-month convention.</li>
            <li><strong>Passive losses</strong> at MAGI > $150k are suspended (not offsetting W-2 immediately); optionally released at sale.</li>
            <li><strong>Sell-case reinvestment</strong> compounds monthly carrying-cost savings at the user-chosen return for long-horizon fairness.</li>
            <li>Driver bridge buckets sum to the net Δ within $1 (residual absorbed in <code>residual_other</code>).</li>
        </ul>
    </div>`;
}

export function bindResultsPanel(container, state, handlers) {
    const { onBridgeCompareChange } = handlers;
    const bridgeSelect = container.querySelector('#rvs-bridge-select');
    if (bridgeSelect) {
        bridgeSelect.addEventListener('change', (e) => onBridgeCompareChange(e.target.value));
    }
}
