/**
 * Alerts view — chronological list with severity badges,
 * "Unread only" toggle, "Mark all read" button.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { escapeHtml } from '../utils.js';
import { renderBadge, severityBadgeVariant } from '../components/badge.js';

let _data = {
    alerts: [],
    loading: true,
    showUnreadOnly: false,
};

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function formatDateTime(iso) {
    if (!iso) return '--';
    return new Date(iso).toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: 'numeric', minute: '2-digit',
    });
}

const ALERT_TYPE_LABELS = {
    price_cut: 'Price Cut',
    status_change: 'Status Change',
    back_on_market: 'Back on Market',
    source_degraded: 'Source Issue',
    nearby_price_change: 'Nearby Change',
    price_threshold_exceeded: 'Budget Alert',
    high_dom: 'High DOM',
    significant_price_drop: 'Big Price Drop',
    new_listing: 'New Listing',
    pipeline_failed: 'Pipeline Failed',
    data_stale: 'Data Stale',
    comp_update: 'Comp Update',
};

function alertTypeLabel(type) {
    return ALERT_TYPE_LABELS[type] || type.replace(/_/g, ' ');
}

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container) {
    _data.loading = true;
    render(container);
    bind(container);

    try {
        const data = await api.listAlerts({
            unread_only: _data.showUnreadOnly,
            limit: 100,
        });
        _data.alerts = data || [];
    } catch {
        showToast('Failed to load alerts', 'error');
    } finally {
        _data.loading = false;
    }

    render(container);
    bind(container);
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container) {
    const { alerts, loading, showUnreadOnly } = _data;
    const unreadCount = alerts.filter(a => !a.is_read).length;

    let bodyHtml;
    if (loading) {
        bodyHtml = '<div class="text-gray-500 text-sm">Loading alerts...</div>';
    } else if (alerts.length === 0) {
        bodyHtml = `
        <div class="text-center py-12 text-gray-500">
            <p class="text-lg mb-1">No alerts</p>
            <p class="text-sm">Alerts will appear here when property changes are detected.</p>
        </div>`;
    } else {
        bodyHtml = '<div class="space-y-2">' + alerts.map(alert => {
            const borderClass = alert.is_read
                ? 'border-gray-200'
                : 'border-blue-200 bg-blue-50/30';
            const unreadDot = !alert.is_read
                ? '<span class="w-2 h-2 bg-blue-500 rounded-full"></span>'
                : '';
            const markReadBtn = !alert.is_read
                ? `<button data-mark-read="${escapeHtml(alert.id)}" class="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap">Mark read</button>`
                : '';
            const propLink = alert.property_id
                ? `<span class="ml-2"><a href="#property/${escapeHtml(alert.property_id)}" class="text-blue-500 hover:text-blue-700">View property</a></span>`
                : '';

            return `
            <div class="bg-white border rounded-lg p-4 transition-colors ${borderClass}">
                <div class="flex items-start justify-between gap-4">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1 flex-wrap">
                            ${renderBadge(alert.severity, severityBadgeVariant(alert.severity))}
                            ${renderBadge(alertTypeLabel(alert.alert_type), 'muted')}
                            ${unreadDot}
                        </div>
                        <h3 class="text-sm font-medium text-gray-900">${escapeHtml(alert.title)}</h3>
                        ${alert.description ? `<p class="text-xs text-gray-600 mt-1">${escapeHtml(alert.description)}</p>` : ''}
                        <div class="text-xs text-gray-400 mt-2">
                            ${formatDateTime(alert.triggered_at)}
                            ${propLink}
                        </div>
                    </div>
                    ${markReadBtn}
                </div>
            </div>`;
        }).join('') + '</div>';
    }

    const unreadSubtext = unreadCount > 0
        ? `<p class="text-sm text-gray-500 mt-1">${unreadCount} unread alert${unreadCount !== 1 ? 's' : ''}</p>`
        : '';
    const markAllBtn = unreadCount > 0
        ? '<button id="mark-all-read" class="text-sm text-blue-600 hover:text-blue-800">Mark all read</button>'
        : '';

    container.innerHTML = `
    <div>
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-2xl font-bold">Alerts</h1>
                ${unreadSubtext}
            </div>
            <div class="flex gap-3 items-center">
                <label class="flex items-center gap-2 text-sm text-gray-600">
                    <input type="checkbox" id="unread-toggle" ${showUnreadOnly ? 'checked' : ''} class="rounded border-gray-300 text-blue-600" />
                    Unread only
                </label>
                ${markAllBtn}
            </div>
        </div>
        ${bodyHtml}
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container) {
    // Unread toggle
    const toggle = container.querySelector('#unread-toggle');
    if (toggle) {
        toggle.addEventListener('change', () => {
            _data.showUnreadOnly = toggle.checked;
            load(container);
        });
    }

    // Mark all read
    const markAll = container.querySelector('#mark-all-read');
    if (markAll) {
        markAll.addEventListener('click', async () => {
            try {
                await api.markAllAlertsRead();
                _data.alerts = _data.alerts.map(a => ({ ...a, is_read: true }));
                showToast('All alerts marked as read', 'success');
                render(container);
                bind(container);
            } catch {
                showToast('Failed to mark alerts read', 'error');
            }
        });
    }

    // Individual mark read
    container.querySelectorAll('[data-mark-read]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const alertId = btn.getAttribute('data-mark-read');
            try {
                const updated = await api.markAlertRead(alertId, true);
                _data.alerts = _data.alerts.map(a => a.id === updated.id ? updated : a);
                render(container);
                bind(container);
            } catch {
                showToast('Failed to mark alert read', 'error');
            }
        });
    });
}
