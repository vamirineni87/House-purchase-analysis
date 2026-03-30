/**
 * County tab — three sections: Assessments table, Permits list, Deeds table.
 * "Refresh County" button. Handles empty: "Click Refresh County to fetch records."
 */

import { api } from '../../api.js';
import { formatCurrency, formatDate, escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';
import { showToast } from '../../toast.js';

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const data = state.countyData;

    if (!data) {
        container.innerHTML = `
        <div class="space-y-6">
            <div class="flex items-center justify-between">
                <h3 class="text-sm font-semibold text-gray-700">County Records</h3>
                <button id="county-refresh-btn" class="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200">Refresh County</button>
            </div>
            <div class="text-gray-500 text-sm text-center py-8">
                No county data available. Click "Refresh County" to fetch records.
            </div>
        </div>`;
        return;
    }

    // Assessments table
    let assessmentsHtml;
    if (!data.assessments || data.assessments.length === 0) {
        assessmentsHtml = '<p class="text-sm text-gray-500">No assessment records.</p>';
    } else {
        const rows = data.assessments.map(a => `
        <tr>
            <td class="px-3 py-2 font-medium">${a.tax_year}</td>
            <td class="px-3 py-2 text-right">${formatCurrency(a.land_value)}</td>
            <td class="px-3 py-2 text-right">${formatCurrency(a.improvement_value)}</td>
            <td class="px-3 py-2 text-right font-medium">${formatCurrency(a.total_value)}</td>
            <td class="px-3 py-2 text-right">${a.annual_tax ? formatCurrency(a.annual_tax) : '--'}</td>
        </tr>`).join('');

        assessmentsHtml = `
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="min-w-full text-sm">
                <thead>
                    <tr class="bg-gray-50 text-gray-600 text-left">
                        <th class="px-3 py-2 font-medium">Year</th>
                        <th class="px-3 py-2 font-medium text-right">Land</th>
                        <th class="px-3 py-2 font-medium text-right">Improvement</th>
                        <th class="px-3 py-2 font-medium text-right">Total</th>
                        <th class="px-3 py-2 font-medium text-right">Annual Tax</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${rows}</tbody>
            </table>
        </div>`;
    }

    // Permits list
    let permitsHtml;
    if (!data.permits || data.permits.length === 0) {
        permitsHtml = '<p class="text-sm text-gray-500">No permit records.</p>';
    } else {
        const cards = data.permits.map(p => {
            const statusVariant = p.status === 'final' ? 'success' : p.status === 'issued' ? 'info' : 'muted';
            const statusBadge = p.status ? renderBadge(p.status, statusVariant) : '';
            const permitNumber = p.permit_number ? `<span class="text-gray-400 ml-2">#${escapeHtml(p.permit_number)}</span>` : '';
            const description = p.description ? `<p class="text-xs text-gray-600 mt-1">${escapeHtml(p.description)}</p>` : '';
            const cost = p.estimated_cost ? `<p class="text-xs text-gray-500 mt-1">Est. cost: ${formatCurrency(p.estimated_cost)}</p>` : '';

            return `
            <div class="bg-white border border-gray-200 rounded-lg p-3">
                <div class="flex items-center justify-between">
                    <span class="text-sm font-medium text-gray-900">${escapeHtml(p.type)}${permitNumber}</span>
                    <div class="flex gap-2 items-center">
                        ${statusBadge}
                        <span class="text-xs text-gray-500">${formatDate(p.issue_date)}</span>
                    </div>
                </div>
                ${description}
                ${cost}
            </div>`;
        }).join('');

        permitsHtml = `<div class="space-y-2">${cards}</div>`;
    }

    // Deeds table
    let deedsHtml;
    if (!data.deeds || data.deeds.length === 0) {
        deedsHtml = '<p class="text-sm text-gray-500">No deed records.</p>';
    } else {
        const rows = data.deeds.map(d => `
        <tr>
            <td class="px-3 py-2">${formatDate(d.sale_date)}</td>
            <td class="px-3 py-2">${escapeHtml(d.deed_type || '--')}</td>
            <td class="px-3 py-2 text-xs">${escapeHtml(d.grantor || '--')}</td>
            <td class="px-3 py-2 text-xs">${escapeHtml(d.grantee || '--')}</td>
            <td class="px-3 py-2 text-right font-medium">${d.sale_price ? formatCurrency(d.sale_price) : '--'}</td>
        </tr>`).join('');

        deedsHtml = `
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="min-w-full text-sm">
                <thead>
                    <tr class="bg-gray-50 text-gray-600 text-left">
                        <th class="px-3 py-2 font-medium">Date</th>
                        <th class="px-3 py-2 font-medium">Type</th>
                        <th class="px-3 py-2 font-medium">Grantor</th>
                        <th class="px-3 py-2 font-medium">Grantee</th>
                        <th class="px-3 py-2 font-medium text-right">Price</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${rows}</tbody>
            </table>
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-gray-700">County Records</h3>
            <button id="county-refresh-btn" class="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200">Refresh County</button>
        </div>

        <div>
            <h4 class="text-sm font-medium text-gray-600 mb-2">Tax Assessments</h4>
            ${assessmentsHtml}
        </div>

        <div>
            <h4 class="text-sm font-medium text-gray-600 mb-2">Building Permits</h4>
            ${permitsHtml}
        </div>

        <div>
            <h4 class="text-sm font-medium text-gray-600 mb-2">Deed / Ownership History</h4>
            ${deedsHtml}
        </div>
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container, state, actions) {
    const refreshBtn = container.querySelector('#county-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            refreshBtn.disabled = true;
            refreshBtn.textContent = 'Refreshing...';
            try {
                await api.refreshCountyData(state.propertyId);
                state.countyData = await api.getCountyData(state.propertyId);
                showToast('County data refreshed', 'success');
                if (actions?.reload) actions.reload();
            } catch (err) {
                showToast('Failed to refresh county data', 'error');
                refreshBtn.disabled = false;
                refreshBtn.textContent = 'Refresh County';
            }
        });
    }
}
