/**
 * Properties list view — table with Address, County, Type, Last Run Status, Added.
 * Mobile card fallback. Click row navigates to #property/{id}.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { formatDate, escapeHtml } from '../utils.js';
import { renderBadge, runStatusBadgeVariant } from '../components/badge.js';
import { showAddPropertyModal } from '../components/modal.js';

let _data = {
    properties: [],
    latestRuns: {},
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

        // Load latest run for each property (first 20)
        const runMap = {};
        await Promise.allSettled(
            _data.properties.slice(0, 20).map(async (p) => {
                try {
                    const runs = await api.getPipelineRuns(p.id, 1);
                    if (runs.length > 0) runMap[p.id] = runs[0];
                } catch { /* skip */ }
            })
        );
        _data.latestRuns = runMap;
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

function formatPropertyType(type) {
    if (!type) return '--';
    return type.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function runStatusLabel(status) {
    if (!status) return 'No runs';
    return status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function runBadgeVariant(status) {
    if (!status) return 'muted';
    return runStatusBadgeVariant(status);
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container) {
    const { properties, latestRuns, loading, error } = _data;

    const errorHtml = error
        ? `<div class="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-4">${escapeHtml(error)}</div>`
        : '';

    let bodyHtml;

    if (loading) {
        bodyHtml = '<div class="text-gray-500 text-sm">Loading properties...</div>';
    } else if (properties.length === 0) {
        bodyHtml = `
        <div class="text-center py-12 text-gray-500">
            <p class="text-lg mb-2">No properties yet</p>
            <p class="text-sm">Click "+ Add Property" to start tracking.</p>
        </div>`;
    } else {
        // Mobile cards
        const mobileCards = properties.map(p => {
            const run = latestRuns[p.id];
            const badge = renderBadge(runStatusLabel(run?.status), runBadgeVariant(run?.status), 'sm');
            const countyBadge = p.county
                ? renderBadge(p.county, p.county === 'fairfax' ? 'info' : 'warning', 'sm')
                : '';
            return `
            <a href="#property/${p.id}" class="block bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors">
                <div class="text-sm font-medium text-gray-900 mb-1">${escapeHtml(p.address || 'No address')}</div>
                <div class="flex items-center gap-2 flex-wrap">
                    ${countyBadge}
                    ${badge}
                    <span class="text-xs text-gray-500 ml-auto">${formatDate(p.created_at)}</span>
                </div>
            </a>`;
        }).join('');

        // Desktop table rows
        const tableRows = properties.map(p => {
            const run = latestRuns[p.id];
            const badge = renderBadge(runStatusLabel(run?.status), runBadgeVariant(run?.status), 'sm');
            return `
            <tr class="hover:bg-gray-50 cursor-pointer" data-property-id="${escapeHtml(p.id)}">
                <td class="px-4 py-3 font-medium text-gray-900">${escapeHtml(p.address || 'No address')}</td>
                <td class="px-4 py-3 text-gray-700 capitalize">${escapeHtml(p.county || '--')}</td>
                <td class="px-4 py-3 text-gray-700">${escapeHtml(formatPropertyType(p.property_type))}</td>
                <td class="px-4 py-3">${badge}</td>
                <td class="px-4 py-3 text-gray-500">${formatDate(p.created_at)}</td>
            </tr>`;
        }).join('');

        bodyHtml = `
        <!-- Mobile card view -->
        <div class="md:hidden space-y-3">${mobileCards}</div>

        <!-- Desktop table view -->
        <div class="hidden md:block bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="min-w-full text-sm">
                <thead>
                    <tr class="bg-gray-50 text-gray-600 text-left">
                        <th class="px-4 py-3 font-medium">Address</th>
                        <th class="px-4 py-3 font-medium">County</th>
                        <th class="px-4 py-3 font-medium">Type</th>
                        <th class="px-4 py-3 font-medium">Last Run</th>
                        <th class="px-4 py-3 font-medium">Added</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${tableRows}</tbody>
            </table>
        </div>`;
    }

    container.innerHTML = `
    <div>
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

    // Table row clicks
    container.querySelectorAll('[data-property-id]').forEach(row => {
        row.addEventListener('click', () => {
            const id = row.getAttribute('data-property-id');
            window.location.hash = `#property/${id}`;
        });
    });
}
