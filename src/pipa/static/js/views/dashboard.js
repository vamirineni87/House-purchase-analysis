/**
 * Dashboard view — stats bar (4 cards), active pipeline runs,
 * kanban board (6 columns), add property button.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { formatCurrency, formatDate, escapeHtml } from '../utils.js';
import { STAGES } from '../constants.js';
import { renderBadge, stageBadgeVariant } from '../components/badge.js';
import { renderMetricCard } from '../components/metric-card.js';
import { showAddPropertyModal } from '../components/modal.js';

let _data = {
    properties: [],
    watchlist: [],
    alerts: [],
    activeRuns: [],
    loading: true,
};

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container) {
    _data.loading = true;
    render(container);

    try {
        const [props, watch, alertData] = await Promise.all([
            api.listProperties(),
            api.listWatchlist(),
            api.listAlerts({ unread_only: true, limit: 10 }),
        ]);
        _data.properties = props || [];
        _data.watchlist = watch || [];
        _data.alerts = alertData || [];

        // Find active runs across first 10 properties
        const runs = [];
        for (const p of _data.properties.slice(0, 10)) {
            try {
                const pipeRuns = await api.getPipelineRuns(p.id, 1);
                const running = pipeRuns.filter(r => r.status === 'running' || r.status === 'queued');
                runs.push(...running);
            } catch { /* skip */ }
        }
        _data.activeRuns = runs;
    } catch (err) {
        showToast('Failed to load dashboard', 'error');
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
    const { properties, watchlist, alerts, activeRuns, loading } = _data;

    const propMap = new Map();
    for (const p of properties) propMap.set(p.id, p);

    const byStage = new Map();
    for (const s of STAGES) byStage.set(s, []);
    for (const entry of watchlist) {
        const list = byStage.get(entry.stage);
        if (list) list.push(entry);
    }

    const totalTracked = properties.length;
    const onWatchlist = watchlist.length;
    const unreadAlerts = alerts.filter(a => !a.is_read).length;

    // Stats bar
    const statsHtml = `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        ${renderMetricCard('Total Properties', String(totalTracked))}
        ${renderMetricCard('On Watchlist', String(onWatchlist))}
        ${renderMetricCard('Active Runs', String(activeRuns.length))}
        <a href="#alerts">${renderMetricCard('Unread Alerts', String(unreadAlerts))}</a>
    </div>`;

    // Active pipeline runs
    let activeRunsHtml = '';
    if (activeRuns.length > 0) {
        const runCards = activeRuns.map(run => {
            const prop = propMap.get(run.property_id);
            const tasks = run.tasks || [];
            const completed = tasks.filter(t => t.status === 'succeeded' || t.status === 'failed').length;
            const pct = tasks.length > 0 ? (completed / tasks.length) * 100 : 0;
            return `
            <a href="#property/${run.property_id}" class="block bg-white border border-blue-200 rounded-lg p-3 hover:bg-blue-50/50">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <div class="w-2.5 h-2.5 bg-blue-500 rounded-full animate-pulse"></div>
                        <span class="text-sm font-medium text-gray-900">${escapeHtml(prop?.address || run.property_id.slice(0, 8))}</span>
                    </div>
                    <span class="text-xs text-gray-500">${completed}/${tasks.length} tasks</span>
                </div>
                <div class="mt-1.5 w-full bg-gray-100 rounded-full h-1.5">
                    <div class="bg-blue-500 h-1.5 rounded-full transition-all" style="width:${pct}%"></div>
                </div>
            </a>`;
        }).join('');
        activeRunsHtml = `
        <div class="mb-8">
            <h2 class="text-sm font-semibold text-gray-700 mb-3">Active Pipeline Runs</h2>
            <div class="space-y-2">${runCards}</div>
        </div>`;
    }

    // Kanban board
    let kanbanHtml;
    if (loading) {
        kanbanHtml = '<div class="text-gray-500 text-sm">Loading...</div>';
    } else {
        const columns = STAGES.map(stage => {
            const entries = byStage.get(stage) || [];
            const countBadge = entries.length > 0
                ? `<span class="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">${entries.length}</span>`
                : '';

            let cardsHtml;
            if (entries.length === 0) {
                cardsHtml = '<p class="text-gray-400 text-sm">No properties</p>';
            } else {
                cardsHtml = '<div class="space-y-2">' + entries.map(entry => {
                    const prop = propMap.get(entry.property_id);
                    const countyBadge = prop?.county
                        ? renderBadge(prop.county, prop.county === 'fairfax' ? 'info' : 'warning', 'sm')
                        : '';
                    return `
                    <a href="#property/${entry.property_id}" class="block p-2 border border-gray-100 rounded hover:border-blue-200 hover:bg-blue-50/50 transition-colors">
                        <div class="text-xs font-medium text-gray-900 truncate">${escapeHtml(prop?.address || 'Unknown')}</div>
                        <div class="flex items-center justify-between mt-1">
                            ${countyBadge}
                            <span class="text-xs text-gray-400">${formatDate(entry.added_at)}</span>
                        </div>
                    </a>`;
                }).join('') + '</div>';
            }

            return `
            <div class="bg-white rounded-lg border border-gray-200 p-4 min-h-[200px]">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-semibold text-sm text-gray-500 uppercase tracking-wide">${stage}</h3>
                    ${countBadge}
                </div>
                ${cardsHtml}
            </div>`;
        }).join('');

        kanbanHtml = `<div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">${columns}</div>`;
    }

    container.innerHTML = `
    <div>
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-2xl font-bold mb-1">Dashboard</h1>
                <p class="text-gray-500 text-sm">Property Intelligence Platform -- Fairfax & Loudoun County, VA</p>
            </div>
            <button id="add-property-btn" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors">+ Add Property</button>
        </div>
        ${statsHtml}
        ${activeRunsHtml}
        <h2 class="text-sm font-semibold text-gray-700 mb-3">Watchlist Pipeline</h2>
        ${kanbanHtml}
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
}
