/**
 * Compact sticky header for property detail scroll page.
 *
 * Merges: address, price, pursue badge, pipeline status pill,
 * county, type, source, last refresh, action buttons, stage selector.
 */

import { formatCurrency, formatDate, escapeHtml } from '../../utils.js';
import { renderBadge, stageBadgeVariant, runStatusBadgeVariant } from '../../components/badge.js';
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
 * Render the compact sticky header.
 * @param {object} state - Full page state
 * @returns {string} HTML
 */
export function renderHeader(state) {
    const { property, listingData, watchEntry, latestRun, decision, packet, actionLoading, countyData } = state;
    const ld = listingData || {};

    // Address
    const currentAddr = (property?.addresses || []).find(a => a.is_current && a.address_type === 'situs');
    const address = currentAddr?.normalized_address || property?.address || 'No address';
    const county = currentAddr?.county || property?.county || '';

    // Prices
    const listPrice = ld.price || packet?.price_view?.list_price || null;

    // County assessed value (latest assessment total_value)
    const assessments = countyData?.assessments || [];
    const countyAssessed = assessments.length > 0 ? assessments[0]?.total_value : null;
    // County +8% (Loudoun assessment ratio is ~92% of market)
    const countyPlus8 = countyAssessed ? Math.round(countyAssessed * 1.08) : null;

    // Zestimate
    const zestimate = ld.zestimate || null;

    // Price display: Listed | County+8% | Zestimate
    const priceItems = [];
    if (listPrice) priceItems.push(`<span class="text-lg font-bold text-gray-900">${formatCurrency(listPrice)}</span><span class="text-xs text-gray-400 ml-0.5">listed</span>`);
    if (countyPlus8) priceItems.push(`<span class="text-sm font-semibold text-gray-700">${formatCurrency(countyPlus8)}</span><span class="text-xs text-gray-400 ml-0.5">county+8%</span>`);
    if (zestimate) priceItems.push(`<span class="text-sm font-semibold text-gray-700">${formatCurrency(zestimate)}</span><span class="text-xs text-gray-400 ml-0.5">zest</span>`);
    const priceHtml = priceItems.length > 0
        ? priceItems.join('<span class="text-gray-300 mx-1.5">|</span>')
        : '';

    // Pursue signal
    let pursueHtml = '';
    if (decision?.decision_status) {
        const label = decision.decision_status.charAt(0).toUpperCase() + decision.decision_status.slice(1);
        pursueHtml = renderBadge(label, pursueVariant(decision.decision_status), 'sm');
    }

    // Pipeline status pill
    let pipelinePill = '';
    if (latestRun) {
        const s = latestRun.status || 'unknown';
        pipelinePill = renderBadge(s, runStatusBadgeVariant(s), 'sm');
    }

    // Metadata line
    const countyLabel = county ? county.charAt(0).toUpperCase() + county.slice(1) + ' County' : '';
    const propType = (property?.property_type || '').replace(/_/g, ' ');
    const source = ld.source || ld.listing_source || ld._source || '';
    const lastRefresh = latestRun?.created_at;

    const metaParts = [countyLabel, propType, source].filter(Boolean);
    const metaHtml = metaParts.map(m => `<span class="capitalize">${escapeHtml(m)}</span>`).join('<span class="text-gray-300">|</span>');
    const refreshHtml = lastRefresh ? `<span>Last run: ${formatDate(lastRefresh)}</span>` : '';

    // Action buttons (compact)
    const anyLoading = actionLoading !== null;
    const btn = (id, label) => {
        const loading = actionLoading === id;
        const disabled = anyLoading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-200';
        const spinner = loading ? '<span class="animate-spin inline-block w-3 h-3 border border-gray-400 border-t-transparent rounded-full mr-1"></span>' : '';
        return `<button id="${id}" class="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 border border-gray-200 rounded-md ${disabled} transition-colors" ${anyLoading ? 'disabled' : ''}>${spinner}${escapeHtml(label)}</button>`;
    };

    // Stage selector
    const stageOptions = STAGES.map(s => {
        const selected = watchEntry?.stage === s ? 'selected' : '';
        return `<option value="${s}" ${selected}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`;
    }).join('');

    return `
<div id="detail-header" class="bg-white border-b border-gray-200 py-3">
  <div class="flex items-start justify-between gap-4 flex-wrap">
    <div class="min-w-0">
      <div class="flex items-center gap-3 flex-wrap">
        <a href="#properties" class="text-gray-400 hover:text-blue-600">&larr;</a>
        <h1 class="text-xl font-bold text-gray-900">${escapeHtml(address)}</h1>
      </div>
      <div class="flex items-center gap-3 mt-1 text-sm text-gray-600 flex-wrap">
        ${priceHtml}
        ${pursueHtml}
        ${pipelinePill}
        ${metaHtml}
        ${refreshHtml}
      </div>
    </div>
    <div class="flex items-center gap-2 flex-wrap flex-shrink-0">
      ${btn('action-run-pipeline', 'Pipeline')}
      ${btn('action-refresh-listing', 'Listing')}
      ${btn('action-refresh-county', 'County')}
      ${btn('action-deep-comp', 'Deep Comp')}
      ${btn('action-rerun-ai', 'AI')}
      <select id="stage-select" class="text-xs border border-gray-300 rounded px-2 py-1.5">
        <option value="" disabled ${!watchEntry ? 'selected' : ''}>${watchEntry ? 'Stage...' : 'Watchlist'}</option>
        ${stageOptions}
      </select>
    </div>
  </div>
</div>`;
}

/**
 * Bind header events: action buttons + stage selector.
 */
export function bindHeader(container, state, handlers) {
    const { onAction, onStageChange } = handlers;

    // Action buttons
    const actionIds = [
        'action-run-pipeline', 'action-refresh-listing', 'action-refresh-county',
        'action-deep-comp', 'action-rerun-ai',
    ];
    for (const id of actionIds) {
        const btn = container.querySelector(`#${id}`);
        if (btn) {
            btn.addEventListener('click', () => onAction(id));
        }
    }

    // Stage selector
    const select = container.querySelector('#stage-select');
    if (select) {
        select.addEventListener('change', () => {
            if (select.value) onStageChange(select.value);
        });
    }
}
