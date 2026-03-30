/**
 * Summary tab — Quick Take (pursue/maybe/pass + bullets), Price Benchmarks,
 * Key Metrics grid, Next Actions card, address details.
 * Handles 5 states: never_run, loading, partial, stale, complete.
 */

import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';
import { renderMetricCard } from '../../components/metric-card.js';
import { renderPriceBenchmarks } from '../../components/price-benchmarks.js';

function pursueVariant(status) {
    switch (status) {
        case 'pursue': return 'success';
        case 'maybe':  return 'warning';
        case 'pass':   return 'critical';
        default:       return 'muted';
    }
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const { property, listingData, packet, decision, latestRun } = state;
    const ld = listingData || {};

    // Determine data state
    if (!latestRun && !packet && !ld.price) {
        container.innerHTML = `
        <div class="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
            <p class="text-gray-500 text-sm mb-2">No analysis data yet.</p>
            <p class="text-gray-400 text-xs">Run the pipeline to see the summary.</p>
        </div>`;
        return;
    }

    const listPrice = ld.price || packet?.price_view?.list_price || undefined;

    // Quick Take
    let quickTakeHtml = '';
    if (packet?.quick_take) {
        const rec = packet.quick_take.recommendation || '';
        const bullets = (packet.quick_take.bullets || []).map(b =>
            `<li class="text-sm text-gray-700 flex gap-2"><span class="text-gray-400">-</span>${escapeHtml(b)}</li>`
        ).join('');
        quickTakeHtml = `
        <div class="bg-white border border-gray-200 rounded-lg p-4">
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Quick Take</h3>
            <div class="flex items-center gap-2 mb-2">
                ${renderBadge(rec.toUpperCase(), pursueVariant(rec), 'md')}
            </div>
            <ul class="space-y-1">${bullets}</ul>
        </div>`;
    }

    // Price Benchmarks
    const benchmarksHtml = renderPriceBenchmarks(
        listPrice,
        ld.zestimate || undefined,
        ld.tax_assessed_value || ld.tax_assessed || packet?.price_view?.assessment_value || undefined,
        undefined,
        packet?.price_view?.comp_estimate || undefined
    );

    // Key Metrics
    const beds = ld.bedrooms || ld.beds || '--';
    const baths = ld.baths || ld.bathrooms || '--';
    const sqft = ld.sqft ? Number(ld.sqft).toLocaleString() : '--';
    const lot = ld.lot_sqft ? Number(ld.lot_sqft).toLocaleString() + ' sqft'
        : ld.lot_acres ? String(ld.lot_acres) + ' ac' : '--';
    const yearBuilt = ld.year_built ? String(ld.year_built) : '--';
    const hoa = (ld.hoa_monthly || ld.hoa)
        ? formatCurrency(Number(ld.hoa_monthly || ld.hoa)) + '/mo' : '--';
    const dom = ld.days_on_zillow || ld.dom || ld.days_on_market;
    const cdom = ld.cdom || ld.cumulative_dom;

    const metricsHtml = `
    <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-3">Key Metrics</h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            ${renderMetricCard('Beds', String(beds))}
            ${renderMetricCard('Baths', String(baths))}
            ${renderMetricCard('Sqft', sqft)}
            ${renderMetricCard('Lot', lot)}
            ${renderMetricCard('Year Built', yearBuilt)}
            ${renderMetricCard('HOA', hoa)}
            ${renderMetricCard('DOM', dom !== undefined ? String(dom) : '--')}
            ${renderMetricCard('CDOM', cdom !== undefined ? String(cdom) : '--')}
        </div>
    </div>`;

    // Red flags
    let redFlagsHtml = '';
    if (packet?.hidden_cost?.unknowns && packet.hidden_cost.unknowns.length > 0) {
        const items = packet.hidden_cost.unknowns.map(item =>
            `<li class="text-sm text-red-700 flex gap-2"><span>!</span>${escapeHtml(item)}</li>`
        ).join('');
        redFlagsHtml = `
        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
            <h3 class="text-sm font-semibold text-red-700 mb-2">Red Flags</h3>
            <ul class="space-y-1">${items}</ul>
        </div>`;
    }

    // Strengths
    let strengthsHtml = '';
    if (packet?.community_view?.community_notes && packet.community_view.community_notes.length > 0) {
        const items = packet.community_view.community_notes.map(item =>
            `<li class="text-sm text-green-700 flex gap-2"><span>+</span>${escapeHtml(item)}</li>`
        ).join('');
        strengthsHtml = `
        <div class="bg-green-50 border border-green-200 rounded-lg p-4">
            <h3 class="text-sm font-semibold text-green-700 mb-2">Strengths</h3>
            <ul class="space-y-1">${items}</ul>
        </div>`;
    }

    // Next Actions
    let nextActionsHtml = '';
    const warnings = [];
    if (!listPrice) warnings.push('No list price - add one in Financial tab');
    if (!packet) warnings.push('No decision packet - run full pipeline');
    if (!ld.year_built) warnings.push('No year built data - run pipeline or check listing');
    if (latestRun) {
        const failedTasks = (latestRun.tasks || []).filter(t => t.status === 'failed');
        if (failedTasks.length > 0) {
            warnings.push(`${failedTasks.length} pipeline task(s) failed - check Pipeline tab`);
        }
    }
    if (warnings.length > 0) {
        nextActionsHtml = `
        <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <h3 class="text-sm font-semibold text-amber-700 mb-2">Next Actions</h3>
            <ul class="space-y-1">
                ${warnings.map(w => `<li class="text-sm text-amber-700 flex gap-2"><span>&rarr;</span>${escapeHtml(w)}</li>`).join('')}
            </ul>
        </div>`;
    }

    // Address & identifiers
    let addressHtml = '';
    if (property.addresses && property.addresses.length > 0) {
        const addrRows = property.addresses.map(addr => `
        <div class="flex items-center justify-between text-sm">
            <span class="text-gray-900">${escapeHtml(addr.normalized_address)}</span>
            <div class="flex gap-2">
                ${renderBadge(addr.address_type, 'muted')}
                ${addr.is_current ? renderBadge('current', 'success') : ''}
            </div>
        </div>`).join('');

        let parcelRows = '';
        if (property.parcel_identifiers && property.parcel_identifiers.length > 0) {
            parcelRows = `
            <div class="mt-3 pt-3 border-t border-gray-100 space-y-2">
                ${property.parcel_identifiers.map(pid => `
                <div class="flex items-center justify-between text-sm">
                    <span class="text-gray-900 font-mono">${escapeHtml(pid.identifier_value)}</span>
                    <div class="flex gap-2">
                        ${renderBadge(pid.identifier_type, 'muted')}
                        ${renderBadge(pid.county, 'info')}
                    </div>
                </div>`).join('')}
            </div>`;
        }

        addressHtml = `
        <div class="bg-white border border-gray-200 rounded-lg p-4">
            <h3 class="text-sm font-semibold text-gray-700 mb-3">Address & Identifiers</h3>
            <div class="space-y-2">${addrRows}</div>
            ${parcelRows}
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${quickTakeHtml}
        ${benchmarksHtml}
        ${metricsHtml}
        ${redFlagsHtml}
        ${strengthsHtml}
        ${nextActionsHtml}
        ${addressHtml}
    </div>`;
}

export function bind(container, state) {
    // Summary tab is mostly read-only, no event listeners needed.
}
