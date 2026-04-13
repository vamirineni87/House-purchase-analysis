/**
 * Properties list view — quick-glance table with key metrics.
 * Shows: Address, Price, County+8%, Zest, Beds/Baths, Sqft, DOM, Status.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { formatDate, formatCurrency, escapeHtml } from '../utils.js';
import { renderBadge, runStatusBadgeVariant } from '../components/badge.js';
import { showAddPropertyModal } from '../components/modal.js';

// Watchlist-stage filter chips. "active" is the default — everything except
// rejected, so stale-lost offers don't clutter the main view.
const WATCHLIST_STAGES = ['researching', 'touring', 'offer', 'contract', 'closed', 'rejected'];
const FILTER_CHIPS = [
    { key: 'active', label: 'Active' },
    { key: 'all', label: 'All' },
    ...WATCHLIST_STAGES.map(s => ({ key: s, label: s.charAt(0).toUpperCase() + s.slice(1) })),
];

let _data = {
    properties: [],
    latestRuns: {},
    listings: {},
    countyAssessed: {},
    loading: true,
    error: null,
    filter: 'active',
};

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container) {
    _data.loading = true;
    _data.error = null;
    render(container);

    try {
        const data = await api.listProperties();
        _data.properties = data || [];

        // Load latest run + listing data + county for each property (parallel)
        const runMap = {};
        const listingMap = {};
        const countyMap = {};
        await Promise.allSettled(
            _data.properties.slice(0, 20).map(async (p) => {
                const [runRes, listingRes, countyRes] = await Promise.allSettled([
                    api.getPipelineRuns(p.id, 1),
                    api.getListingData(p.id),
                    api.getCountyData(p.id),
                ]);
                if (runRes.status === 'fulfilled' && runRes.value.length > 0) {
                    runMap[p.id] = runRes.value[0];
                }
                if (listingRes.status === 'fulfilled') {
                    listingMap[p.id] = listingRes.value?.listing_data || listingRes.value || {};
                }
                if (countyRes.status === 'fulfilled') {
                    const assessments = countyRes.value?.assessments || [];
                    if (assessments.length > 0) {
                        countyMap[p.id] = assessments[0]?.total_value || null;
                    }
                }
            })
        );
        _data.latestRuns = runMap;
        _data.listings = listingMap;
        _data.countyAssessed = countyMap;
    } catch (err) {
        _data.error = err.message || 'Failed to load properties';
    } finally {
        _data.loading = false;
    }

    render(container);
    bind(container);
}

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function fmtPrice(n) {
    if (n == null) return '--';
    return formatCurrency(n);
}

function fmtNum(n) {
    if (n == null || n === '') return '--';
    return String(n);
}

function runStatusLabel(status) {
    if (!status) return 'No runs';
    return status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function statusLabel(v) {
    if (!v) return '--';
    return v.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// Color pill for a buyer-status value. Picks a Tailwind palette based on the
// value's *meaning* (positive / neutral / negative) so Rejected always reads
// red regardless of which of the three status fields it came from.
function statusPill(v) {
    if (!v) return '<span class="text-gray-300">--</span>';
    const key = v.toLowerCase();
    let cls = 'bg-gray-100 text-gray-700';
    if (['rejected', 'reject', 'lost', 'passed', 'deprioritize'].includes(key)) {
        cls = 'bg-red-100 text-red-700';
    } else if (['won', 'pursue', 'offer', 'offered', 'offer_ready', 'contract'].includes(key)) {
        cls = 'bg-green-100 text-green-700';
    } else if (['touring', 'shortlisted', 'researching', 'maybe'].includes(key)) {
        cls = 'bg-blue-100 text-blue-700';
    } else if (['closed', 'discovered', 'waiting_on_docs'].includes(key)) {
        cls = 'bg-yellow-100 text-yellow-700';
    }
    return `<span class="inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}">${escapeHtml(statusLabel(v))}</span>`;
}

function filterProperties(properties, filter) {
    if (filter === 'all') return properties;
    if (filter === 'active') {
        return properties.filter(p => (p.watchlist_stage || '') !== 'rejected');
    }
    return properties.filter(p => (p.watchlist_stage || '') === filter);
}

function zillowLink(ld) {
    const url = ld?._url || ld?.listing_url || ld?.url || '';
    if (!url) return '';
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="text-blue-400 hover:text-blue-600 transition-colors" title="View on Zillow" onclick="event.stopPropagation()">
        <svg class="w-4 h-4 inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
    </a>`;
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container) {
    const { properties, latestRuns, listings, countyAssessed, loading, error, filter } = _data;

    const errorHtml = error
        ? `<div class="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">${escapeHtml(error)}</div>`
        : '';

    // Per-stage counts drive the chip badges.
    const counts = { all: properties.length, active: 0 };
    for (const s of WATCHLIST_STAGES) counts[s] = 0;
    for (const p of properties) {
        const s = p.watchlist_stage || '';
        if (s !== 'rejected') counts.active += 1;
        if (s && counts[s] != null) counts[s] += 1;
    }

    const chipsHtml = FILTER_CHIPS.map(c => {
        const active = filter === c.key;
        const cls = active
            ? 'bg-blue-600 text-white border-blue-600'
            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50';
        return `<button data-filter="${c.key}" class="px-3 py-1 text-xs rounded-full border transition-colors ${cls}">
            ${escapeHtml(c.label)} <span class="opacity-70">(${counts[c.key] || 0})</span>
        </button>`;
    }).join('');

    const filterBarHtml = !loading && properties.length > 0
        ? `<div class="flex flex-wrap gap-2 mb-4">${chipsHtml}</div>`
        : '';

    const visible = filterProperties(properties, filter);

    let bodyHtml;

    if (loading) {
        bodyHtml = '<div class="text-gray-500 text-sm py-8">Loading properties...</div>';
    } else if (properties.length === 0) {
        bodyHtml = `
        <div class="text-center py-12 text-gray-500">
            <p class="text-lg mb-2">No properties yet</p>
            <p class="text-sm">Click "+ Add Property" to start tracking.</p>
        </div>`;
    } else if (visible.length === 0) {
        bodyHtml = `
        <div class="text-center py-12 text-gray-500">
            <p class="text-sm">No properties match this filter.</p>
        </div>`;
    } else {
        // Mobile cards
        const mobileCards = visible.map(p => {
            const ld = listings[p.id] || {};
            const run = latestRuns[p.id];
            const assessed = countyAssessed[p.id];
            const badge = renderBadge(runStatusLabel(run?.status), runStatusBadgeVariant(run?.status || ''), 'sm');

            return `
            <div class="bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors relative">
                <a href="#property/${p.id}" class="block">
                    <div class="text-sm font-medium text-gray-900 mb-1">${escapeHtml(p.address || 'No address')} ${zillowLink(ld)}</div>
                    <div class="flex items-center gap-3 text-xs text-gray-600 mb-2">
                        <span class="font-semibold text-gray-900">${fmtPrice(ld.price)}</span>
                        <span>${fmtNum(ld.bedrooms || ld.beds)}bd/${fmtNum(ld.bathrooms || ld.baths)}ba</span>
                        <span>${fmtNum(ld.sqft)} sf</span>
                    </div>
                    <div class="flex items-center gap-2 flex-wrap mb-2">
                        ${statusPill(p.watchlist_stage)}
                        ${statusPill(p.decision_status)}
                        ${statusPill(p.decision_stage)}
                    </div>
                    <div class="flex items-center gap-2 flex-wrap">
                        ${badge}
                        <span class="text-xs text-gray-400 ml-auto">${formatDate(p.created_at)}</span>
                    </div>
                </a>
                <button data-delete-id="${escapeHtml(p.id)}" class="absolute top-2 right-2 text-gray-300 hover:text-red-500 transition-colors p-1" title="Delete property">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
            </div>`;
        }).join('');

        // Desktop table rows
        const tableRows = visible.map(p => {
            const ld = listings[p.id] || {};
            const run = latestRuns[p.id];
            const assessed = countyAssessed[p.id];
            const assessedPlus8 = assessed ? Math.round(assessed * 1.08) : null;
            const badge = renderBadge(runStatusLabel(run?.status), runStatusBadgeVariant(run?.status || ''), 'sm');
            const dom = ld.days_on_zillow ?? ld.dom ?? ld.days_on_market;

            return `
            <tr class="hover:bg-gray-50 cursor-pointer" data-property-id="${escapeHtml(p.id)}">
                <td class="px-3 py-2.5">
                    <div class="font-medium text-gray-900 text-sm">${escapeHtml(p.address || 'No address')} ${zillowLink(ld)}</div>
                    <div class="text-xs text-gray-400">${escapeHtml(p.county || '')} &middot; ${escapeHtml((p.property_type || '').replace(/_/g, ' '))}</div>
                </td>
                <td class="px-3 py-2.5 text-sm font-semibold text-gray-900 text-right">${fmtPrice(ld.price)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-600 text-right">${fmtPrice(assessedPlus8)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-600 text-right">${fmtPrice(ld.zestimate)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-center">${fmtNum(ld.bedrooms || ld.beds)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-center">${fmtNum(ld.bathrooms || ld.baths)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-right">${ld.sqft ? Number(ld.sqft).toLocaleString() : '--'}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-center">${dom != null ? dom : '--'}</td>
                <td class="px-3 py-2.5">${statusPill(p.watchlist_stage)}</td>
                <td class="px-3 py-2.5">${statusPill(p.decision_status)}</td>
                <td class="px-3 py-2.5">${statusPill(p.decision_stage)}</td>
                <td class="px-3 py-2.5">${badge}</td>
                <td class="px-3 py-2.5 text-center">
                    <button data-delete-id="${escapeHtml(p.id)}" class="text-gray-300 hover:text-red-500 transition-colors p-1" title="Delete property">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                    </button>
                </td>
            </tr>`;
        }).join('');

        bodyHtml = `
        <!-- Mobile card view -->
        <div class="md:hidden space-y-3">${mobileCards}</div>

        <!-- Desktop table view -->
        <div class="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="min-w-full text-sm">
                <thead>
                    <tr class="bg-gray-50 text-gray-500 text-left text-xs uppercase tracking-wide">
                        <th class="px-3 py-2.5 font-medium">Property</th>
                        <th class="px-3 py-2.5 font-medium text-right">Listed</th>
                        <th class="px-3 py-2.5 font-medium text-right">County+8%</th>
                        <th class="px-3 py-2.5 font-medium text-right">Zestimate</th>
                        <th class="px-3 py-2.5 font-medium text-center">Beds</th>
                        <th class="px-3 py-2.5 font-medium text-center">Baths</th>
                        <th class="px-3 py-2.5 font-medium text-right">Sqft</th>
                        <th class="px-3 py-2.5 font-medium text-center">DOM</th>
                        <th class="px-3 py-2.5 font-medium">Watchlist</th>
                        <th class="px-3 py-2.5 font-medium">Decision</th>
                        <th class="px-3 py-2.5 font-medium">Stage</th>
                        <th class="px-3 py-2.5 font-medium">Run</th>
                        <th class="px-3 py-2.5 font-medium text-center w-10"></th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${tableRows}</tbody>
            </table>
        </div>`;
    }

    container.innerHTML = `
    <div class="px-6 py-6">
        <div class="flex items-center justify-between mb-6">
            <h1 class="text-2xl font-bold">Properties</h1>
            <button id="add-property-btn" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors">+ Add Property</button>
        </div>
        ${errorHtml}
        ${filterBarHtml}
        ${bodyHtml}
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container) {
    const addBtn = container.querySelector('#add-property-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => showAddPropertyModal());
    }

    container.querySelectorAll('[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            _data.filter = btn.getAttribute('data-filter');
            render(container);
            bind(container);
        });
    });

    container.querySelectorAll('[data-property-id]').forEach(row => {
        row.addEventListener('click', (e) => {
            // Don't navigate if delete button was clicked
            if (e.target.closest('[data-delete-id]')) return;
            const id = row.getAttribute('data-property-id');
            window.location.hash = `#property/${id}`;
        });
    });

    // Delete buttons
    container.querySelectorAll('[data-delete-id]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            e.preventDefault();
            const id = btn.getAttribute('data-delete-id');
            const prop = _data.properties.find(p => p.id === id);
            const addr = prop?.address || 'this property';
            if (!confirm(`Delete "${addr}" and all its data? This cannot be undone.`)) return;

            btn.disabled = true;
            try {
                await api.deleteProperty(id);
                showToast('Property deleted', 'success');
                // Reload the list
                await load(container);
            } catch (err) {
                showToast('Delete failed: ' + (err.message || 'unknown'), 'error');
                btn.disabled = false;
            }
        });
    });
}
