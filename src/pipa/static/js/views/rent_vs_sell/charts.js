/**
 * Chart.js wrappers for the Rent vs Sell view.
 *
 * All draws destroy prior instances stored on the canvas element
 * (canvas._chartInstance) before creating a new one. No React-like
 * lifecycle needed.
 */

const COLORS = {
    sell_now: '#2563eb',
    sell_now_10y: '#2563eb',
    keep_5y: '#16a34a',
    keep_10y: '#16a34a',
    rent_then_sell: '#d97706',
};

function destroyChart(canvasEl) {
    if (!canvasEl) return;
    if (canvasEl._chartInstance) {
        canvasEl._chartInstance.destroy();
        canvasEl._chartInstance = null;
    }
}

function chosenStrategies(activeLens) {
    if (activeLens === '10y') return [['sell_now_10y', 'Sell Now'], ['keep_10y', 'Keep 10Y']];
    if (activeLens === 'rts') return [['sell_now', 'Sell Now'], ['rent_then_sell', 'Rent-Then-Sell']];
    return [['sell_now', 'Sell Now'], ['keep_5y', 'Keep 5Y'], ['rent_then_sell', 'Rent-Then-Sell']];
}

export function drawNetWorthChart(container, strategies, activeLens) {
    if (typeof Chart === 'undefined' || !container) return;
    const canvas = container.querySelector('#rvs-chart-nw');
    if (!canvas) return;
    destroyChart(canvas);

    const horizon = activeLens === '10y' ? 120 : 60;
    const labels = Array.from({ length: horizon }, (_, i) => i + 1);
    const datasets = [];
    for (const [name, label] of chosenStrategies(activeLens)) {
        const strat = strategies[name];
        if (!strat || !strat.net_worth_path) continue;
        datasets.push({
            label,
            data: strat.net_worth_path.slice(0, horizon),
            borderColor: COLORS[name] || '#6b7280',
            backgroundColor: 'transparent',
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 2,
        });
    }

    canvas._chartInstance = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
            scales: {
                x: { ticks: { maxTicksLimit: 6, font: { size: 10 } }, title: { display: true, text: 'Month', font: { size: 10 } } },
                y: { ticks: { callback: (v) => '$' + (v / 1000).toFixed(0) + 'k', font: { size: 10 } } },
            },
        },
    });
}

export function drawCashFlowChart(container, strategies, activeLens) {
    if (typeof Chart === 'undefined' || !container) return;
    const canvas = container.querySelector('#rvs-chart-cf');
    if (!canvas) return;
    destroyChart(canvas);

    const horizon = activeLens === '10y' ? 120 : 60;
    const labels = Array.from({ length: horizon }, (_, i) => i + 1);
    const datasets = [];
    const chosen = activeLens === '10y'
        ? [['sell_now_10y', 'Sell Now', '#2563eb'], ['keep_10y', 'Keep 10Y', '#16a34a']]
        : [['sell_now', 'Sell Now', '#2563eb'], ['keep_5y', 'Keep 5Y', '#16a34a']];
    for (const [name, label, color] of chosen) {
        const strat = strategies[name];
        if (!strat || !strat.monthly_cashflow_path) continue;
        datasets.push({
            label,
            data: strat.monthly_cashflow_path.slice(0, horizon),
            borderColor: color,
            backgroundColor: color + '22',
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 1.5,
        });
    }
    canvas._chartInstance = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
            scales: {
                x: { ticks: { maxTicksLimit: 6, font: { size: 10 } } },
                y: { ticks: { callback: (v) => '$' + v.toFixed(0), font: { size: 10 } } },
            },
        },
    });
}

/**
 * Horizontal waterfall bar chart for the 18-bucket StrategyDriverBridge.
 *
 * `bridge` is the driver_bridge_vs_sell dict. `comparisonLabel` drives
 * the chart title. Positive bars (green) push toward "keep wins";
 * negative bars (red) push toward "sell wins".
 *
 * If the engine ever drops a bucket key, we console.warn so the drift
 * is visible during dev — without failing the user-facing render.
 */
export function drawDriverBridge(container, bridge, comparisonLabel) {
    if (typeof Chart === 'undefined' || !container || !bridge) return;
    const canvas = container.querySelector('#rvs-chart-bridge');
    if (!canvas) return;
    destroyChart(canvas);

    const order = [
        ['current_home_appreciation_effect', 'Appreciation'],
        ['current_home_principal_paydown', 'Principal paydown'],
        ['rental_cashflow_after_tax', 'Rental cashflow (after tax)'],
        ['vacancy_and_bad_debt_drag', 'Vacancy + bad debt'],
        ['leasing_and_turnover_drag', 'Leasing + turnover'],
        ['property_management_drag', 'Mgmt fee'],
        ['routine_maintenance_drag', 'Routine maintenance'],
        ['capex_drag_current_home', 'Capex (current)'],
        ['capex_drag_new_home', 'Capex (new)'],
        ['ownership_cost_growth_effect', 'Ownership cost growth'],
        ['extra_new_home_interest_cost', 'Extra new-home interest'],
        ['trapped_equity_redeployment_benefit', 'Trapped equity redeployment'],
        ['sale_tax_difference', 'Sale tax difference'],
        ['future_sale_friction_difference', 'Future sale friction'],
        ['reinvestment_benefit_sell_case', 'Reinvestment benefit (sell)'],
        ['refi_effect', 'Refi effect'],
        ['reserve_drag', 'Reserve drag'],
        ['residual_other', 'Residual'],
    ];

    const labels = order.map(([, label]) => label);
    const values = order.map(([key]) => {
        if (!(key in bridge)) {
            // Drift detection — fail soft but noisy in dev
            console.warn(`drawDriverBridge: missing bucket key '${key}'`);
            return 0;
        }
        return bridge[key] || 0;
    });
    // Also warn if the engine surfaced keys we don't know about
    const knownKeys = new Set(order.map(([k]) => k));
    for (const k of Object.keys(bridge)) {
        if (!knownKeys.has(k)) {
            console.warn(`drawDriverBridge: unknown bucket key '${k}' — update order[]`);
        }
    }
    const colors = values.map(v => v >= 0 ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.7)');

    canvas._chartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: comparisonLabel || 'Δ',
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: { display: !!comparisonLabel, text: comparisonLabel, font: { size: 11 } },
            },
            scales: {
                x: { ticks: { callback: (v) => '$' + (v / 1000).toFixed(0) + 'k', font: { size: 10 } } },
                y: { ticks: { font: { size: 10 } } },
            },
        },
    });
}

export function drawAllCharts(container, state) {
    if (!state.outputs) return;
    const strategies = state.outputs.strategies || {};
    drawNetWorthChart(container, strategies, state.activeLens);
    drawCashFlowChart(container, strategies, state.activeLens);
    // Driver bridge uses the selected comparison
    const selected = state.bridgeComparison || 'keep_5y';
    const strat = strategies[selected];
    const bridge = strat && strat.driver_bridge_vs_sell;
    const label = {
        keep_5y: 'Sell vs Keep 5Y',
        keep_10y: 'Sell vs Keep 10Y',
        rent_then_sell: 'Sell vs Rent-Then-Sell',
    }[selected] || '';
    drawDriverBridge(container, bridge, label);
}
