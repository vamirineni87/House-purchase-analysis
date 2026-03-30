/**
 * Listing History tab — DOM/CDOM metrics, original ask, total reduction,
 * price history timeline, relist detection badge.
 */

import { formatCurrency, formatDate, escapeHtml } from '../../utils.js';
import { renderMetricCard } from '../../components/metric-card.js';
import { renderBadge } from '../../components/badge.js';

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const ld = state.listingData || {};
    const priceHistory = ld.price_history || [];
    const dom = ld.days_on_zillow || ld.dom || ld.days_on_market;
    const cdom = ld.cdom || ld.cumulative_dom;
    const originalAsk = ld.original_ask;
    const totalReduction = ld.total_reduction;
    const isRelist = ld.is_relist || (cdom && dom && cdom > dom * 1.5);

    // Metrics row
    const metricsHtml = `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${renderMetricCard('DOM', dom !== undefined ? String(dom) : '--')}
        ${renderMetricCard('CDOM', cdom !== undefined ? String(cdom) : '--')}
        ${renderMetricCard('Original List', originalAsk ? formatCurrency(Number(originalAsk)) : '--')}
        ${renderMetricCard('Total Reduction', totalReduction ? formatCurrency(Number(totalReduction)) : '--')}
    </div>`;

    // Relist detection
    let relistHtml = '';
    if (isRelist) {
        relistHtml = `
        <div class="flex items-center gap-2">
            ${renderBadge('Relist Detected', 'warning', 'md')}
            <span class="text-xs text-gray-500">CDOM significantly exceeds DOM, indicating a prior listing attempt.</span>
        </div>`;
    }

    // Price history table
    let historyHtml;
    if (priceHistory.length > 0) {
        const rows = priceHistory.map((event, i) => {
            const eventType = event.event_type || event.event || 'unknown';
            const eventVariant = eventType === 'price_change' ? 'warning'
                : eventType === 'listed' ? 'info'
                : eventType === 'sold' ? 'success' : 'muted';
            const price = event.price ? formatCurrency(Number(event.price)) : '--';
            const change = event.change_amount ? formatCurrency(Number(event.change_amount)) : '--';
            const changeClass = event.change_amount && Number(event.change_amount) < 0 ? 'text-green-600' : '';

            return `
            <tr>
                <td class="px-3 py-2">${escapeHtml(event.date || '--')}</td>
                <td class="px-3 py-2">${renderBadge(eventType.replace(/_/g, ' '), eventVariant, 'sm')}</td>
                <td class="px-3 py-2 text-right font-medium">${price}</td>
                <td class="px-3 py-2 text-right ${changeClass}">${change}</td>
            </tr>`;
        }).join('');

        historyHtml = `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Price History</h3>
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="bg-gray-50 text-gray-600 text-left">
                            <th class="px-3 py-2 font-medium">Date</th>
                            <th class="px-3 py-2 font-medium">Event</th>
                            <th class="px-3 py-2 font-medium text-right">Price</th>
                            <th class="px-3 py-2 font-medium text-right">Change</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">${rows}</tbody>
                </table>
            </div>
        </div>`;
    } else {
        historyHtml = `
        <div class="text-sm text-gray-500 text-center py-8 bg-gray-50 rounded-lg">
            No listing history data available. Run the pipeline to extract price history from the listing page.
        </div>`;
    }

    // Source info
    let sourceHtml = '';
    const source = ld.source || ld.listing_source || '';
    const listingUrl = ld.url || ld.listing_url || '';
    if (source || listingUrl) {
        sourceHtml = `
        <div class="flex items-center gap-3 text-xs text-gray-500">
            ${source ? renderBadge(source, 'muted', 'sm') : ''}
            ${listingUrl ? `<a href="${escapeHtml(listingUrl)}" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-700 truncate">${escapeHtml(listingUrl)}</a>` : ''}
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${metricsHtml}
        ${relistHtml}
        ${sourceHtml}
        ${historyHtml}
    </div>`;
}

export function bind(container, state) {
    // Listing tab is read-only
}
