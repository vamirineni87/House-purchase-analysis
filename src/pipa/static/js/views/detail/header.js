/**
 * Property detail header — address, list price, county badge, property type,
 * pursue signal badge, stage dropdown, source badge, last refresh time.
 */

import { formatCurrency, formatDate, escapeHtml } from '../../utils.js';
import { renderBadge, stageBadgeVariant } from '../../components/badge.js';
import { STAGES } from '../../constants.js';

function pursueVariant(status) {
    switch (status) {
        case 'pursue': return 'success';
        case 'maybe':  return 'warning';
        case 'pass':   return 'critical';
        default:       return 'muted';
    }
}

/**
 * Render the property detail header block.
 */
export function renderHeader(property, listingData, watchEntry, latestRun, decision, packet) {
    const ld = listingData || {};

    // Find current situs address
    const currentAddr = (property.addresses || []).find(a => a.is_current && a.address_type === 'situs');
    const address = currentAddr?.normalized_address || property.address || 'No address';
    const county = currentAddr?.county || property.county || '';

    // List price
    const listPrice = ld.price || packet?.price_view?.list_price || null;
    const priceHtml = listPrice
        ? `<span class="text-lg font-bold text-gray-900">${formatCurrency(listPrice)}</span>`
        : '';

    // Pursue signal
    let pursueHtml = '';
    if (decision) {
        const label = decision.decision_status.charAt(0).toUpperCase() + decision.decision_status.slice(1);
        pursueHtml = renderBadge(label, pursueVariant(decision.decision_status), 'md');
    }

    // County badge
    const countyHtml = county
        ? renderBadge(county.charAt(0).toUpperCase() + county.slice(1) + ' County', 'info')
        : '';

    // Property type
    const propType = (property.property_type || '').replace(/_/g, ' ');

    // Source badge (Zillow/Redfin)
    const source = ld.source || ld.listing_source || '';
    const sourceHtml = source
        ? renderBadge(source, 'muted', 'sm')
        : '';

    // Last refresh
    const lastRefresh = latestRun?.created_at;
    const refreshHtml = lastRefresh
        ? `<span class="text-xs text-gray-400">Last run: ${formatDate(lastRefresh)}</span>`
        : '';

    // Stage selector
    const stageOptions = STAGES.map(s => {
        const selected = watchEntry?.stage === s ? 'selected' : '';
        return `<option value="${s}" ${selected}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`;
    }).join('');

    const currentStageBadge = watchEntry
        ? renderBadge(watchEntry.stage, stageBadgeVariant(watchEntry.stage), 'md')
        : '';

    return `
    <div class="mb-4">
        <div class="flex items-start justify-between flex-wrap gap-3">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">${escapeHtml(address)}</h1>
                <div class="flex items-center gap-3 mt-1 text-sm text-gray-500 flex-wrap">
                    ${priceHtml}
                    ${pursueHtml}
                    ${countyHtml}
                    <span class="capitalize">${escapeHtml(propType)}</span>
                    ${sourceHtml}
                    ${refreshHtml}
                </div>
            </div>
            <div class="flex items-center gap-2">
                ${currentStageBadge}
                <select id="stage-select" class="text-sm border border-gray-300 rounded px-2 py-1">
                    <option value="" disabled ${!watchEntry ? 'selected' : ''}>${watchEntry ? 'Move to...' : 'Add to watchlist'}</option>
                    ${stageOptions}
                </select>
            </div>
        </div>
    </div>`;
}
