/**
 * Section §2: Pipeline / Data Health
 *
 * Shows latest run status, task list with status badges and error toggles,
 * data freshness per source, and run history (last 5). Header has a
 * [Rerun Failed] button when any tasks failed.
 */

import { formatDate, escapeHtml } from '../../../utils.js';
import { renderBadge, runStatusBadgeVariant } from '../../../components/badge.js';
import { renderTaskList, bindTaskList } from '../../../components/task-list.js';
import { api } from '../../../api.js';
import { showToast } from '../../../toast.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Pipeline / Data Health';
export const ID = 'pipeline-health';
export const DEFAULT_EXPANDED = true;

export function shouldAutoExpand(state) {
    const status = state.latestRun?.status;
    return status === 'partial_success' || status === 'failed';
}

export function getStateBadge(state) {
    const status = state.latestRun?.status;
    if (!status) return { label: 'Not run', variant: 'not-run' };
    if (status === 'succeeded') return { label: 'Complete', variant: 'success' };
    if (status === 'partial_success') return { label: 'Partial', variant: 'warning' };
    if (status === 'failed') return { label: 'Failed', variant: 'critical' };
    if (status === 'running') return { label: 'Running', variant: 'info' };
    return { label: status.replace(/_/g, ' '), variant: 'muted' };
}

export function headerExtra(state) {
    const tasks = state.latestRun?.tasks || [];
    const hasFailed = tasks.some(t => t.status === 'failed');
    if (!hasFailed) return '';
    return `<button data-action="rerun-failed-header"
        class="px-2 py-1 text-xs font-medium text-red-600 border border-red-200 rounded hover:bg-red-50"
        onclick="event.stopPropagation()">Rerun Failed</button>`;
}

// ── Helpers ────────────────────────────────────────────────────────

function formatDurationCompact(ms) {
    if (!ms && ms !== 0) return '--';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
}

function formatRelative(iso) {
    if (!iso) return 'never';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const { latestRun, pipelineRuns, freshness } = state;
    const parts = [];

    // ── Latest Run ────────────────────────────────────────────────
    if (latestRun) {
        const tasks = latestRun.tasks || [];
        const succeeded = tasks.filter(t => t.status === 'succeeded').length;
        const failed = tasks.filter(t => t.status === 'failed').length;
        const skipped = tasks.filter(t => t.status === 'skipped').length;
        const statusLabel = (latestRun.status || '').replace(/_/g, ' ');
        const variant = runStatusBadgeVariant(latestRun.status);
        const runType = (latestRun.run_type || '').replace(/_/g, ' ');

        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Latest Run</div>
            <div class="flex items-center gap-3 mb-2">
                ${renderBadge(statusLabel, variant, 'sm')}
                <span class="text-xs text-gray-500">${escapeHtml(runType)}</span>
                <span class="text-xs text-gray-400">${formatDate(latestRun.started_at || latestRun.created_at)}</span>
                <span class="text-xs text-gray-400">${succeeded}ok / ${failed}fail / ${skipped}skip of ${tasks.length}</span>
            </div>
            ${renderTaskList(tasks, true)}
        </div>`);
    } else {
        parts.push(`
        <div class="bg-gray-50 border border-gray-200 rounded p-3 text-center">
            <p class="text-sm text-gray-500">No pipeline runs yet.</p>
        </div>`);
    }

    // ── Data Freshness ────────────────────────────────────────────
    const freshnessArr = Array.isArray(freshness) ? freshness : [];
    if (freshnessArr.length > 0) {
        const rows = freshnessArr.map(f => {
            const stale = f.is_stale;
            const badge = stale
                ? renderBadge('Stale', 'warning', 'sm')
                : renderBadge('Fresh', 'success', 'sm');
            const relTime = formatRelative(f.last_fetched);
            return `
            <div class="flex items-center justify-between py-1 border-b border-gray-100 last:border-0">
                <span class="text-xs text-gray-700 capitalize">${escapeHtml(f.source)}</span>
                <div class="flex items-center gap-2">
                    <span class="text-xs text-gray-400">${relTime}</span>
                    ${badge}
                </div>
            </div>`;
        }).join('');

        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Data Freshness</div>
            <div>${rows}</div>
        </div>`);
    }

    // ── Run History (last 5) ──────────────────────────────────────
    const runs = Array.isArray(pipelineRuns) ? pipelineRuns.slice(0, 5) : [];
    if (runs.length > 0) {
        const rows = runs.map(run => {
            const tasks = run.tasks || [];
            const succeeded = tasks.filter(t => t.status === 'succeeded').length;
            const failed = tasks.filter(t => t.status === 'failed').length;
            const label = (run.status || '').replace(/_/g, ' ');
            const variant = runStatusBadgeVariant(run.status);
            const runType = (run.run_type || '').replace(/_/g, ' ');
            return `
            <div class="flex items-center justify-between py-1 border-b border-gray-100 last:border-0">
                <div class="flex items-center gap-2">
                    ${renderBadge(label, variant, 'sm')}
                    <span class="text-xs text-gray-600">${escapeHtml(runType)}</span>
                </div>
                <div class="flex items-center gap-3 text-xs text-gray-400">
                    <span>${succeeded}/${tasks.length} ok${failed > 0 ? ` ${failed}F` : ''}</span>
                    <span>${formatRelative(run.created_at)}</span>
                </div>
            </div>`;
        }).join('');

        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Run History</div>
            <div>${rows}</div>
        </div>`);
    }

    return `<div class="space-y-4">${parts.join('')}</div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    // Bind task list error toggles
    bindTaskList(container);

    // Rerun task buttons within the task list
    container.querySelectorAll('[data-rerun-task]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const taskName = btn.getAttribute('data-rerun-task');
            if (!state.latestRun) return;
            btn.disabled = true;
            btn.textContent = '...';
            try {
                await api.rerunTask(state.latestRun.id, taskName);
                showToast(`Rerunning ${taskName.replace(/_/g, ' ')}`, 'success');
                if (actions?.reload) actions.reload();
            } catch {
                showToast('Failed to rerun task', 'error');
                btn.disabled = false;
                btn.textContent = 'Rerun';
            }
        });
    });

    // Rerun Failed header button
    const rerunFailedBtn = container.querySelector('[data-action="rerun-failed-header"]');
    if (rerunFailedBtn) {
        rerunFailedBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!state.latestRun) return;
            rerunFailedBtn.disabled = true;
            rerunFailedBtn.textContent = 'Running...';
            const failedTasks = (state.latestRun.tasks || []).filter(t => t.status === 'failed');
            try {
                for (const task of failedTasks) {
                    await api.rerunTask(state.latestRun.id, task.task_name);
                }
                showToast(`Rerunning ${failedTasks.length} failed task(s)`, 'success');
                if (actions?.reload) actions.reload();
            } catch {
                showToast('Failed to rerun tasks', 'error');
                rerunFailedBtn.disabled = false;
                rerunFailedBtn.textContent = 'Rerun Failed';
            }
        });
    }
}
