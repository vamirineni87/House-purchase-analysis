/**
 * General-purpose formatting and rendering utilities.
 */

// ── Formatters ──────────────────────────────────────────────────────

/**
 * Format a number as US currency: "$1,234,567".
 * Returns "—" for null/undefined/NaN.
 *
 * @param {number|null|undefined} n
 * @param {number} [decimals=0]
 * @returns {string}
 */
export function formatCurrency(n, decimals = 0) {
    if (n == null || Number.isNaN(n)) return '\u2014';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(n);
}

/**
 * Format a number with commas: "1,234,567".
 * Returns "—" for null/undefined/NaN.
 *
 * @param {number|null|undefined} n
 * @returns {string}
 */
export function formatNumber(n) {
    if (n == null || Number.isNaN(n)) return '\u2014';
    return new Intl.NumberFormat('en-US').format(n);
}

/**
 * Format an ISO 8601 date string as "Mar 29, 2026".
 * Returns "—" for falsy input.
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatDate(iso) {
    if (!iso) return '\u2014';
    try {
        return new Date(iso).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
        });
    } catch {
        return '\u2014';
    }
}

/**
 * Format an ISO timestamp as "Mar 29, 2026 3:15 PM".
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatDateTime(iso) {
    if (!iso) return '\u2014';
    try {
        return new Date(iso).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
        });
    } catch {
        return '\u2014';
    }
}

/**
 * Format a duration in milliseconds as a human-readable string.
 *   0–999 ms   -> "123ms"
 *   1–59.9 s   -> "2.4s"
 *   60 s+      -> "1m 30s"
 *
 * @param {number|null|undefined} ms
 * @returns {string}
 */
export function formatDuration(ms) {
    if (ms == null || Number.isNaN(ms)) return '\u2014';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    const totalSec = ms / 1000;
    if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
    const min = Math.floor(totalSec / 60);
    const sec = Math.round(totalSec % 60);
    return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

/**
 * Format a percentage: "85.3%".
 *
 * @param {number|null|undefined} n  Value between 0 and 1, or 0 and 100
 * @param {boolean} [isDecimal=true] true if n is 0-1, false if 0-100
 * @returns {string}
 */
export function formatPercent(n, isDecimal = true) {
    if (n == null || Number.isNaN(n)) return '\u2014';
    const pct = isDecimal ? n * 100 : n;
    return `${pct.toFixed(1)}%`;
}

// ── HTML Helpers ────────────────────────────────────────────────────

/**
 * Escape a string for safe insertion into HTML.
 *
 * @param {string} str
 * @returns {string}
 */
export function escapeHtml(str) {
    if (!str) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(str).replace(/[&<>"']/g, (ch) => map[ch]);
}

/**
 * Render an HTML table from headers and row data.
 *
 * @param {string[]} headers            Column header labels
 * @param {(string|number)[][]} rows    Array of row arrays
 * @param {object} [options]
 * @param {string} [options.tableClass]  Extra CSS classes for <table>
 * @param {string} [options.emptyText]   Message when rows is empty
 * @param {boolean} [options.striped]    Alternate row backgrounds (default true)
 * @param {boolean} [options.compact]    Smaller padding (default false)
 * @returns {string} HTML string
 */
export function renderTable(headers, rows, options = {}) {
    const {
        tableClass = '',
        emptyText = 'No data available',
        striped = true,
        compact = false,
    } = options;

    if (!rows || rows.length === 0) {
        return `<p class="text-gray-500 text-sm py-4">${escapeHtml(emptyText)}</p>`;
    }

    const cellPad = compact ? 'px-3 py-1.5' : 'px-4 py-2.5';

    const ths = headers
        .map((h) => `<th class="${cellPad} text-left text-xs font-medium text-gray-500 uppercase tracking-wider">${escapeHtml(String(h))}</th>`)
        .join('');

    const trs = rows
        .map((row, i) => {
            const bgClass = striped && i % 2 === 1 ? 'bg-gray-50' : '';
            const tds = row
                .map((cell) => `<td class="${cellPad} text-sm text-gray-700 whitespace-nowrap">${escapeHtml(String(cell ?? '\u2014'))}</td>`)
                .join('');
            return `<tr class="${bgClass} hover:bg-gray-100 transition-colors">${tds}</tr>`;
        })
        .join('');

    return `
        <div class="overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full divide-y divide-gray-200 ${escapeHtml(tableClass)}">
                <thead class="bg-gray-50"><tr>${ths}</tr></thead>
                <tbody class="bg-white divide-y divide-gray-200">${trs}</tbody>
            </table>
        </div>
    `;
}

/**
 * Create a badge / pill element.
 *
 * @param {string} text
 * @param {string} colorClasses  Tailwind bg + text classes, e.g. "bg-green-100 text-green-700"
 * @returns {string} HTML string
 */
export function badge(text, colorClasses = 'bg-gray-100 text-gray-700') {
    return `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${escapeHtml(colorClasses)}">${escapeHtml(text)}</span>`;
}

/**
 * Truncate a string to a maximum length, appending "..." if truncated.
 *
 * @param {string} str
 * @param {number} max
 * @returns {string}
 */
export function truncate(str, max = 60) {
    if (!str) return '';
    return str.length > max ? str.slice(0, max - 1) + '\u2026' : str;
}
