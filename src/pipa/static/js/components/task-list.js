/**
 * Task list component — per-task rows with status dots, name, duration,
 * retry count badge, expandable error details, rerun button.
 */

import { renderBadge } from './badge.js';

const STATUS_DOT = {
    succeeded: 'bg-green-500',
    failed:    'bg-red-500',
    running:   'bg-blue-500 animate-pulse',
    pending:   'bg-gray-300',
    queued:    'bg-gray-300',
    skipped:   'bg-gray-200',
};

function dotClass(status) {
    return STATUS_DOT[status] || 'bg-gray-300';
}

function formatDuration(ms) {
    if (!ms && ms !== 0) return '--';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
}

function formatTaskName(name) {
    return name
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

function statusVariant(status) {
    if (status === 'succeeded') return 'success';
    if (status === 'failed') return 'critical';
    if (status === 'running') return 'info';
    return 'muted';
}

/**
 * Render a list of pipeline task rows.
 * @param {Array}    tasks        - Array of task objects.
 * @param {boolean}  showRerun    - Whether to show rerun buttons for failed tasks.
 * @returns {string} HTML string
 */
export function renderTaskList(tasks, showRerun = false) {
    if (!tasks || tasks.length === 0) {
        return '<div class="text-sm text-gray-500">No tasks in this run.</div>';
    }

    const rows = tasks.map(task => {
        const retryBadge = task.retry_count > 0
            ? renderBadge(`${task.retry_count} retries`, 'warning', 'sm')
            : '';

        const rerunBtn = (task.status === 'failed' && showRerun)
            ? `<button data-rerun-task="${esc(task.task_name)}" class="px-2 py-1 text-xs font-medium text-red-600 border border-red-200 rounded hover:bg-red-50">Rerun</button>`
            : '';

        const detailsBtn = task.error_details
            ? `<button data-toggle-error="${esc(task.id)}" class="text-xs text-gray-400 hover:text-gray-600">Details</button>`
            : '';

        const errorPanel = task.error_details
            ? `<div id="error-${esc(task.id)}" class="hidden mt-2 ml-5 p-2 bg-red-50 rounded text-xs text-red-700 font-mono whitespace-pre-wrap break-all">${esc(task.error_details)}</div>`
            : '';

        return `
        <div class="bg-white border border-gray-200 rounded-lg px-4 py-2.5">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3 min-w-0 flex-1">
                    <div class="w-2.5 h-2.5 rounded-full flex-shrink-0 ${dotClass(task.status)}"></div>
                    <span class="text-sm font-medium text-gray-900 truncate">${esc(formatTaskName(task.task_name))}</span>
                    ${retryBadge}
                </div>
                <div class="flex items-center gap-3 flex-shrink-0">
                    <span class="text-xs text-gray-500">${formatDuration(task.duration_ms)}</span>
                    ${renderBadge(task.status, statusVariant(task.status), 'sm')}
                    ${rerunBtn}
                    ${detailsBtn}
                </div>
            </div>
            ${errorPanel}
        </div>`;
    });

    return `<div class="space-y-1">${rows.join('')}</div>`;
}

/**
 * Bind toggle handlers for error detail panels.
 * @param {HTMLElement} container - Parent container after innerHTML is set.
 */
export function bindTaskList(container) {
    container.querySelectorAll('[data-toggle-error]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.getAttribute('data-toggle-error');
            const panel = container.querySelector(`#error-${id}`);
            if (panel) {
                panel.classList.toggle('hidden');
                btn.textContent = panel.classList.contains('hidden') ? 'Details' : 'Hide';
            }
        });
    });
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
