/**
 * Pipeline tab — data freshness grid, latest run task list with status dots,
 * run history table. Uses run-status-ribbon and task-list components.
 */

import { formatDate, escapeHtml } from '../../utils.js';
import { renderBadge, runStatusBadgeVariant } from '../../components/badge.js';
import { renderRunStatusRibbon } from '../../components/run-status-ribbon.js';
import { renderTaskList, bindTaskList } from '../../components/task-list.js';
import { api } from '../../api.js';
import { showToast } from '../../toast.js';

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const { pipelineRuns, latestRun, freshness } = state;

    // Freshness grid
    let freshnessHtml = '';
    if (freshness && freshness.length > 0) {
        const cards = freshness.map(f => {
            const borderCls = f.is_stale ? 'border-amber-200 bg-amber-50' : 'border-gray-200 bg-white';
            const badge = f.is_stale
                ? renderBadge('Stale', 'warning', 'sm')
                : renderBadge('Fresh', 'success', 'sm');
            const lastFetched = f.last_fetched ? `Last: ${formatDate(f.last_fetched)}` : 'Never fetched';
            return `
            <div class="border rounded-lg p-3 ${borderCls}">
                <div class="flex items-center justify-between mb-1">
                    <span class="text-sm font-medium text-gray-900 capitalize">${escapeHtml(f.source)}</span>
                    ${badge}
                </div>
                <div class="text-xs text-gray-500">${lastFetched} | TTL: ${f.ttl_hours || '--'}h</div>
            </div>`;
        }).join('');

        freshnessHtml = `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Data Freshness</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">${cards}</div>
        </div>`;
    }

    // Latest run tasks
    let latestTasksHtml = '';
    if (latestRun) {
        const runType = (latestRun.run_type || '').replace(/_/g, ' ');
        latestTasksHtml = `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Latest Run: ${escapeHtml(runType)}</h3>
            ${renderTaskList(latestRun.tasks || [], true)}
        </div>`;
    }

    // Run history
    let historyHtml;
    if (pipelineRuns.length === 0) {
        historyHtml = '<div class="text-sm text-gray-500">No pipeline runs yet. Click "Run Full Pipeline" to start.</div>';
    } else {
        const rows = pipelineRuns.map(run => {
            const tasks = run.tasks || [];
            const succeeded = tasks.filter(t => t.status === 'succeeded').length;
            const failed = tasks.filter(t => t.status === 'failed').length;
            const label = run.status.replace(/_/g, ' ');
            const variant = run.status === 'succeeded' ? 'success'
                : run.status === 'failed' ? 'critical'
                : run.status === 'partial_success' ? 'warning' : 'info';

            return `
            <div class="bg-white border border-gray-200 rounded-lg p-3">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        ${renderBadge(label, variant, 'sm')}
                        <span class="text-sm text-gray-700">${escapeHtml((run.run_type || '').replace(/_/g, ' '))}</span>
                    </div>
                    <div class="flex items-center gap-3 text-xs text-gray-500">
                        <span>${succeeded}/${tasks.length} ok${failed > 0 ? `, ${failed} failed` : ''}</span>
                        <span>${formatDate(run.created_at)}</span>
                    </div>
                </div>
            </div>`;
        }).join('');

        historyHtml = `<div class="space-y-2">${rows}</div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${freshnessHtml}
        ${latestTasksHtml}
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Run History</h3>
            ${historyHtml}
        </div>
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container, state, actions) {
    // Bind task list error toggles
    bindTaskList(container);

    // Rerun task buttons
    container.querySelectorAll('[data-rerun-task]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const taskName = btn.getAttribute('data-rerun-task');
            if (!state.latestRun) return;
            btn.disabled = true;
            btn.textContent = '...';
            try {
                await api.rerunTask(state.latestRun.id, taskName);
                const runs = await api.getPipelineRuns(state.propertyId, 10);
                state.pipelineRuns = runs;
                state.latestRun = runs.length > 0 ? runs[0] : null;
                showToast(`Rerunning ${taskName.replace(/_/g, ' ')}`, 'success');
                if (actions?.reload) actions.reload();
            } catch {
                showToast('Failed to rerun task', 'error');
                btn.disabled = false;
                btn.textContent = 'Rerun';
            }
        });
    });
}
