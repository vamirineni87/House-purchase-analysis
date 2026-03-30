/**
 * Condition tab — score card with progress bar, component cards grid,
 * capex forecast bars. Handles empty: "Run pipeline to analyze condition."
 */

import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const data = state.conditionData;

    if (!data) {
        container.innerHTML = `
        <div class="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
            <p class="text-gray-500 text-sm mb-3">No condition data yet. Run the pipeline first.</p>
            <p class="text-gray-400 text-xs">The pipeline will analyze roof, HVAC, water heater, electrical, and windows based on year built and any AI-extracted upgrade info.</p>
        </div>`;
        return;
    }

    const score = data.score ?? data.condition_score ?? 0;
    const capex = data.capex_forecast || {};
    const components = data.components || [];

    // Score card
    const scoreColor = score >= 70 ? 'text-green-600' : score >= 40 ? 'text-amber-600' : 'text-red-600';
    const barColor = score >= 70 ? 'bg-green-500' : score >= 40 ? 'bg-amber-500' : 'bg-red-500';

    const scoreHtml = `
    <div class="bg-white border border-gray-200 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-2">Condition Score</h3>
        <div class="flex items-center gap-4">
            <div class="text-3xl font-bold ${scoreColor}">${Number(score).toFixed(0)}/100</div>
            <div class="flex-1 bg-gray-200 rounded-full h-3">
                <div class="h-3 rounded-full ${barColor}" style="width:${Math.min(score, 100)}%"></div>
            </div>
        </div>
    </div>`;

    // Component cards
    let componentsHtml = '';
    if (components.length > 0) {
        const cards = components.map((comp, i) => {
            const type = comp.component_type || comp.type || 'unknown';
            const year = comp.estimated_install_year || comp.install_year;
            const currentYear = new Date().getFullYear();
            const age = year ? currentYear - year : null;
            const remaining = comp.remaining_life;
            const replacementCost = comp.replacement_cost;

            let ageColor = 'text-green-600';
            let statusText = 'Good condition';
            if (age && age > 15) { ageColor = 'text-red-600'; statusText = 'Replace soon'; }
            else if (age && age > 10) { ageColor = 'text-amber-600'; statusText = 'Monitor'; }

            let remainingHtml = '';
            if (remaining !== undefined && remaining !== null) {
                const rc = remaining < 3 ? 'text-red-600' : remaining < 7 ? 'text-amber-600' : 'text-green-600';
                remainingHtml = `
                <div class="flex items-center justify-between text-xs">
                    <span class="text-gray-500">Est. remaining</span>
                    <span class="font-medium ${rc}">${remaining} years</span>
                </div>`;
            }

            let costHtml = '';
            if (replacementCost) {
                costHtml = `
                <div class="flex items-center justify-between text-xs">
                    <span class="text-gray-500">Replacement</span>
                    <span class="font-medium text-gray-900">${formatCurrency(replacementCost)}</span>
                </div>`;
            }

            const source = comp.source;
            const confidence = comp.confidence;
            const sourceVariant = source === 'county' ? 'info' : source === 'listing' ? 'warning' : 'muted';
            const confVariant = confidence === 'high' ? 'success' : confidence === 'medium' ? 'warning' : 'muted';

            return `
            <div class="bg-white border border-gray-200 rounded-lg p-3">
                <div class="text-sm font-medium text-gray-900 capitalize">${escapeHtml(type.replace(/_/g, ' '))}</div>
                <div class="text-xs text-gray-500 mt-1">
                    Installed: ${year || 'unknown'} ${age !== null ? `(${age} years old)` : ''}
                </div>
                <div class="text-xs mt-1">
                    <span class="font-medium ${ageColor}">${statusText}</span>
                </div>
                <div class="space-y-1.5 mt-2">
                    ${age !== null ? `
                    <div class="flex items-center justify-between text-xs">
                        <span class="text-gray-500">Age</span>
                        <span class="font-medium ${ageColor}">${age} years</span>
                    </div>` : ''}
                    ${remainingHtml}
                    ${costHtml}
                </div>
                <div class="flex items-center gap-1.5 mt-2">
                    ${source ? renderBadge(source, sourceVariant, 'sm') : ''}
                    ${confidence ? renderBadge(confidence, confVariant, 'sm') : ''}
                </div>
            </div>`;
        }).join('');

        componentsHtml = `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-3">Components</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">${cards}</div>
        </div>`;
    }

    // Capex forecast
    let capexHtml = '';
    const capexEntries = Object.entries(capex)
        .map(([year, cost]) => ({ year: parseInt(year), cost }))
        .sort((a, b) => a.year - b.year);

    if (capexEntries.length > 0) {
        const maxCost = Math.max(...capexEntries.map(e => e.cost));
        const bars = capexEntries.map(({ year, cost }) => {
            const barColor = cost > 5000 ? 'bg-red-400' : cost > 2000 ? 'bg-amber-400' : 'bg-green-400';
            const width = maxCost > 0 ? (cost / maxCost) * 100 : 0;
            return `
            <div class="flex items-center gap-3">
                <span class="text-xs font-medium text-gray-500 w-10">${year}</span>
                <div class="flex-1 h-5 bg-gray-100 rounded relative">
                    <div class="h-full rounded ${barColor}" style="width:${width}%;min-width:${cost > 0 ? '2px' : '0'}"></div>
                </div>
                <span class="text-xs font-medium text-gray-700 w-20 text-right">${formatCurrency(cost)}</span>
            </div>`;
        }).join('');

        const total = capexEntries.reduce((sum, e) => sum + e.cost, 0);

        capexHtml = `
        <div class="bg-white border border-gray-200 rounded-lg p-4">
            <h4 class="text-sm font-semibold text-gray-700 mb-3">Capex Forecast</h4>
            <div class="space-y-2">${bars}</div>
            <div class="mt-2 pt-2 border-t border-gray-100 flex justify-between text-xs">
                <span class="text-gray-500">Total projected</span>
                <span class="font-medium text-gray-900">${formatCurrency(total)}</span>
            </div>
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${scoreHtml}
        ${componentsHtml}
        ${capexHtml}
    </div>`;
}

export function bind(container, state) {
    // Condition tab is read-only
}
