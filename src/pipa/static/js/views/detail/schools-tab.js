/**
 * Schools tab — 3 school cards (elementary, middle, high) with name, rating /10,
 * distance, enrollment. Average school rating. Handles empty state.
 */

import { escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';

const LEVELS = ['elementary', 'middle', 'high'];

function ratingColor(rating) {
    if (!rating && rating !== 0) return 'text-gray-400';
    if (rating >= 8) return 'text-green-600';
    if (rating >= 6) return 'text-amber-600';
    if (rating >= 4) return 'text-orange-600';
    return 'text-red-600';
}

function ratingBg(rating) {
    if (!rating && rating !== 0) return 'bg-gray-100';
    if (rating >= 8) return 'bg-green-50 border-green-200';
    if (rating >= 6) return 'bg-amber-50 border-amber-200';
    if (rating >= 4) return 'bg-orange-50 border-orange-200';
    return 'bg-red-50 border-red-200';
}

function levelIcon(level) {
    switch (level.toLowerCase()) {
        case 'elementary': return 'E';
        case 'middle':     return 'M';
        case 'high':       return 'H';
        default:           return 'S';
    }
}

function renderSchoolCard(school) {
    const assignedBadge = school.assigned ? renderBadge('Assigned', 'info', 'sm') : '';
    const ratingHtml = school.rating !== undefined && school.rating !== null
        ? `<div><span class="text-2xl font-bold ${ratingColor(school.rating)}">${school.rating}</span><span class="text-sm text-gray-400">/10</span></div>`
        : '<span class="text-sm text-gray-400">No rating</span>';

    const distanceHtml = school.distance_mi !== undefined
        ? `<div class="text-xs text-gray-500">${school.distance_mi.toFixed(1)} mi away</div>`
        : '';

    let detailsHtml = '';
    const details = [];
    if (school.enrollment) {
        details.push(`<div class="flex justify-between text-xs"><span class="text-gray-500">Enrollment</span><span class="font-medium text-gray-700">${school.enrollment.toLocaleString()}</span></div>`);
    }
    if (school.student_teacher_ratio) {
        details.push(`<div class="flex justify-between text-xs"><span class="text-gray-500">Student:Teacher</span><span class="font-medium text-gray-700">${school.student_teacher_ratio}:1</span></div>`);
    }
    if (school.test_scores) {
        for (const [key, val] of Object.entries(school.test_scores)) {
            details.push(`<div class="flex justify-between text-xs"><span class="text-gray-500 capitalize">${key.replace(/_/g, ' ')}</span><span class="font-medium text-gray-700">${val}</span></div>`);
        }
    }
    if (details.length > 0) {
        detailsHtml = `<div class="mt-3 pt-3 border-t border-gray-200/50 space-y-1.5">${details.join('')}</div>`;
    }

    return `
    <div class="border rounded-lg p-4 ${ratingBg(school.rating)}">
        <div class="flex items-start justify-between mb-3">
            <div class="flex items-center gap-2">
                <div class="w-8 h-8 bg-white border border-gray-200 rounded-lg flex items-center justify-center text-sm font-bold text-gray-500">${levelIcon(school.level)}</div>
                <div>
                    <div class="text-xs text-gray-500 uppercase tracking-wide">${escapeHtml(school.level)}</div>
                    <div class="text-sm font-medium text-gray-900">${escapeHtml(school.name)}</div>
                </div>
            </div>
            ${assignedBadge}
        </div>
        <div class="flex items-end justify-between">
            <div>${distanceHtml}</div>
            <div class="text-right">${ratingHtml}</div>
        </div>
        ${detailsHtml}
    </div>`;
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const ld = state.listingData || {};

    // Get schools from listing data
    const rawSchools = ld.assigned_schools || ld.nearby_schools || [];
    const schools = rawSchools.map(s => ({
        name: s.name || 'Unknown',
        rating: s.rating || 0,
        level: s.level || '',
        grades: s.grades || '',
        distance_mi: s.distance_mi || s.distance || 0,
        enrollment: s.enrollment,
        student_teacher_ratio: s.student_teacher_ratio,
        test_scores: s.test_scores,
        assigned: s.assigned,
    }));

    if (schools.length === 0) {
        container.innerHTML = `
        <div class="text-sm text-gray-500 text-center py-8">
            No school data available. Run the pipeline to fetch school information.
        </div>`;
        return;
    }

    // Group by level
    const grouped = {};
    for (const level of LEVELS) {
        grouped[level] = schools.filter(s => s.level.toLowerCase() === level);
    }
    const other = schools.filter(s => !LEVELS.includes(s.level.toLowerCase()));

    // Average rating
    const rated = schools.filter(s => s.rating !== undefined && s.rating > 0);
    const avgRating = rated.length > 0
        ? rated.reduce((sum, s) => sum + s.rating, 0) / rated.length
        : undefined;

    let avgHtml = '';
    if (avgRating !== undefined) {
        avgHtml = `
        <div class="bg-white border border-gray-200 rounded-lg p-4 flex items-center gap-4">
            <div>
                <div class="text-xs text-gray-500">Average School Rating</div>
                <div class="text-2xl font-bold ${ratingColor(avgRating)}">${avgRating.toFixed(1)}/10</div>
            </div>
            <div>
                <div class="text-xs text-gray-500">Schools Rated</div>
                <div class="text-2xl font-bold text-gray-900">${rated.length}</div>
            </div>
        </div>`;
    }

    // Cards by level
    const levelCards = LEVELS.map(level => {
        const levelSchools = grouped[level];
        if (levelSchools.length === 0) {
            return `
            <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
                <div class="text-xs text-gray-500 uppercase tracking-wide mb-2">${level}</div>
                <div class="text-sm text-gray-400">No data</div>
            </div>`;
        }
        return levelSchools.map(s => renderSchoolCard(s)).join('');
    }).join('');

    let otherHtml = '';
    if (other.length > 0) {
        otherHtml = `
        <div>
            <h4 class="text-sm font-semibold text-gray-700 mb-2">Other Schools</h4>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                ${other.map(s => renderSchoolCard(s)).join('')}
            </div>
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${avgHtml}
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">${levelCards}</div>
        ${otherHtml}
    </div>`;
}

export function bind(container, state) {
    // Schools tab is read-only
}
