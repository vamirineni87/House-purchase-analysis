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

// Normalize a school name for fuzzy matching: strip level words AND
// their abbreviations, punctuation, lowercase, collapse spaces.
// LCPS uses "Pinebrook ES" / "Willard MS" / "Lightridge HS";
// Zillow uses "Pinebrook Elementary School" — both must collapse to
// "pinebrook" / "willard" / "lightridge" to match.
function _normSchoolName(name) {
    if (!name) return '';
    return String(name)
        .toLowerCase()
        .replace(/[^a-z0-9 ]/g, ' ')
        .replace(/\b(elementary|middle|high|junior|senior|primary|intermediate|school|es|ms|hs|jhs|shs|jrhs|srhs)\b/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

// Normalize a school level so "elementary" / "Elementary" / "ES" all
// collapse to the same canonical bucket. Used in the merge key so
// "Willard ES" and "Willard HS" don't accidentally match each other
// just because the normalizer strips the level.
function _normSchoolLevel(level) {
    if (!level) return '';
    const l = String(level).toLowerCase().trim();
    if (l === 'es' || l.startsWith('elem')) return 'elementary';
    if (l === 'ms' || l.startsWith('mid')) return 'middle';
    if (l === 'hs' || l.startsWith('high')) return 'high';
    return l;
}

// Build a composite match key. Same name at different levels (e.g. a
// district that has both "Willard Elementary" and "Willard High") must
// stay distinct or the merge will paste high-school ratings onto the
// elementary school card.
function _schoolMatchKey(name, level) {
    const n = _normSchoolName(name);
    if (!n) return '';
    const l = _normSchoolLevel(level);
    return `${n}|${l}`;
}

function _getSchools(state) {
    const ld = state.listingData || {};
    const zillowSchools = Array.isArray(ld.assigned_schools) && ld.assigned_schools.length > 0
        ? ld.assigned_schools
        : (Array.isArray(ld.nearby_schools) ? ld.nearby_schools : []);
    const lcpsSchools = Array.isArray(state.lcpsSchools) ? state.lcpsSchools : [];

    // Index Zillow by (normalized name + level) so same-name schools at
    // different levels don't merge into one row, and so we can track
    // which Zillow rows have been consumed by an LCPS match.
    const zillowByKey = {};
    for (const z of zillowSchools) {
        const k = _schoolMatchKey(z.name, z.level);
        if (k) zillowByKey[k] = z;
    }
    const consumed = new Set();

    const out = [];

    // 1. LCPS schools first (boundary-authoritative). Merge in Zillow's
    //    score fields by (name, level) match.
    for (const lcps of lcpsSchools) {
        const k = _schoolMatchKey(lcps.name, lcps.level);
        const z = zillowByKey[k] || {};
        if (k && zillowByKey[k]) consumed.add(k);
        out.push({
            ...z,            // pull in scores/enrollment/links from Zillow
            ...lcps,         // LCPS overrides for name/principal/level/address
            _source: 'lcps',
            rating: lcps.rating ?? z.rating ?? null,
            grades: lcps.grades || z.grades || '',
            level: lcps.level || z.level || '',
            distance_mi: lcps.distance_mi ?? z.distance_mi ?? null,
            enrollment: lcps.enrollment ?? z.enrollment ?? null,
            student_teacher_ratio: lcps.student_teacher_ratio ?? z.student_teacher_ratio ?? null,
            student_counselor_ratio: lcps.student_counselor_ratio ?? z.student_counselor_ratio ?? null,
            pct_certified_teachers: lcps.pct_certified_teachers ?? z.pct_certified_teachers ?? null,
            greatschools_link: lcps.greatschools_link || z.greatschools_link || null,
        });
    }

    // 2. Zillow schools that weren't matched to any LCPS row. These
    //    might be boundary mismatches (different school assigned by
    //    Zillow vs LCPS) or nearby/non-assigned schools.
    for (const z of zillowSchools) {
        const k = _schoolMatchKey(z.name, z.level);
        if (k && consumed.has(k)) continue;
        out.push({ ...z, _source: 'zillow' });
    }

    // 3. Fallback: if neither source has data, try state.schools (legacy field)
    if (out.length === 0 && Array.isArray(state.schools)) {
        return state.schools.map(s => ({ ...s, _source: s._source || 'zillow' }));
    }

    return out;
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

    // Big score circle + text label so the rating is unambiguous.
    let ratingDisplay;
    if (rating != null && rating > 0) {
        const label = rating >= 8 ? 'Above Avg' : rating >= 6 ? 'Average' : rating >= 4 ? 'Below Avg' : 'Low';
        ratingDisplay = `
        <div class="flex flex-col items-center">
            <div class="w-14 h-14 rounded-full ${ratingBg(rating)} ring-2 ${ratingRing(rating)} flex items-center justify-center">
                <span class="text-xl font-bold ${ratingColor(rating)}">${rating}</span>
            </div>
            <div class="text-[10px] text-gray-500 mt-0.5">${label}</div>
            <div class="text-[9px] text-gray-400">/10 GS</div>
        </div>`;
    } else {
        ratingDisplay = `
        <div class="flex flex-col items-center">
            <div class="w-14 h-14 rounded-full bg-gray-100 ring-2 ring-gray-200 flex items-center justify-center">
                <span class="text-xs text-gray-400">N/A</span>
            </div>
            <div class="text-[9px] text-gray-400 mt-0.5">No score</div>
        </div>`;
    }

    const details = [];
    const detailRow = (lbl, val) =>
        `<div class="flex justify-between"><span class="text-gray-500">${lbl}</span><span class="font-medium text-gray-700">${val}</span></div>`;

    if (grades) details.push(detailRow('Grades', escapeHtml(grades)));
    if (distance != null) details.push(detailRow('Distance', `${Number(distance).toFixed(1)} mi`));
    if (school.enrollment != null) details.push(detailRow('Enrollment', Number(school.enrollment).toLocaleString()));
    if (school.student_teacher_ratio != null) details.push(detailRow('Student:Teacher', `${school.student_teacher_ratio}:1`));
    if (school.student_counselor_ratio != null) details.push(detailRow('Student:Counselor', `${school.student_counselor_ratio}:1`));
    if (school.pct_certified_teachers != null) {
        const pct = Number(school.pct_certified_teachers);
        const display = pct <= 1 ? `${Math.round(pct * 100)}%` : `${Math.round(pct)}%`;
        details.push(detailRow('Certified Teachers', display));
    }
    if (school.principal) details.push(detailRow('Principal', escapeHtml(school.principal)));
    if (school.greatschools_link) {
        const url = school.greatschools_link.startsWith('http')
            ? school.greatschools_link
            : `https://www.greatschools.org${school.greatschools_link}`;
        details.push(`<div class="pt-1"><a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="text-[11px] text-blue-600 hover:underline">View on GreatSchools →</a></div>`);
    }

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

    // Normalize and tag source. Carry through all the score-adjacent
    // fields so the card can show them.
    const normalized = schools.map(s => ({
        name: s.name || 'Unknown',
        rating: s.rating ?? null,
        level: s.level || '',
        grades: s.grades || '',
        distance_mi: s.distance_mi ?? s.distance ?? null,
        enrollment: s.enrollment ?? null,
        student_teacher_ratio: s.student_teacher_ratio ?? null,
        student_counselor_ratio: s.student_counselor_ratio ?? null,
        pct_certified_teachers: s.pct_certified_teachers ?? null,
        greatschools_link: s.greatschools_link || null,
        principal: s.principal || null,
        _source: s._source || '',
    }));

    // Order by level (elem → middle → high → other), but include EVERY
    // school. Within a level, LCPS schools come first (authoritative),
    // then Zillow extras (boundary mismatches or nearby schools).
    const levelOrder = { elementary: 0, middle: 1, high: 2 };
    const sourceOrder = { lcps: 0, zillow: 1 };
    const ordered = [...normalized].sort((a, b) => {
        const la = levelOrder[(a.level || '').toLowerCase()] ?? 99;
        const lb = levelOrder[(b.level || '').toLowerCase()] ?? 99;
        if (la !== lb) return la - lb;
        const sa = sourceOrder[a._source] ?? 9;
        const sb = sourceOrder[b._source] ?? 9;
        return sa - sb;
    });

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
