/**
 * Section §1: Summary + Next Actions
 *
 * Always visible (not collapsible). Shows quick take with recommendation badge,
 * unique features as blue pills, red flags as red pills, strengths as green pills,
 * and next actions as a compact checklist.
 */

import { escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Summary + Next Actions';
export const ID = 'summary-actions';
export const DEFAULT_EXPANDED = true; // always visible, never collapsed

export function shouldAutoExpand(_state) { return true; }

export function getStateBadge(state) {
    const { packet, latestRun } = state;
    if (packet?.quick_take) return { label: 'Complete', variant: 'success' };
    if (latestRun) return { label: 'Partial', variant: 'warning' };
    return { label: 'Not run', variant: 'not-run' };
}

export function headerExtra(_state) { return ''; }

// ── Helpers ────────────────────────────────────────────────────────

const PURSUE_CLASSES = {
    pursue: 'bg-green-100 text-green-700',
    maybe:  'bg-amber-100 text-amber-700',
    pass:   'bg-red-100 text-red-700',
};

const PILL_CLASSES = {
    feature:  'inline-block text-[11px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700',
    flag:     'inline-block text-[11px] px-2 py-0.5 rounded-full bg-red-100 text-red-700',
    strength: 'inline-block text-[11px] px-2 py-0.5 rounded-full bg-green-100 text-green-700',
};

function pill(text, type) {
    return `<span class="${PILL_CLASSES[type] || PILL_CLASSES.feature}">${escapeHtml(text)}</span>`;
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const { packet, listingData, analysisResults, latestRun } = state;
    const ld = listingData || {};

    // No data at all
    if (!packet && !latestRun && !ld.price) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">Run pipeline to generate summary</p>
        </div>`;
    }

    const parts = [];

    // ── Quick Take ─────────────────────────────────────────────────
    if (packet?.quick_take) {
        const qt = packet.quick_take;
        const rec = qt.recommendation || '';
        const cls = PURSUE_CLASSES[rec] || 'bg-gray-100 text-gray-500';
        const bullets = (qt.bullets || [])
            .map(b => `<li class="text-xs text-ink-600 leading-snug flex gap-1.5"><span class="text-ink-300 shrink-0">&mdash;</span><span>${escapeHtml(b)}</span></li>`)
            .join('');

        parts.push(`
        <div>
            <div class="flex items-center gap-2.5 mb-2">
                <span class="text-[11px] text-gray-500 uppercase tracking-wide">Quick Take</span>
                <span class="inline-block text-[11px] font-bold uppercase px-2 py-0.5 rounded tracking-wide ${cls}">${rec}</span>
            </div>
            ${bullets ? `<ul class="space-y-0.5">${bullets}</ul>` : ''}
        </div>`);
    }

    // ── Unique Features (blue pills) ──────────────────────────────
    const upgrades = analysisResults?.ai_extraction?.upgrades || [];
    const communityNotes = packet?.community_view?.community_notes || [];
    // Deduplicate: use upgrades first, fall back to community notes for features
    const features = upgrades.length > 0 ? upgrades : [];
    if (features.length > 0) {
        const pills = features.map(f => pill(f, 'feature')).join(' ');
        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Features</div>
            <div class="flex flex-wrap gap-1">${pills}</div>
        </div>`);
    }

    // ── Red Flags (red pills) ─────────────────────────────────────
    const unknowns = packet?.hidden_cost?.unknowns || [];
    if (unknowns.length > 0) {
        const pills = unknowns.map(u => pill(u, 'flag')).join(' ');
        parts.push(`
        <div>
            <div class="text-xs font-semibold text-red-600 uppercase tracking-wide mb-1">Red Flags</div>
            <div class="flex flex-wrap gap-1">${pills}</div>
        </div>`);
    }

    // ── Strengths (green pills) ───────────────────────────────────
    if (communityNotes.length > 0) {
        const pills = communityNotes.map(n => pill(n, 'strength')).join(' ');
        parts.push(`
        <div>
            <div class="text-xs font-semibold text-green-600 uppercase tracking-wide mb-1">Strengths</div>
            <div class="flex flex-wrap gap-1">${pills}</div>
        </div>`);
    }

    // ── Next Actions (compact checklist) ──────────────────────────
    const actions = [];

    // From latest run warnings
    if (latestRun) {
        const failedTasks = (latestRun.tasks || []).filter(t => t.status === 'failed');
        if (failedTasks.length > 0) {
            actions.push(`${failedTasks.length} pipeline task(s) failed — check Pipeline Health`);
        }
    }

    // Missing data — only show if data is truly absent (not just loading)
    const hasCounty = !!(state.countyData && Object.keys(state.countyData).length > 0);
    const hasComps = !!(state.quickComp || state.deepComp);

    if (!latestRun) actions.push('Run pipeline to analyze this property');
    if (!ld.price) actions.push('No list price — add via Financial tab or re-scrape');
    if (!hasCounty && latestRun) actions.push('No county data — run county refresh');
    if (!hasComps && latestRun) actions.push('No comp analysis — run Quick Comp');

    // Warnings from packet
    const packetWarnings = packet?.warning_engine?.warnings || [];
    packetWarnings.forEach(w => {
        const msg = typeof w === 'string' ? w : (w.message || w.text || '');
        if (msg) actions.push(msg);
    });

    if (actions.length > 0) {
        const items = actions
            .map(a => `<li class="text-xs text-amber-700 flex gap-1.5 leading-snug"><span class="shrink-0">&rarr;</span><span>${escapeHtml(a)}</span></li>`)
            .join('');
        parts.push(`
        <div>
            <div class="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-1">Next Actions</div>
            <ul class="space-y-0.5">${items}</ul>
        </div>`);
    }

    if (parts.length === 0) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">Run pipeline to generate summary</p>
        </div>`;
    }

    return `<div class="space-y-3">${parts.join('')}</div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(_container, _state, _actions) {
    // Summary section is read-only, no interactive elements.
}
