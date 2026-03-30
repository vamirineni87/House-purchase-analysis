/**
 * Action button component — primary (blue) and secondary (gray) variants.
 * Shows "Running..." when loading. Supports disabled state.
 */

/**
 * @param {string}  id       - Element id for querySelector binding.
 * @param {string}  label    - Button text.
 * @param {string}  variant  - 'primary' | 'secondary'
 * @param {boolean} disabled - Whether button is disabled.
 * @param {boolean} loading  - Whether button is in loading state.
 * @returns {string} HTML string
 */
export function renderActionButton(id, label, variant = 'primary', disabled = false, loading = false) {
    const base = variant === 'primary'
        ? 'bg-blue-600 text-white hover:bg-blue-700'
        : 'bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300';
    const disabledAttr = (disabled || loading) ? 'disabled' : '';
    const text = loading ? 'Running...' : esc(label);
    return `<button id="${esc(id)}" ${disabledAttr} class="px-3 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-50 ${base}">${text}</button>`;
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
