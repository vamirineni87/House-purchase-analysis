/**
 * Properties list view — quick-glance table with key metrics.
 * Shows: Address, Price, County+8%, Zest, Beds/Baths, Sqft, DOM, Status.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { formatDate, formatCurrency, escapeHtml } from '../utils.js';
import { renderBadge, runStatusBadgeVariant } from '../components/badge.js';
import { showAddPropertyModal } from '../components/modal.js';

let _data = {
    properties: [],
    latestRuns: {},
    listings: {},
    countyAssessed: {},
    loading: true,
    error: null,
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

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container) {
    const { properties, latestRuns, listings, countyAssessed, loading, error } = _data;

    const errorHtml = error
        ? `<div class="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">${escapeHtml(error)}</div>`
        : '';

    let bodyHtml;

    if (loading) {
        bodyHtml = '<div class="text-gray-500 text-sm py-8">Loading properties...</div>';
    } else if (properties.length === 0) {
        bodyHtml = `
        <div class="text-center py-12 text-gray-500">
            <p class="text-lg mb-2">No properties yet</p>
            <p class="text-sm">Click "+ Add Property" to start tracking.</p>
        </div>`;
    } else {
        // Mobile cards
        const mobileCards = properties.map(p => {
            const ld = listings[p.id] || {};
            const run = latestRuns[p.id];
            const assessed = countyAssessed[p.id];
            const badge = renderBadge(runStatusLabel(run?.status), runStatusBadgeVariant(run?.status || ''), 'sm');

            return `
            <a href="#property/${p.id}" class="block bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors">
                <div class="text-sm font-medium text-gray-900 mb-1">${escapeHtml(p.address || 'No address')}</div>
                <div class="flex items-center gap-3 text-xs text-gray-600 mb-2">
                    <span class="font-semibold text-gray-900">${fmtPrice(ld.price)}</span>
                    <span>${fmtNum(ld.bedrooms || ld.beds)}bd/${fmtNum(ld.bathrooms || ld.baths)}ba</span>
                    <span>${fmtNum(ld.sqft)} sf</span>
                </div>
                <div class="flex items-center gap-2 flex-wrap">
                    ${badge}
                    <span class="text-xs text-gray-400 ml-auto">${formatDate(p.created_at)}</span>
                </div>
            </a>`;
        }).join('');

        // Desktop table rows
        const tableRows = properties.map(p => {
            const ld = listings[p.id] || {};
            const run = latestRuns[p.id];
            const assessed = countyAssessed[p.id];
            const assessedPlus8 = assessed ? Math.round(assessed * 1.08) : null;
            const badge = renderBadge(runStatusLabel(run?.status), runStatusBadgeVariant(run?.status || ''), 'sm');
            const dom = ld.days_on_zillow ?? ld.dom ?? ld.days_on_market;

            return `
            <tr class="hover:bg-gray-50 cursor-pointer" data-property-id="${escapeHtml(p.id)}">
                <td class="px-3 py-2.5">
                    <div class="font-medium text-gray-900 text-sm">${escapeHtml(p.address || 'No address')}</div>
                    <div class="text-xs text-gray-400">${escapeHtml(p.county || '')} &middot; ${escapeHtml((p.property_type || '').replace(/_/g, ' '))}</div>
                </td>
                <td class="px-3 py-2.5 text-sm font-semibold text-gray-900 text-right">${fmtPrice(ld.price)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-600 text-right">${fmtPrice(assessedPlus8)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-600 text-right">${fmtPrice(ld.zestimate)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-center">${fmtNum(ld.bedrooms || ld.beds)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-center">${fmtNum(ld.bathrooms || ld.baths)}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-right">${ld.sqft ? Number(ld.sqft).toLocaleString() : '--'}</td>
                <td class="px-3 py-2.5 text-sm text-gray-700 text-center">${dom != null ? dom : '--'}</td>
                <td class="px-3 py-2.5">${badge}</td>
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
                        <th class="px-3 py-2.5 font-medium">Status</th>
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

    container.querySelectorAll('[data-property-id]').forEach(row => {
        row.addEventListener('click', () => {
            const id = row.getAttribute('data-property-id');
            window.location.hash = `#property/${id}`;
        });
    });
}
