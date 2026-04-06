/**
 * Section §7: Schools
 *
 * Shows LCPS official assigned schools (authoritative) with Zillow data
 * as supplementary info. Flags discrepancies — LCPS always wins.
 */

import { escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';

export const TITLE = 'Schools';
export const ID = 'schools';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(state) {
    // Expand when there's a discrepancy between LCPS and Zillow
    const xref = state.schoolCrossRef;
    if (xref?.mismatches?.length > 0) return true;
    if (xref?.boundary_change_warning) return true;
    return false;
}

export function getStateBadge(state) {
    const schools = _getSchools(state);
    const xref = state.schoolCrossRef;
    if (xref?.mismatches?.length > 0) return { label: 'Mismatch', variant: 'warning' };
    if (xref?.boundary_change_warning) return { label: 'Boundary Change', variant: 'critical' };
    if (schools.length > 0) return { label: 'Complete', variant: 'success' };
    return { label: 'Not run', variant: 'muted' };
}

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
    // Prefer LCPS data, fall back to Zillow
    if (state.lcpsSchools && state.lcpsSchools.length > 0) return state.lcpsSchools;
    const ld = state.listingData || {};
    const raw = ld.assigned_schools || ld.nearby_schools || state.schools || [];
    return Array.isArray(raw) ? raw : [];
}

function _getZillowSchools(state) {
    const ld = state.listingData || {};
    return ld.assigned_schools || ld.nearby_schools || [];
}

function ratingColor(r) { return r >= 8 ? 'text-green-600' : r >= 6 ? 'text-amber-600' : r >= 4 ? 'text-orange-600' : 'text-red-600'; }
function ratingBg(r) { return r >= 8 ? 'bg-green-50' : r >= 6 ? 'bg-amber-50' : r >= 4 ? 'bg-orange-50' : 'bg-red-50'; }
function ratingRing(r) { return r >= 8 ? 'ring-green-300' : r >= 6 ? 'ring-amber-300' : r >= 4 ? 'ring-orange-300' : 'ring-red-300'; }

function levelLabel(level) {
    if (!level) return 'School';
    const l = level.toLowerCase();
    if (l === 'elementary') return 'Elementary';
    if (l === 'middle') return 'Middle';
    if (l === 'high') return 'High';
    return level.charAt(0).toUpperCase() + level.slice(1);
}

function renderSchoolCard(school, mismatch) {
    const name = school.name || 'Unknown';
    const rating = school.rating;
    const level = school.level || '';
    const grades = school.grades || '';
    const distance = school.distance_mi ?? school.distance;
    const source = school._source || '';

    const ratingDisplay = rating != null
        ? `<div class="w-12 h-12 rounded-full ${ratingBg(rating)} ring-2 ${ratingRing(rating)} flex items-center justify-center">
               <span class="text-lg font-bold ${ratingColor(rating)}">${rating}</span>
           </div>`
        : `<div class="w-12 h-12 rounded-full bg-gray-100 ring-2 ring-gray-200 flex items-center justify-center">
               <span class="text-xs text-gray-400">N/A</span>
           </div>`;

    const details = [];
    if (grades) details.push(`<div class="flex justify-between"><span class="text-gray-500">Grades</span><span class="font-medium text-gray-700">${escapeHtml(grades)}</span></div>`);
    if (distance != null) details.push(`<div class="flex justify-between"><span class="text-gray-500">Distance</span><span class="font-medium text-gray-700">${Number(distance).toFixed(1)} mi</span></div>`);
    if (school.enrollment != null) details.push(`<div class="flex justify-between"><span class="text-gray-500">Enrollment</span><span class="font-medium text-gray-700">${Number(school.enrollment).toLocaleString()}</span></div>`);
    if (school.student_teacher_ratio != null) details.push(`<div class="flex justify-between"><span class="text-gray-500">Student:Teacher</span><span class="font-medium text-gray-700">${school.student_teacher_ratio}:1</span></div>`);

    const sourceBadge = source === 'lcps'
        ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">LCPS Official</span>'
        : source === 'zillow'
            ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-medium">Zillow</span>'
            : '';

    let mismatchHtml = '';
    if (mismatch) {
        mismatchHtml = `
        <div class="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs">
            <div class="font-medium text-amber-800">Zillow says: ${escapeHtml(mismatch.zillow_says)}</div>
            <div class="text-amber-600">LCPS is authoritative — Zillow may be outdated</div>
        </div>`;
    }

    const detailsHtml = details.length > 0
        ? `<div class="mt-2 pt-2 border-t border-gray-100 space-y-1 text-xs">${details.join('')}</div>`
        : '';

    return `
    <div class="p-3 bg-white border rounded">
        <div class="flex items-start gap-3">
            ${ratingDisplay}
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                    <span class="text-xs text-gray-400 uppercase tracking-wide">${escapeHtml(levelLabel(level))}</span>
                    ${sourceBadge}
                </div>
                <div class="text-sm font-medium text-gray-900 truncate" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
            </div>
        </div>
        ${detailsHtml}
        ${mismatchHtml}
    </div>`;
}

// ── Render ──────────────────────────────────────────────────────────

export function render(state) {
    const schools = _getSchools(state);
    const xref = state.schoolCrossRef;

    if (schools.length === 0) {
        return `
        <div class="text-xs text-gray-400 text-center py-6 bg-gray-50 rounded-lg">
            School data not available. Click County refresh to fetch LCPS school assignments.
        </div>`;
    }

    // Build mismatch lookup by level
    const mismatches = {};
    if (xref?.mismatches) {
        for (const m of xref.mismatches) {
            mismatches[m.level] = m;
        }
    }

    // Boundary change warning
    let boundaryHtml = '';
    if (xref?.boundary_change_warning) {
        boundaryHtml = `
        <div class="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700 mb-3">
            <span class="font-semibold">Boundary Change Alert:</span> School assignments may change in the future year. Verify with LCPS directly.
        </div>`;
    }

    // Normalize and tag source
    const normalized = schools.map(s => ({
        name: s.name || 'Unknown',
        rating: s.rating ?? null,
        level: s.level || '',
        grades: s.grades || '',
        distance_mi: s.distance_mi ?? s.distance ?? null,
        enrollment: s.enrollment ?? null,
        student_teacher_ratio: s.student_teacher_ratio ?? null,
        _source: s._source || '',
    }));

    const levels = ['elementary', 'middle', 'high'];
    const byLevel = {};
    for (const s of normalized) {
        const key = s.level.toLowerCase();
        if (!byLevel[key]) byLevel[key] = [];
        byLevel[key].push(s);
    }

    const ordered = [];
    for (const level of levels) {
        const pool = byLevel[level] || [];
        if (pool.length > 0) ordered.push(pool[0]);
    }
    for (const s of normalized) {
        if (!ordered.includes(s)) ordered.push(s);
    }

    const cards = ordered.map(s => {
        const level = s.level.toLowerCase();
        return renderSchoolCard(s, mismatches[level]);
    }).join('');

    return `
    ${boundaryHtml}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        ${cards}
    </div>`;
}

export function bind(container, state, actions) {
    // Schools section is read-only
}
