/**
 * Section §7: Schools
 *
 * Three school cards (elementary, middle, high) with ratings, distance,
 * enrollment, student:teacher ratio. Average rating badge in header.
 */

import { escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';

export const TITLE = 'Schools';
export const ID = 'schools';
export const DEFAULT_EXPANDED = false;

// ── Auto-expand ────────────────────────────────────────────────────

export function shouldAutoExpand(state) {
    return false;
}

// ── State badge ────────────────────────────────────────────────────

export function getStateBadge(state) {
    const schools = _getSchools(state);
    if (schools.length > 0) return { label: 'Complete', variant: 'success' };
    return { label: 'Not run', variant: 'muted' };
}

// ── Header extra: average rating badge ─────────────────────────────

export function headerExtra(state) {
    const schools = _getSchools(state);
    const rated = schools.filter(s => s.rating != null && s.rating > 0);
    if (rated.length === 0) return '';

    const avg = rated.reduce((sum, s) => sum + s.rating, 0) / rated.length;
    const variant = avg >= 8 ? 'success' : avg >= 6 ? 'warning' : 'critical';

    return renderBadge(`Avg ${avg.toFixed(1)}/10`, variant, 'sm');
}

// ── Helpers ────────────────────────────────────────────────────────

function _getSchools(state) {
    const ld = state.listingData || {};
    const raw = ld.assigned_schools || ld.nearby_schools || state.schools || [];
    return Array.isArray(raw) ? raw : [];
}

function ratingColor(rating) {
    if (rating == null) return 'text-gray-400';
    if (rating >= 8) return 'text-green-600';
    if (rating >= 6) return 'text-amber-600';
    if (rating >= 4) return 'text-orange-600';
    return 'text-red-600';
}

function ratingBg(rating) {
    if (rating == null) return 'bg-gray-50';
    if (rating >= 8) return 'bg-green-50';
    if (rating >= 6) return 'bg-amber-50';
    if (rating >= 4) return 'bg-orange-50';
    return 'bg-red-50';
}

function ratingRingColor(rating) {
    if (rating == null) return 'ring-gray-200';
    if (rating >= 8) return 'ring-green-300';
    if (rating >= 6) return 'ring-amber-300';
    if (rating >= 4) return 'ring-orange-300';
    return 'ring-red-300';
}

function levelLabel(level) {
    if (!level) return 'School';
    const l = level.toLowerCase();
    if (l === 'elementary') return 'Elementary';
    if (l === 'middle') return 'Middle';
    if (l === 'high') return 'High';
    return level.charAt(0).toUpperCase() + level.slice(1);
}

function renderSchoolCard(school) {
    const name = school.name || 'Unknown';
    const rating = school.rating;
    const level = school.level || '';
    const grades = school.grades || '';
    const distance = school.distance_mi ?? school.distance;
    const enrollment = school.enrollment;
    const ratio = school.student_teacher_ratio;

    const ratingDisplay = rating != null
        ? `<div class="w-12 h-12 rounded-full ${ratingBg(rating)} ring-2 ${ratingRingColor(rating)} flex items-center justify-center">
               <span class="text-lg font-bold ${ratingColor(rating)}">${rating}</span>
           </div>`
        : `<div class="w-12 h-12 rounded-full bg-gray-100 ring-2 ring-gray-200 flex items-center justify-center">
               <span class="text-xs text-gray-400">N/A</span>
           </div>`;

    const details = [];
    if (grades) {
        details.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Grades</span>
                <span class="font-medium text-gray-700">${escapeHtml(grades)}</span>
            </div>`);
    }
    if (distance != null) {
        details.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Distance</span>
                <span class="font-medium text-gray-700">${Number(distance).toFixed(1)} mi</span>
            </div>`);
    }
    if (enrollment != null) {
        details.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Enrollment</span>
                <span class="font-medium text-gray-700">${Number(enrollment).toLocaleString()}</span>
            </div>`);
    }
    if (ratio != null) {
        details.push(`
            <div class="flex justify-between">
                <span class="text-gray-500">Student:Teacher</span>
                <span class="font-medium text-gray-700">${ratio}:1</span>
            </div>`);
    }

    const detailsHtml = details.length > 0
        ? `<div class="mt-2 pt-2 border-t border-gray-100 space-y-1 text-xs">${details.join('')}</div>`
        : '';

    return `
    <div class="p-3 bg-white border rounded">
        <div class="flex items-start gap-3">
            ${ratingDisplay}
            <div class="flex-1 min-w-0">
                <div class="text-xs text-gray-400 uppercase tracking-wide">${escapeHtml(levelLabel(level))}</div>
                <div class="text-sm font-medium text-gray-900 truncate" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
            </div>
        </div>
        ${detailsHtml}
    </div>`;
}

// ── Render ──────────────────────────────────────────────────────────

export function render(state) {
    const schools = _getSchools(state);

    if (schools.length === 0) {
        return `
        <div class="text-xs text-gray-400 text-center py-6 bg-gray-50 rounded-lg">
            School data not available. Run the pipeline to fetch school information.
        </div>`;
    }

    // Normalize school objects
    const normalized = schools.map(s => ({
        name: s.name || 'Unknown',
        rating: s.rating ?? null,
        level: s.level || '',
        grades: s.grades || '',
        distance_mi: s.distance_mi ?? s.distance ?? null,
        enrollment: s.enrollment ?? null,
        student_teacher_ratio: s.student_teacher_ratio ?? null,
        assigned: s.assigned,
    }));

    // Try to show one per level in order: elementary, middle, high
    const levels = ['elementary', 'middle', 'high'];
    const byLevel = {};
    for (const s of normalized) {
        const key = s.level.toLowerCase();
        if (!byLevel[key]) byLevel[key] = [];
        byLevel[key].push(s);
    }

    // Build ordered cards: assigned levels first, then extras
    const ordered = [];
    const used = new Set();
    for (const level of levels) {
        const pool = byLevel[level] || [];
        if (pool.length > 0) {
            ordered.push(pool[0]);
            used.add(pool[0]);
        }
    }
    // Add any remaining schools not yet shown
    for (const s of normalized) {
        if (!used.has(s)) ordered.push(s);
    }

    const cards = ordered.map(s => renderSchoolCard(s)).join('');

    return `
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${cards}
    </div>`;
}

// ── Bind ────────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    // Schools section is read-only
}
