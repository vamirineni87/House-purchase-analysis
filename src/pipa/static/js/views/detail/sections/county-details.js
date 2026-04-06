/**
 * Section §9: County Details — deep county records.
 *
 * Three sub-sections: Assessments table, Permits table, Deeds table.
 * Refresh County button in the header. Compact text-xs tables.
 */

import { formatCurrency, formatDate, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { showToast } from '../../../toast.js';
import { api } from '../../../api.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'County Details';
export const ID = 'county-details';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(_state) { return false; }

export function getStateBadge(state) {
    const cd = state.countyData;
    if (!cd) return { label: 'Not run', variant: 'not-run' };
    const hasAssessments = !!(cd.assessments?.length);
    const hasPermits = !!(cd.permits?.length);
    const hasDeeds = !!(cd.deeds?.length);
    if (hasAssessments || hasPermits || hasDeeds) return { label: 'Complete', variant: 'success' };
    return { label: 'Partial', variant: 'warning' };
}

export function headerExtra(state) {
    const loading = state.actionLoading?.refreshCounty;
    return `
    <button class="county-refresh-btn px-2.5 py-1 text-xs font-medium rounded border transition-colors
        ${loading ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}"
        ${loading ? 'disabled' : ''}>
        ${loading ? 'Refreshing...' : 'Refresh County'}
    </button>`;
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const cd = state.countyData;

    if (!cd) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">County data not fetched. Click <strong>Refresh County</strong> to pull records.</p>
        </div>`;
    }

    const parts = [];

    // ── Assessments ───────────────────────────────────────────────
    parts.push('<div>');
    parts.push('<h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Tax Assessments</h4>');
    const assessments = cd.assessments || [];
    if (assessments.length === 0) {
        parts.push('<p class="text-xs text-gray-500">No assessment records.</p>');
    } else {
        const aRows = assessments.map((a, i) => {
            const bg = i % 2 === 1 ? 'bg-gray-50' : '';
            return `
            <tr class="${bg} hover:bg-gray-100 transition-colors">
                <td class="px-2 py-1 text-xs font-medium text-gray-700">${escapeHtml(String(a.tax_year ?? ''))}</td>
                <td class="px-2 py-1 text-xs text-right text-gray-700">${formatCurrency(a.land_value)}</td>
                <td class="px-2 py-1 text-xs text-right text-gray-700">${formatCurrency(a.improvement_value)}</td>
                <td class="px-2 py-1 text-xs text-right font-medium text-gray-900">${formatCurrency(a.total_value)}</td>
                <td class="px-2 py-1 text-xs text-right text-gray-700">${a.annual_tax != null ? formatCurrency(a.annual_tax) : '\u2014'}</td>
            </tr>`;
        }).join('');
        parts.push(`
        <div class="overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Year</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Land</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Improvement</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Total</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Annual Tax</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-100">${aRows}</tbody>
            </table>
        </div>`);
    }
    parts.push('</div>');

    // ── Permits ───────────────────────────────────────────────────
    parts.push('<div>');
    parts.push('<h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Building Permits</h4>');
    const permits = cd.permits || [];
    if (permits.length === 0) {
        parts.push('<p class="text-xs text-gray-500">No permit records.</p>');
    } else {
        const pRows = permits.map((p, i) => {
            const bg = i % 2 === 1 ? 'bg-gray-50' : '';
            const statusVariant = p.status === 'final' ? 'success' : p.status === 'issued' ? 'info' : 'muted';
            return `
            <tr class="${bg} hover:bg-gray-100 transition-colors">
                <td class="px-2 py-1 text-xs text-gray-700 whitespace-nowrap">${escapeHtml(p.permit_number || '\u2014')}</td>
                <td class="px-2 py-1 text-xs text-gray-700">${escapeHtml(p.type || '\u2014')}</td>
                <td class="px-2 py-1 text-xs text-gray-700 max-w-xs truncate">${escapeHtml(p.description || '\u2014')}</td>
                <td class="px-2 py-1 text-xs text-right text-gray-700">${p.estimated_cost != null ? formatCurrency(p.estimated_cost) : '\u2014'}</td>
                <td class="px-2 py-1 text-xs text-gray-700 whitespace-nowrap">${formatDate(p.issue_date)}</td>
                <td class="px-2 py-1">${p.status ? renderBadge(p.status, statusVariant, 'sm') : '\u2014'}</td>
            </tr>`;
        }).join('');
        parts.push(`
        <div class="overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Permit #</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Est. Cost</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Issued</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-100">${pRows}</tbody>
            </table>
        </div>`);
    }
    parts.push('</div>');

    // ── Deeds ─────────────────────────────────────────────────────
    parts.push('<div>');
    parts.push('<h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Deed / Ownership History</h4>');
    const deeds = cd.deeds || [];
    if (deeds.length === 0) {
        parts.push('<p class="text-xs text-gray-500">No deed records.</p>');
    } else {
        const dRows = deeds.map((d, i) => {
            const bg = i % 2 === 1 ? 'bg-gray-50' : '';
            return `
            <tr class="${bg} hover:bg-gray-100 transition-colors">
                <td class="px-2 py-1 text-xs text-gray-700 whitespace-nowrap">${formatDate(d.sale_date)}</td>
                <td class="px-2 py-1 text-xs text-right font-medium text-gray-900">${d.sale_price != null ? formatCurrency(d.sale_price) : '\u2014'}</td>
                <td class="px-2 py-1 text-xs text-gray-700">${escapeHtml(d.grantor || '\u2014')}</td>
                <td class="px-2 py-1 text-xs text-gray-700">${escapeHtml(d.grantee || '\u2014')}</td>
                <td class="px-2 py-1 text-xs text-gray-700">${escapeHtml(d.deed_type || '\u2014')}</td>
                <td class="px-2 py-1 text-xs text-gray-500">${escapeHtml(d.instrument_number || '\u2014')}</td>
            </tr>`;
        }).join('');
        parts.push(`
        <div class="overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                        <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 uppercase">Price</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Grantor</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Grantee</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                        <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500 uppercase">Instrument #</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-100">${dRows}</tbody>
            </table>
        </div>`);
    }
    parts.push('</div>');

    return `<div class="space-y-5">${parts.join('')}</div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    const refreshBtn = container.querySelector('.county-refresh-btn');
    if (!refreshBtn) return;

    // Stop clicks from toggling the section collapse
    refreshBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (refreshBtn.disabled) return;

        refreshBtn.disabled = true;
        refreshBtn.textContent = 'Refreshing...';

        try {
            await api.refreshCountyData(state.property.id);
            state.countyData = await api.getCountyData(state.property.id);
            showToast('County data refreshed', 'success');
            if (actions?.rerenderSection) {
                actions.rerenderSection(ID);
            } else if (actions?.reload) {
                actions.reload();
            }
        } catch (err) {
            showToast('Failed to refresh county data: ' + (err.message || 'unknown'), 'error');
            refreshBtn.disabled = false;
            refreshBtn.textContent = 'Refresh County';
        }
    });
}
