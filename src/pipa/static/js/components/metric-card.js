/**
 * Metric card component — white card with label + bold value.
 */

/**
 * @param {string} label - Small text above the value.
 * @param {string} value - Large bold display value.
 * @returns {string} HTML string
 */
export function renderMetricCard(label, value) {
    const safeLabel = esc(label);
    const safeValue = esc(value != null ? String(value) : '--');
    return `
    <div class="bg-white border border-gray-200 rounded-lg p-3">
        <div class="text-xs text-gray-500">${safeLabel}</div>
        <div class="text-lg font-semibold text-gray-900">${safeValue}</div>
    </div>`;
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
