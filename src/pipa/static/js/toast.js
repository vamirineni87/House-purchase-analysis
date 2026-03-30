/**
 * Lightweight toast notifications.
 *
 * Usage:
 *   import { showToast } from './toast.js';
 *   showToast('Property saved', 'success');
 *   showToast('Network error', 'error', 6000);
 */

const TYPE_STYLES = {
    success: 'bg-green-600 text-white',
    error:   'bg-red-600 text-white',
    info:    'bg-blue-600 text-white',
    warning: 'bg-amber-500 text-white',
};

const TYPE_ICONS = {
    success: `<svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`,
    error:   `<svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`,
    info:    `<svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01"/></svg>`,
    warning: `<svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86l-8.4 14.31A1 1 0 002.77 20h18.46a1 1 0 00.88-1.83l-8.4-14.31a1 1 0 00-1.76 0z"/></svg>`,
};

/**
 * Display a toast notification.
 *
 * @param {string} message     Text shown in the toast
 * @param {'success'|'error'|'info'|'warning'} type  Visual style (default: 'info')
 * @param {number} duration    Auto-dismiss delay in ms (default: 4000, 0 = no auto-dismiss)
 */
export function showToast(message, type = 'info', duration = 4000) {
    const root = document.getElementById('toast-root');
    if (!root) return;

    const el = document.createElement('div');
    el.className = [
        'flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm max-w-sm',
        'transform translate-x-full transition-transform duration-300 ease-out',
        TYPE_STYLES[type] || TYPE_STYLES.info,
    ].join(' ');

    el.innerHTML = `
        ${TYPE_ICONS[type] || TYPE_ICONS.info}
        <span class="flex-1">${escapeToastHtml(message)}</span>
        <button class="ml-2 opacity-70 hover:opacity-100 shrink-0" aria-label="Close">&times;</button>
    `;

    // Dismiss on click
    const closeBtn = el.querySelector('button');
    closeBtn.addEventListener('click', () => dismiss(el));

    root.appendChild(el);

    // Trigger the slide-in animation on the next frame
    requestAnimationFrame(() => {
        el.classList.remove('translate-x-full');
        el.classList.add('translate-x-0');
    });

    // Auto-dismiss
    if (duration > 0) {
        setTimeout(() => dismiss(el), duration);
    }
}

/**
 * Dismiss a toast element with a fade-out animation.
 * @param {HTMLElement} el
 */
function dismiss(el) {
    if (!el || !el.parentNode) return;

    el.classList.add('opacity-0', 'translate-x-full');
    el.addEventListener('transitionend', () => {
        if (el.parentNode) el.parentNode.removeChild(el);
    }, { once: true });

    // Safety: remove after animation even if transitionend does not fire
    setTimeout(() => {
        if (el.parentNode) el.parentNode.removeChild(el);
    }, 400);
}

/**
 * Minimal HTML escape for toast content.
 * @param {string} str
 * @returns {string}
 */
function escapeToastHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
