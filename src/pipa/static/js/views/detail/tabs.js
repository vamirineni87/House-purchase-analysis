/**
 * Tab bar — renders horizontal tab navigation.
 * Active tab has blue border-bottom.
 */

const TAB_IDS = [
    'Summary',
    'Pipeline',
    'Financial',
    'Value/Comps',
    'Condition',
    'County',
    'Listing History',
    'Schools',
    'AI Analysis',
    'Notes & DD',
];

/**
 * Render the tab bar.
 * @param {string} activeTab - Currently active tab id.
 * @returns {string} HTML string
 */
export function renderTabBar(activeTab) {
    const tabs = TAB_IDS.map(tab => {
        const isActive = activeTab === tab;
        const cls = isActive
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300';
        return `<button data-tab="${esc(tab)}" class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${cls}">${esc(tab)}</button>`;
    }).join('');

    return `
    <div class="border-b border-gray-200 mb-6">
        <nav class="flex gap-0 -mb-px overflow-x-auto">${tabs}</nav>
    </div>`;
}

export { TAB_IDS };

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
