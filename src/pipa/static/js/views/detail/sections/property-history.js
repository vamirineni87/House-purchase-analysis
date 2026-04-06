/**
 * Section §8: Property History — combined chronological timeline.
 *
 * Merges listing price history, county assessments, permits, and deeds
 * into a single date-sorted table with filter chips and expandable rows.
 */

import { formatCurrency, formatDate, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Property History';
export const ID = 'property-history';
export const DEFAULT_EXPANDED = true;

export function shouldAutoExpand(_state) { return false; }

export function getStateBadge(state) {
    const hasListing = !!(state.listingData?.price_history?.length);
    const hasCounty = !!(
        state.countyData?.assessments?.length ||
        state.countyData?.permits?.length ||
        state.countyData?.deeds?.length
    );
    if (hasListing && hasCounty) return { label: 'Complete', variant: 'success' };
    if (hasListing || hasCounty) return { label: 'Partial', variant: 'warning' };
    return { label: 'Not run', variant: 'not-run' };
}

export function headerExtra(_state) { return ''; }

// ── Helpers ────────────────────────────────────────────────────────

const TYPE_CONFIG = {
    listing:    { label: 'Listing',    variant: 'info' },
    assessment: { label: 'Assessment', variant: 'muted' },
    permit:     { label: 'Permit',     variant: 'warning' },
    deed:       { label: 'Deed',       variant: 'success' },
};

/**
 * Merge all data sources into a flat array of timeline events.
 * Each event: { date, sortKey, type, description, amount, detail }
 */
function buildTimeline(state) {
    const events = [];

    // 1. Listing price history
    const priceHistory = state.listingData?.price_history || [];
    for (const ph of priceHistory) {
        const eventType = ph.event_type || ph.event || 'unknown';
        const desc = eventType.replace(/_/g, ' ');
        events.push({
            date: ph.date || '',
            sortKey: ph.date || '0000-00-00',
            type: 'listing',
            description: desc.charAt(0).toUpperCase() + desc.slice(1),
            amount: ph.price ?? null,
            detail: null,
        });
    }

    // 2. County assessments
    const assessments = state.countyData?.assessments || [];
    for (const a of assessments) {
        const year = a.tax_year || a.year;
        const dateStr = year ? `${year}-01-01` : '';
        events.push({
            date: dateStr,
            sortKey: dateStr || '0000-00-00',
            type: 'assessment',
            description: `Tax assessment ${year || ''}`.trim(),
            amount: a.total_value ?? null,
            detail: {
                land_value: a.land_value,
                improvement_value: a.improvement_value,
                total_value: a.total_value,
                annual_tax: a.annual_tax,
            },
        });
    }

    // 3. County permits
    const permits = state.countyData?.permits || [];
    for (const p of permits) {
        events.push({
            date: p.issue_date || '',
            sortKey: p.issue_date || '0000-00-00',
            type: 'permit',
            description: [p.type, p.description].filter(Boolean).join(' — ') || 'Permit',
            amount: p.estimated_cost ?? null,
            detail: {
                permit_number: p.permit_number,
                status: p.status,
                description: p.description,
                type: p.type,
            },
        });
    }

    // 4. County deeds
    const deeds = state.countyData?.deeds || [];
    for (const d of deeds) {
        events.push({
            date: d.sale_date || '',
            sortKey: d.sale_date || '0000-00-00',
            type: 'deed',
            description: d.deed_type || 'Deed transfer',
            amount: d.sale_price ?? null,
            detail: {
                grantor: d.grantor,
                grantee: d.grantee,
                deed_type: d.deed_type,
                instrument_number: d.instrument_number,
            },
        });
    }

    // Sort most-recent first
    events.sort((a, b) => (b.sortKey > a.sortKey ? 1 : b.sortKey < a.sortKey ? -1 : 0));
    return events;
}

function renderDetailRow(detail) {
    if (!detail) return '';
    const pairs = Object.entries(detail)
        .filter(([, v]) => v != null && v !== '')
        .map(([k, v]) => {
            const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const val = typeof v === 'number' ? formatCurrency(v) : escapeHtml(String(v));
            return `<span class="text-xs text-gray-500"><span class="font-medium text-gray-600">${escapeHtml(label)}:</span> ${val}</span>`;
        });
    return pairs.join('<span class="text-gray-300 mx-1">|</span>');
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const events = buildTimeline(state);

    if (events.length === 0) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">No history data. Run the pipeline and refresh county data to build a timeline.</p>
        </div>`;
    }

    // Filter chips
    const chipBase = 'px-2.5 py-1 text-xs font-medium rounded-full cursor-pointer border transition-colors select-none';
    const chipActive = 'bg-blue-600 text-white border-blue-600';
    const chipInactive = 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100';
    const filters = [
        { type: 'all', label: 'All' },
        { type: 'listing', label: 'Listing' },
        { type: 'assessment', label: 'Assessment' },
        { type: 'permit', label: 'Permit' },
        { type: 'deed', label: 'Deed' },
    ];
    const chipsHtml = filters
        .map(f => `<button class="history-filter-chip ${chipBase} ${f.type === 'all' ? chipActive : chipInactive}" data-filter-type="${f.type}">${f.label}</button>`)
        .join('');

    // Table rows
    const rowsHtml = events.map((evt, i) => {
        const cfg = TYPE_CONFIG[evt.type] || TYPE_CONFIG.listing;
        const detailContent = renderDetailRow(evt.detail);
        const hasDetail = !!detailContent;
        const rowCursor = hasDetail ? 'cursor-pointer' : '';
        const bgClass = i % 2 === 1 ? 'bg-gray-50' : '';

        return `
        <tr class="history-row ${bgClass} hover:bg-gray-100 transition-colors ${rowCursor}" data-event-type="${evt.type}" data-row-idx="${i}">
            <td class="px-2 py-1.5 text-xs text-gray-700 whitespace-nowrap">${formatDate(evt.date)}</td>
            <td class="px-2 py-1.5">${renderBadge(cfg.label, cfg.variant, 'sm')}</td>
            <td class="px-2 py-1.5 text-xs text-gray-700 max-w-xs truncate">${escapeHtml(evt.description)}</td>
            <td class="px-2 py-1.5 text-xs text-gray-700 text-right whitespace-nowrap">${evt.amount != null ? formatCurrency(evt.amount) : '\u2014'}</td>
        </tr>
        ${hasDetail ? `
        <tr class="history-detail-row hidden" data-detail-for="${i}">
            <td colspan="4" class="px-3 py-2 bg-gray-50 border-t border-gray-100">
                <div class="flex flex-wrap gap-x-3 gap-y-1">${detailContent}</div>
            </td>
        </tr>` : ''}`;
    }).join('');

    return `
    <div class="space-y-3">
        <div class="flex flex-wrap gap-1.5">${chipsHtml}</div>
        <div class="overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Amount</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">${rowsHtml}</tbody>
            </table>
        </div>
        <p class="text-xs text-gray-400">${events.length} event${events.length !== 1 ? 's' : ''} from ${new Set(events.map(e => e.type)).size} source${new Set(events.map(e => e.type)).size !== 1 ? 's' : ''}</p>
    </div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, _state, _actions) {
    // Filter chips
    const chips = container.querySelectorAll('.history-filter-chip');
    const rows = container.querySelectorAll('.history-row');
    const detailRows = container.querySelectorAll('.history-detail-row');

    const chipActive = 'bg-blue-600 text-white border-blue-600';
    const chipInactive = 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100';

    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            const filterType = chip.getAttribute('data-filter-type');

            // Update chip styles
            chips.forEach(c => {
                c.className = c.className
                    .replace(/bg-blue-600|text-white|border-blue-600/g, '')
                    .replace(/bg-white|text-gray-600|border-gray-300|hover:bg-gray-100/g, '')
                    .trim();
                c.classList.add(...chipInactive.split(' '));
            });
            chip.className = chip.className
                .replace(/bg-white|text-gray-600|border-gray-300|hover:bg-gray-100/g, '')
                .trim();
            chip.classList.add(...chipActive.split(' '));

            // Toggle row visibility
            rows.forEach(row => {
                const rowType = row.getAttribute('data-event-type');
                if (filterType === 'all' || rowType === filterType) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });

            // Hide all detail rows when filter changes
            detailRows.forEach(dr => dr.classList.add('hidden'));
        });
    });

    // Expandable rows
    rows.forEach(row => {
        const idx = row.getAttribute('data-row-idx');
        const detailRow = container.querySelector(`[data-detail-for="${idx}"]`);
        if (!detailRow) return;

        row.addEventListener('click', () => {
            detailRow.classList.toggle('hidden');
        });
    });
}
