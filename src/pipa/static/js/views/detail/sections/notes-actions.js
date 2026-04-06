/**
 * Section §12: Notes & Due Diligence.
 *
 * Add note form (textarea + type dropdown + submit), note list with
 * type badges and delete buttons, due diligence placeholder.
 */

import { formatDate, escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { showToast } from '../../../toast.js';
import { api } from '../../../api.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Notes & Due Diligence';
export const ID = 'notes-actions';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(_state) { return false; }

export function getStateBadge(_state) {
    return { label: 'Complete', variant: 'success' };
}

export function headerExtra(state) {
    const notes = state.notes || [];
    if (notes.length === 0) return '';
    return renderBadge(String(notes.length), 'info', 'sm');
}

// ── Helpers ────────────────────────────────────────────────────────

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

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const notes = state.notes || [];

    // Type dropdown options
    const typeOptions = NOTE_TYPES.map(t =>
        `<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
    ).join('');

    // Add note form — compact single row
    const formHtml = `
    <div class="bg-white border border-gray-200 rounded-lg p-3">
        <div class="flex gap-2 items-end">
            <textarea id="section-note-content" placeholder="Write a note..." rows="2"
                class="flex-1 border border-gray-300 rounded px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"></textarea>
            <div class="flex flex-col gap-1.5 shrink-0">
                <select id="section-note-type" class="text-xs border border-gray-300 rounded px-2 py-1">
                    ${typeOptions}
                </select>
                <button id="section-note-submit"
                    class="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
                    disabled>Add</button>
            </div>
        </div>
    </div>`;

    // Notes list
    let notesListHtml;
    if (notes.length === 0) {
        notesListHtml = '<p class="text-xs text-gray-500 text-center py-4">No notes yet.</p>';
    } else {
        const cards = notes.map(note => `
        <div class="flex items-start gap-2 bg-white border border-gray-200 rounded-lg p-2.5 group">
            <div class="flex-1 min-w-0">
                <p class="text-xs text-gray-900 whitespace-pre-wrap leading-snug">${escapeHtml(note.content)}</p>
                <div class="flex items-center gap-1.5 mt-1">
                    ${renderBadge(note.note_type || 'general', noteTypeVariant(note.note_type), 'sm')}
                    <span class="text-xs text-gray-400">${formatDate(note.created_at)}</span>
                </div>
            </div>
            <button class="note-delete-btn shrink-0 text-gray-300 hover:text-red-500 transition-colors text-sm leading-none opacity-0 group-hover:opacity-100"
                data-note-id="${escapeHtml(String(note.id))}" title="Delete note">&times;</button>
        </div>`).join('');

        notesListHtml = `<div class="space-y-1.5">${cards}</div>`;
    }

    // Due diligence placeholder
    const ddHtml = `
    <div class="bg-gray-50 border border-gray-200 rounded-lg p-3">
        <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Due Diligence</div>
        <p class="text-xs text-gray-400">Due diligence checklist coming soon.</p>
    </div>`;

    return `
    <div class="space-y-3">
        ${formHtml}
        ${notesListHtml}
        ${ddHtml}
    </div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    const contentEl = container.querySelector('#section-note-content');
    const typeEl = container.querySelector('#section-note-type');
    const submitBtn = container.querySelector('#section-note-submit');

    // Enable/disable submit based on content
    if (contentEl && submitBtn) {
        contentEl.addEventListener('input', () => {
            submitBtn.disabled = !contentEl.value.trim();
        });
    }

    // Submit note
    if (submitBtn) {
        submitBtn.addEventListener('click', async () => {
            const content = contentEl?.value?.trim();
            if (!content) return;

            submitBtn.disabled = true;
            const noteType = typeEl?.value || 'general';

            try {
                await api.createNote(state.property.id, {
                    content,
                    note_type: noteType,
                });

                // Clear form
                if (contentEl) contentEl.value = '';

                // Reload notes
                state.notes = await api.listNotes(state.property.id);
                showToast('Note added', 'success');
                if (actions?.rerenderSection) {
                    actions.rerenderSection(ID);
                } else if (actions?.reload) {
                    actions.reload();
                }
            } catch (err) {
                showToast('Failed to add note: ' + (err.message || 'unknown'), 'error');
                submitBtn.disabled = false;
            }
        });
    }

    // Delete note buttons
    container.querySelectorAll('.note-delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const noteId = btn.getAttribute('data-note-id');
            if (!noteId) return;

            try {
                await api.deleteNote(state.property.id, noteId);
                state.notes = (state.notes || []).filter(n => String(n.id) !== noteId);
                showToast('Note deleted', 'success');
                if (actions?.rerenderSection) {
                    actions.rerenderSection(ID);
                } else if (actions?.reload) {
                    actions.reload();
                }
            } catch (err) {
                showToast('Failed to delete note: ' + (err.message || 'unknown'), 'error');
            }
        });
    });
}
