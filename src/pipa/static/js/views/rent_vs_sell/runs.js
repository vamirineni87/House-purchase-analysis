/**
 * Rent vs Sell — saved runs drawer.
 *
 * Lists saved runs, load on click, duplicate/delete buttons, checkbox
 * selection for compare mode.
 */

import { escapeHtml } from '../../utils.js';

export function renderSavedRunsDrawer(state) {
    const runs = state.savedRuns || [];
    if (runs.length === 0) {
        return `<div class="bg-white border border-gray-200 rounded-lg p-3 mb-4 text-xs text-gray-400">No saved runs yet.</div>`;
    }
    const rows = runs.map(r => `
        <div class="flex items-center justify-between px-3 py-2 border-b border-gray-100">
            <div class="flex items-center gap-2">
                <input type="checkbox" data-rvs-compare-id="${escapeHtml(r.id)}" class="rvs-compare-cb" />
                <a href="#rent-vs-sell?run_id=${encodeURIComponent(r.id)}" class="text-sm text-blue-600 hover:underline">${escapeHtml(r.name)}</a>
                <span class="text-[10px] text-gray-400">${escapeHtml(r.scenario_label)}</span>
                ${r.summary_json?.lean ? `<span class="text-[10px] text-gray-500">${escapeHtml(r.summary_json.lean)}</span>` : ''}
            </div>
            <div class="flex items-center gap-2">
                <button data-rvs-duplicate-id="${escapeHtml(r.id)}" class="text-[10px] text-gray-500 hover:text-gray-800">Duplicate</button>
                <button data-rvs-delete-id="${escapeHtml(r.id)}" class="text-[10px] text-red-500 hover:text-red-700">Delete</button>
            </div>
        </div>`).join('');
    return `
    <div class="bg-white border border-gray-200 rounded-lg mb-4">
        <div class="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
            <div class="text-xs font-semibold text-gray-700 uppercase">Saved runs</div>
            <button id="rvs-compare-selected" class="text-xs px-2 py-1 bg-gray-100 border border-gray-300 rounded hover:bg-gray-200">Compare selected</button>
        </div>
        ${rows}
    </div>`;
}

export function bindSavedRuns(container, state, handlers) {
    const { onDuplicate, onDelete, onCompareSelected } = handlers;
    container.querySelectorAll('[data-rvs-duplicate-id]').forEach(btn => {
        btn.addEventListener('click', () => onDuplicate(btn.dataset.rvsDuplicateId));
    });
    container.querySelectorAll('[data-rvs-delete-id]').forEach(btn => {
        btn.addEventListener('click', () => onDelete(btn.dataset.rvsDeleteId));
    });
    const compareBtn = container.querySelector('#rvs-compare-selected');
    if (compareBtn) {
        compareBtn.addEventListener('click', () => {
            const checked = Array.from(container.querySelectorAll('.rvs-compare-cb:checked'))
                .map(cb => cb.dataset.rvsCompareId);
            onCompareSelected(checked);
        });
    }
}
