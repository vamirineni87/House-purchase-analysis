/**
 * Run status ribbon — shows status badge, task counts, failed task names, retry button.
 */

import { renderBadge, runStatusBadgeVariant } from './badge.js';

/**
 * Render a pipeline run status ribbon.
 * @param {object}   run          - Pipeline run object (with .status, .tasks, .run_type)
 * @param {object}   options      - { onRetry?: boolean, onRunPipeline?: boolean }
 * @returns {string} HTML string
 */
export function renderRunStatusRibbon(run, options = {}) {
    if (!run) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between">
            <span class="text-sm text-gray-500">No pipeline has been run yet.</span>
            ${options.onRunPipeline ? '<button data-action="run-pipeline" class="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700">Run Full Pipeline</button>' : ''}
        </div>`;
    }

    const tasks = run.tasks || [];
    const succeeded = tasks.filter(t => t.status === 'succeeded').length;
    const failed = tasks.filter(t => t.status === 'failed').length;
    const running = tasks.filter(t => t.status === 'running').length;
    const pending = tasks.filter(t => t.status === 'pending' || t.status === 'queued').length;
    const total = tasks.length;
    const failedNames = tasks
        .filter(t => t.status === 'failed')
        .map(t => t.task_name.replace(/_/g, ' '));

    const statusLabel = run.status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const statusBadge = renderBadge(statusLabel, runStatusBadgeVariant(run.status), 'md');

    let countsHtml = `${succeeded}/${total} tasks succeeded`;
    if (failed > 0) countsHtml += `<span class="text-red-600 ml-1">, ${failed} failed</span>`;
    if (running > 0) countsHtml += `<span class="text-blue-600 ml-1">, ${running} running</span>`;
    if (pending > 0) countsHtml += `<span class="text-gray-400 ml-1">, ${pending} pending</span>`;

    let buttonsHtml = '';
    if (failed > 0 && options.onRetry) {
        buttonsHtml += '<button data-action="retry-failed" class="px-3 py-1.5 text-xs font-medium text-white bg-red-600 rounded hover:bg-red-700">Retry Failed</button>';
    }
    if (options.onRunPipeline) {
        buttonsHtml += '<button data-action="run-pipeline" class="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700">Run Full Pipeline</button>';
    }

    const failedNamesHtml = failedNames.length > 0
        ? `<div class="mt-2 text-xs text-red-600">Failed: ${esc(failedNames.join(', '))}</div>`
        : '';

    const progressHtml = run.status === 'running'
        ? `<div class="mt-2"><div class="w-full bg-gray-100 rounded-full h-1.5"><div class="bg-blue-500 h-1.5 rounded-full transition-all animate-pulse" style="width:${total > 0 ? ((succeeded + failed) / total) * 100 : 0}%"></div></div></div>`
        : '';

    return `
    <div class="bg-white border border-gray-200 rounded-lg px-4 py-3">
        <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-3">
                ${statusBadge}
                <span class="text-sm text-gray-600">${countsHtml}</span>
            </div>
            <div class="flex items-center gap-2">${buttonsHtml}</div>
        </div>
        ${failedNamesHtml}
        ${progressHtml}
    </div>`;
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
