/**
 * Collapsible section component for property detail scroll page.
 *
 * Renders a section with a toggleable header (chevron + title + state badge + headerExtra).
 * Section-level action buttons in headerExtra must call stopPropagation.
 */

const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const CHEVRON_SVG = `<svg class="w-4 h-4 text-gray-400 transition-transform duration-200" viewBox="0 0 20 20" fill="currentColor">
  <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/>
</svg>`;

const BADGE_VARIANTS = {
    'not-run':  'bg-gray-100 text-gray-500',
    'loading':  'bg-blue-100 text-blue-600',
    'partial':  'bg-amber-100 text-amber-700',
    'warning':  'bg-amber-100 text-amber-700',
    'stale':    'bg-amber-100 text-amber-700',
    'complete': 'bg-green-100 text-green-700',
    'success':  'bg-green-100 text-green-700',
    'info':     'bg-blue-100 text-blue-600',
    'critical': 'bg-red-100 text-red-700',
    'muted':    'bg-gray-100 text-gray-500',
};

/**
 * Render a state badge for a section header.
 * @param {{ label: string, variant: string }} badge
 */
export function renderStateBadge(badge) {
    if (!badge || !badge.label) return '';
    const cls = BADGE_VARIANTS[badge.variant] || BADGE_VARIANTS['not-run'];
    return `<span class="section-state-badge text-[10px] px-1.5 py-0.5 rounded font-medium ${cls}">${esc(badge.label)}</span>`;
}

/**
 * Render a collapsible section.
 */
export function renderCollapsibleSection(id, title, content, opts = {}) {
    const expanded = opts.expanded !== false;
    const headerExtra = opts.headerExtra || '';
    const badgeHtml = opts.stateBadge ? renderStateBadge(opts.stateBadge) : '';
    const bodyHidden = expanded ? '' : ' hidden';
    const chevronRotate = expanded ? '' : ' -rotate-90';

    return `<div data-section-id="${esc(id)}" class="bg-white rounded-lg border border-gray-200 shadow-sm">
  <div data-section-toggle="${esc(id)}" role="button" tabindex="0" class="w-full flex items-center justify-between px-5 py-3.5 cursor-pointer select-none hover:bg-gray-50 rounded-t-lg transition-colors">
    <div class="flex items-center gap-2.5 min-w-0">
      <h2 class="text-sm font-semibold text-gray-800 uppercase tracking-wide">${esc(title)}</h2>
      ${badgeHtml}
    </div>
    <div class="flex items-center gap-2.5 flex-shrink-0">
      <span data-section-extra="${esc(id)}" class="flex items-center gap-2">${headerExtra}</span>
      <span data-section-chevron="${esc(id)}" class="transition-transform duration-200${chevronRotate}">${CHEVRON_SVG}</span>
    </div>
  </div>
  <div data-section-body="${esc(id)}" class="px-5 pb-5${bodyHidden}">${content}</div>
</div>`;
}

/**
 * Bind all collapsible toggle buttons in the container.
 */
export function bindCollapsibleSections(container) {
    const toggles = container.querySelectorAll('[data-section-toggle]');
    for (const btn of toggles) {
        btn.addEventListener('click', (e) => {
            if (e.target.closest('[data-section-extra] button, [data-section-extra] a, button[data-action], a[data-action]')) {
                return;
            }
            const id = btn.getAttribute('data-section-toggle');
            const body = container.querySelector(`[data-section-body="${id}"]`);
            const chevron = container.querySelector(`[data-section-chevron="${id}"]`);
            if (!body) return;

            const isHidden = body.classList.contains('hidden');
            body.classList.toggle('hidden');
            if (chevron) {
                chevron.classList.toggle('-rotate-90', !isHidden);
            }

            _persistSectionState(id, isHidden);
        });
    }

    const extraBtns = container.querySelectorAll('[data-section-extra] button, [data-section-extra] a');
    for (const btn of extraBtns) {
        btn.addEventListener('click', (e) => e.stopPropagation());
    }
}

// --- localStorage persistence ---

let _propertyId = null;

export function setPropertyId(propertyId) {
    _propertyId = propertyId;
}

function _storageKey() {
    return _propertyId ? `pipa_sections_${_propertyId}` : null;
}

function _persistSectionState(sectionId, expanded) {
    const key = _storageKey();
    if (!key) return;
    try {
        const saved = JSON.parse(localStorage.getItem(key) || '{}');
        saved[sectionId] = expanded;
        localStorage.setItem(key, JSON.stringify(saved));
    } catch { /* ignore */ }
}

/**
 * Get saved expanded state for a section, or null if not saved.
 */
export function getSavedExpanded(sectionId) {
    const key = _storageKey();
    if (!key) return null;
    try {
        const saved = JSON.parse(localStorage.getItem(key) || '{}');
        return saved[sectionId] ?? null;
    } catch { return null; }
}
