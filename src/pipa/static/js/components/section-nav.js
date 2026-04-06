/**
 * Sticky section navigation bar for property detail scroll page.
 *
 * Renders compact anchor links that scroll to sections.
 * Active section highlighted via IntersectionObserver.
 */

const SECTION_LABELS = [
    { id: 'summary-actions',   label: 'Summary' },
    { id: 'pipeline-health',  label: 'Health' },
    { id: 'price-value',      label: 'Value' },
    { id: 'key-metrics',      label: 'Metrics' },
    { id: 'financial',        label: 'Financial' },
    { id: 'condition',        label: 'Condition' },
    { id: 'schools',          label: 'Schools' },
    { id: 'property-history', label: 'History' },
    { id: 'county-details',   label: 'County' },
    { id: 'comps',            label: 'Comps' },
    { id: 'ai-analysis',      label: 'AI' },
    { id: 'notes',            label: 'Notes' },
];

/**
 * Render the section nav bar HTML.
 */
export function renderSectionNav() {
    const links = SECTION_LABELS.map(({ id, label }) =>
        `<button data-section-link="${id}" class="section-nav-link px-3 py-2 text-xs font-medium text-gray-500 hover:text-blue-600 whitespace-nowrap transition-colors border-b-2 border-transparent">${label}</button>`
    ).join('');

    return `<nav id="section-nav" class="bg-white border-b border-gray-200 px-6">
  <div class="flex flex-wrap gap-0 -mb-px items-center">
    ${links}
    <button id="toggle-all-sections" class="ml-auto px-2 py-1.5 text-xs text-gray-400 hover:text-blue-600 whitespace-nowrap" title="Expand/Collapse All">Expand All</button>
  </div>
</nav>`;
}

/**
 * Bind section nav: click handlers + IntersectionObserver for active tracking.
 */
export function bindSectionNav(container, headerEl) {
    const nav = container.querySelector('#section-nav');
    if (!nav) return;

    // Force layout recalculation so sticky kicks in immediately
    void nav.offsetHeight;

    // Expand/Collapse All
    const toggleAllBtn = nav.querySelector('#toggle-all-sections');
    if (toggleAllBtn) {
        toggleAllBtn.addEventListener('click', () => {
            const bodies = container.querySelectorAll('[data-section-body]');
            const anyHidden = Array.from(bodies).some(b => b.classList.contains('hidden'));
            bodies.forEach(b => b.classList.toggle('hidden', !anyHidden));
            // Update chevrons
            container.querySelectorAll('[data-section-chevron]').forEach(c => {
                c.classList.toggle('-rotate-90', !anyHidden);
            });
            toggleAllBtn.textContent = anyHidden ? 'Collapse All' : 'Expand All';
        });
    }

    const scrollContainer = container.closest('#app') || document.querySelector('#app');
    const links = nav.querySelectorAll('[data-section-link]');
    for (const link of links) {
        link.addEventListener('click', () => {
            const sectionId = link.getAttribute('data-section-link');
            const target = container.querySelector(`[data-section-id="${sectionId}"]`);
            if (target && scrollContainer) {
                const offset = (nav.offsetHeight || 0) + 12;
                const targetTop = target.offsetTop - offset;
                scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
            }
        });
    }

    const sectionEls = SECTION_LABELS.map(({ id }) =>
        container.querySelector(`[data-section-id="${id}"]`)
    ).filter(Boolean);

    if (sectionEls.length === 0) return;

    const observerOpts = {
        root: scrollContainer || null,
        rootMargin: `-${(nav.offsetHeight || 0) + 20}px 0px -60% 0px`,
        threshold: 0,
    };

    let _activeId = null;

    const observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('data-section-id');
                if (id !== _activeId) {
                    _activeId = id;
                    _updateActiveLink(nav, id);
                }
            }
        }
    }, observerOpts);

    for (const el of sectionEls) {
        observer.observe(el);
    }
}

function _updateActiveLink(nav, activeId) {
    const links = nav.querySelectorAll('[data-section-link]');
    for (const link of links) {
        const id = link.getAttribute('data-section-link');
        if (id === activeId) {
            link.classList.add('text-blue-600', 'border-blue-500');
            link.classList.remove('text-gray-500', 'border-transparent');
        } else {
            link.classList.remove('text-blue-600', 'border-blue-500');
            link.classList.add('text-gray-500', 'border-transparent');
        }
    }
}
