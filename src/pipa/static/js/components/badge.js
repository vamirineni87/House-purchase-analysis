/**
 * Badge component — renders a styled inline badge.
 *
 * Variants: default, info, warning, critical, success, muted
 * Sizes: sm, md
 */

const VARIANT_STYLES = {
    default:  'bg-gray-100 text-gray-700',
    info:     'bg-blue-100 text-blue-700',
    warning:  'bg-amber-100 text-amber-700',
    critical: 'bg-red-100 text-red-700',
    success:  'bg-green-100 text-green-700',
    muted:    'bg-gray-50 text-gray-500',
};

const SIZE_STYLES = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-0.5',
};

/**
 * Return an HTML string for a badge element.
 * @param {string} label   - Text displayed inside the badge.
 * @param {string} variant - One of default|info|warning|critical|success|muted.
 * @param {string} size    - One of sm|md.
 * @returns {string} HTML string
 */
export function renderBadge(label, variant = 'default', size = 'sm') {
    const v = VARIANT_STYLES[variant] || VARIANT_STYLES.default;
    const s = SIZE_STYLES[size] || SIZE_STYLES.sm;
    return `<span class="inline-flex items-center rounded-full font-medium ${v} ${s}">${escapeText(label)}</span>`;
}

/**
 * Map a watchlist stage to a badge variant.
 */
export function stageBadgeVariant(stage) {
    const map = {
        researching: 'info',
        touring:     'warning',
        offer:       'critical',
        contract:    'success',
        closed:      'success',
        rejected:    'muted',
    };
    return map[stage] || 'default';
}

/**
 * Map an alert severity to a badge variant.
 */
export function severityBadgeVariant(severity) {
    const map = {
        info:     'info',
        warning:  'warning',
        critical: 'critical',
    };
    return map[severity] || 'default';
}

/**
 * Map a run status to a badge variant.
 */
export function runStatusBadgeVariant(status) {
    const map = {
        succeeded:       'success',
        failed:          'critical',
        partial_success: 'warning',
        running:         'info',
        queued:          'info',
        cancelled:       'muted',
    };
    return map[status] || 'muted';
}

/** Minimal HTML entity escape for text content. */
function escapeText(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
