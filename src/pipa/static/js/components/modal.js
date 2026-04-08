/**
 * Modal component — generic overlay + Add Property modal logic.
 *
 * URL mode: single input for Zillow/Redfin/Realtor URL.
 * Address mode: street, city, state (default VA), zip, type dropdown.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';

let _overlay = null;

/**
 * Show a modal dialog.
 * @param {string} title    - Modal header text.
 * @param {string} bodyHtml - Inner HTML for the modal body.
 * @param {object} options  - { onClose?: Function, width?: string }
 */
export function showModal(title, bodyHtml, options = {}) {
    hideModal();
    const width = options.width || 'max-w-lg';
    _overlay = document.createElement('div');
    _overlay.id = 'modal-overlay';
    _overlay.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/40';
    _overlay.innerHTML = `
    <div class="bg-white rounded-lg shadow-xl ${width} w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <h2 class="text-lg font-semibold text-gray-900">${esc(title)}</h2>
            <button id="modal-close-btn" class="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>
        <div class="px-6 py-4" id="modal-body">
            ${bodyHtml}
        </div>
    </div>`;

    document.body.appendChild(_overlay);

    // Close on backdrop click
    _overlay.addEventListener('click', (e) => {
        if (e.target === _overlay) hideModal(options.onClose);
    });
    // Close button
    const closeBtn = _overlay.querySelector('#modal-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => hideModal(options.onClose));
    }
}

/**
 * Hide the active modal.
 */
export function hideModal(onClose) {
    if (_overlay) {
        _overlay.remove();
        _overlay = null;
    }
    if (typeof onClose === 'function') onClose();
}

/**
 * Show the Add Property modal with URL / Address mode toggle.
 * On successful submit, navigates to the new property detail page.
 */
export function showAddPropertyModal() {
    const bodyHtml = `
    <div id="add-prop-root">
        <div class="flex border border-gray-200 rounded-lg overflow-hidden mb-4">
            <button id="mode-url" class="flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white">URL</button>
            <button id="mode-address" class="flex-1 px-4 py-2 text-sm font-medium bg-gray-100 text-gray-700">Address</button>
        </div>

        <!-- URL mode -->
        <div id="url-form">
            <label class="block text-sm font-medium text-gray-700 mb-1">Listing URL</label>
            <input id="add-url" type="text" placeholder="https://www.zillow.com/homedetails/..." class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-1" />
            <p class="text-xs text-gray-400 mb-4">Zillow, Redfin, or Realtor.com URL</p>
        </div>

        <!-- Address mode (hidden by default) -->
        <div id="address-form" class="hidden space-y-3">
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Street Address</label>
                <input id="add-street" type="text" placeholder="1234 Main St" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
            </div>
            <div class="grid grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">City</label>
                    <input id="add-city" type="text" placeholder="Fairfax" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">State</label>
                    <input id="add-state" type="text" value="VA" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1">Zip</label>
                    <input id="add-zip" type="text" placeholder="22030" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm" />
                </div>
            </div>
            <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Property Type</label>
                <select id="add-type" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">
                    <option value="single_family">Single Family</option>
                    <option value="townhouse">Townhouse</option>
                    <option value="condo">Condo</option>
                    <option value="multi_family">Multi Family</option>
                </select>
            </div>
        </div>

        <div id="add-error" class="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-3 hidden"></div>
        <div id="add-loading" class="text-sm text-blue-600 mb-3 hidden">Scraping listing...</div>

        <button id="add-submit" class="w-full px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 mt-2">
            Add Property
        </button>
    </div>`;

    showModal('Add Property', bodyHtml);

    // Bind mode toggle
    const modeUrl = document.getElementById('mode-url');
    const modeAddr = document.getElementById('mode-address');
    const urlForm = document.getElementById('url-form');
    const addrForm = document.getElementById('address-form');

    let mode = 'url';

    modeUrl.addEventListener('click', () => {
        mode = 'url';
        modeUrl.className = 'flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white';
        modeAddr.className = 'flex-1 px-4 py-2 text-sm font-medium bg-gray-100 text-gray-700';
        urlForm.classList.remove('hidden');
        addrForm.classList.add('hidden');
    });

    modeAddr.addEventListener('click', () => {
        mode = 'address';
        modeAddr.className = 'flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white';
        modeUrl.className = 'flex-1 px-4 py-2 text-sm font-medium bg-gray-100 text-gray-700';
        addrForm.classList.remove('hidden');
        urlForm.classList.add('hidden');
    });

    // Submit handler
    const submitBtn = document.getElementById('add-submit');
    const errorEl = document.getElementById('add-error');
    const loadingEl = document.getElementById('add-loading');

    submitBtn.addEventListener('click', async () => {
        errorEl.classList.add('hidden');
        loadingEl.classList.remove('hidden');
        submitBtn.disabled = true;

        try {
            let result;
            if (mode === 'url') {
                const url = document.getElementById('add-url').value.trim();
                if (!url) {
                    throw new Error('Please enter a listing URL.');
                }
                result = await api.ingestProperty({ url });
            } else {
                const street = document.getElementById('add-street').value.trim();
                const city = document.getElementById('add-city').value.trim();
                const state = document.getElementById('add-state').value.trim();
                const zip = document.getElementById('add-zip').value.trim();
                const propertyType = document.getElementById('add-type').value;
                if (!street) {
                    throw new Error('Please enter a street address.');
                }
                result = await api.ingestProperty({
                    street, city, state, zip,
                    property_type: propertyType,
                });
            }

            hideModal();
            // The backend creates a placeholder property from the URL slug
            // and returns immediately. The Zillow scrape, county scrape,
            // schools, quick comp, and AI pipeline all run in a background
            // task. Tell the user they can move on.
            showToast(
                'Property added. Scraping & analysis are running in the background — check back in a few minutes.',
                'success',
            );
            const propId = result?.property?.id || result?.property_id;
            if (propId) {
                window.location.hash = `#property/${propId}`;
            }
        } catch (err) {
            loadingEl.classList.add('hidden');
            submitBtn.disabled = false;
            errorEl.textContent = err.message || 'Failed to add property';
            errorEl.classList.remove('hidden');
        }
    });
}

function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
