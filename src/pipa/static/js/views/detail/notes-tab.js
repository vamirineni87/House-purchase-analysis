/**
 * Notes & Due Diligence tab — add note form (textarea + type selector + submit),
 * note list with type badges and delete buttons.
 * Due diligence section (placeholder for future).
 */

import { api } from '../../api.js';
import { formatDate, escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';
import { showToast } from '../../toast.js';

const NOTE_TYPES = ['general', 'showing', 'concern', 'positive', 'question'];

function noteTypeVariant(type) {
    switch (type) {
        case 'concern':  return 'warning';
        case 'positive': return 'success';
        case 'showing':  return 'info';
        case 'question': return 'warning';
        default:         return 'muted';
    }
}

let _local = {
    newContent: '',
    newType: 'general',
};

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const notes = state.notes || [];

    // Type options
    const typeOptions = NOTE_TYPES.map(t => {
        const sel = _local.newType === t ? 'selected' : '';
        return `<option value="${t}" ${sel}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`;
    }).join('');

    // Add note form
    const formHtml = `
    <div class="bg-white border border-gray-200 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">Add Note</h3>
        <textarea id="note-content" placeholder="Write a note about this property..." rows="3" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 mb-2">${escapeHtml(_local.newContent)}</textarea>
        <div class="flex items-center justify-between">
            <select id="note-type" class="text-sm border border-gray-300 rounded px-2 py-1">${typeOptions}</select>
            <button id="note-submit" class="px-4 py-1.5 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50" ${!_local.newContent.trim() ? 'disabled' : ''}>Add Note</button>
        </div>
    </div>`;

    // Notes list
    let notesListHtml;
    if (notes.length === 0) {
        notesListHtml = '<div class="text-gray-500 text-sm text-center py-8">No notes yet.</div>';
    } else {
        const cards = notes.map(note => `
        <div class="bg-white border border-gray-200 rounded-lg p-4">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <p class="text-sm text-gray-900 whitespace-pre-wrap">${escapeHtml(note.content)}</p>
                    <div class="flex items-center gap-2 mt-2">
                        ${renderBadge(note.note_type, noteTypeVariant(note.note_type))}
                        <span class="text-xs text-gray-400">${formatDate(note.created_at)}</span>
                    </div>
                </div>
                <button data-delete-note="${escapeHtml(note.id)}" class="text-gray-400 hover:text-red-500 ml-2 text-sm" title="Delete note">x</button>
            </div>
        </div>`).join('');

        notesListHtml = `<div class="space-y-2">${cards}</div>`;
    }

    // Due diligence placeholder
    const ddHtml = `
    <div class="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-2">Due Diligence Checklist</h3>
        <div class="space-y-2 text-sm text-gray-500">
            <div class="flex items-center gap-2">
                <input type="checkbox" disabled class="rounded border-gray-300" />
                <span>Home inspection scheduled</span>
            </div>
            <div class="flex items-center gap-2">
                <input type="checkbox" disabled class="rounded border-gray-300" />
                <span>Radon test ordered</span>
            </div>
            <div class="flex items-center gap-2">
                <input type="checkbox" disabled class="rounded border-gray-300" />
                <span>Title search complete</span>
            </div>
            <div class="flex items-center gap-2">
                <input type="checkbox" disabled class="rounded border-gray-300" />
                <span>HOA docs reviewed</span>
            </div>
            <div class="flex items-center gap-2">
                <input type="checkbox" disabled class="rounded border-gray-300" />
                <span>Appraisal ordered</span>
            </div>
        </div>
        <p class="text-xs text-gray-400 mt-2">Due diligence tracking coming in a future update.</p>
    </div>`;

    container.innerHTML = `
    <div class="space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">Notes & Due Diligence</h2>
        ${formHtml}
        ${notesListHtml}
        ${ddHtml}
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container, state, actions) {
    // Track content changes
    const contentEl = container.querySelector('#note-content');
    const typeEl = container.querySelector('#note-type');
    const submitBtn = container.querySelector('#note-submit');

    if (contentEl) {
        contentEl.addEventListener('input', () => {
            _local.newContent = contentEl.value;
            if (submitBtn) submitBtn.disabled = !_local.newContent.trim();
        });
    }

    if (typeEl) {
        typeEl.addEventListener('change', () => {
            _local.newType = typeEl.value;
        });
    }

    // Submit note
    if (submitBtn) {
        submitBtn.addEventListener('click', async () => {
            const content = _local.newContent.trim();
            if (!content) return;

            submitBtn.disabled = true;
            try {
                await api.createNote(state.propertyId, {
                    content,
                    note_type: _local.newType,
                });
                _local.newContent = '';
                _local.newType = 'general';
                // Reload notes
                state.notes = await api.listNotes(state.propertyId);
                showToast('Note added', 'success');
                if (actions?.reload) actions.reload();
            } catch {
                showToast('Failed to add note', 'error');
                submitBtn.disabled = false;
            }
        });
    }

    // Delete note buttons
    container.querySelectorAll('[data-delete-note]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const noteId = btn.getAttribute('data-delete-note');
            try {
                await api.deleteNote(state.propertyId, noteId);
                state.notes = state.notes.filter(n => n.id !== noteId);
                showToast('Note deleted', 'success');
                if (actions?.reload) actions.reload();
            } catch {
                showToast('Failed to delete note', 'error');
            }
        });
    });
}
