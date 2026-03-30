/**
 * Settings view — API keys section (7 keys, password inputs), save button.
 * Financial defaults table (read-only display). All from backend API.
 */

import { api } from '../api.js';
import { showToast } from '../toast.js';
import { escapeHtml } from '../utils.js';

const API_KEYS = [
    { label: 'FRED API Key',         key: 'fred_api_key',         placeholder: 'Your FRED API key' },
    { label: 'RentCast API Key',     key: 'rentcast_api_key',     placeholder: 'Your RentCast API key' },
    { label: 'GreatSchools API Key', key: 'greatschools_api_key', placeholder: 'Your GreatSchools API key' },
    { label: 'WalkScore API Key',    key: 'walkscore_api_key',    placeholder: 'Your WalkScore API key' },
    { label: 'API Ninjas Key',       key: 'api_ninjas_key',       placeholder: 'Your API Ninjas key' },
    { label: 'Census API Key',       key: 'census_api_key',       placeholder: 'Your Census API key' },
    { label: 'NOAA Token',           key: 'noaa_token',           placeholder: 'Your NOAA API token' },
];

const DEFAULT_ASSUMPTIONS = [
    { label: '30yr Mortgage Rate',            value: '6.50%' },
    { label: '15yr Mortgage Rate',            value: '5.90%' },
    { label: 'Homeowners Insurance Rate',     value: '0.35%' },
    { label: 'PMI Rate',                      value: '0.50%' },
    { label: 'PMI Threshold',                 value: '80% LTV' },
    { label: 'Property Tax Rate (default)',   value: '1.20%' },
    { label: 'Appreciation Rate',             value: '3.00%' },
    { label: 'Inflation Rate',                value: '2.50%' },
    { label: 'Maintenance Rate',              value: '1.00%' },
    { label: 'Closing Cost Rate',             value: '3.00%' },
    { label: 'Vacancy Rate',                  value: '5.00%' },
    { label: 'Marginal Tax Rate',             value: '24.00%' },
    { label: 'Filing Status',                 value: 'Married' },
];

let _keys = {};
let _saved = false;
let _serverDefaults = null;

/**
 * Extract a flat { key: value } map from the grouped settings response
 * for a specific category.
 */
function extractCategory(grouped, category) {
    const items = grouped[category];
    if (!Array.isArray(items)) return {};
    const map = {};
    for (const item of items) {
        map[item.key] = item.value;
    }
    return map;
}

// ---------------------------------------------------------------
// Load
// ---------------------------------------------------------------

export async function load(container) {
    // Try to load from server first
    try {
        const settings = await api.getSettings();
        const apiKeysMap = extractCategory(settings, 'api_keys');
        for (const cfg of API_KEYS) {
            _keys[cfg.key] = apiKeysMap[cfg.key] || '';
        }
        const finDefaults = settings.financial_defaults;
        if (Array.isArray(finDefaults) && finDefaults.length > 0) {
            _serverDefaults = finDefaults.map(item => ({
                label: item.key,
                value: String(item.value),
            }));
        }
    } catch {
        // Fall back to empty keys
        for (const cfg of API_KEYS) {
            _keys[cfg.key] = '';
        }
    }

    _saved = false;
    render(container);
    bind(container);
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container) {
    const keyInputs = API_KEYS.map(cfg => `
    <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">${escapeHtml(cfg.label)}</label>
        <input type="password" data-key="${escapeHtml(cfg.key)}" value="${escapeHtml(_keys[cfg.key] || '')}" placeholder="${escapeHtml(cfg.placeholder)}" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
    </div>`).join('');

    const savedIndicator = _saved
        ? '<span class="text-sm text-green-600">Saved!</span>'
        : '';

    // Financial defaults table
    const assumptions = _serverDefaults || DEFAULT_ASSUMPTIONS;
    const rows = (Array.isArray(assumptions) ? assumptions : DEFAULT_ASSUMPTIONS).map(item => `
    <tr>
        <td class="px-4 py-2 text-gray-700">${escapeHtml(item.label)}</td>
        <td class="px-4 py-2 text-right font-mono text-gray-900">${escapeHtml(item.value)}</td>
    </tr>`).join('');

    container.innerHTML = `
    <div class="max-w-2xl">
        <h1 class="text-2xl font-bold mb-6">Settings</h1>

        <section class="mb-8">
            <h2 class="text-lg font-semibold text-gray-900 mb-4">API Keys</h2>
            <p class="text-sm text-gray-500 mb-4">API keys are sent to the backend with requests that need them. Enter your keys below and click Save.</p>
            <div class="space-y-3">${keyInputs}</div>
            <div class="mt-4 flex items-center gap-3">
                <button id="save-keys-btn" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700">Save Keys</button>
                ${savedIndicator}
            </div>
        </section>

        <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-4">Default Financial Assumptions</h2>
            <p class="text-sm text-gray-500 mb-4">These defaults are loaded from the server's config.yaml. To change them, edit the config file and restart the server.</p>
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="bg-gray-50 text-gray-600 text-left">
                            <th class="px-4 py-2 font-medium">Parameter</th>
                            <th class="px-4 py-2 font-medium text-right">Default Value</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">${rows}</tbody>
                </table>
            </div>
        </section>
    </div>`;
}

// ---------------------------------------------------------------
// Bind
// ---------------------------------------------------------------

export function bind(container) {
    // Track key input changes
    container.querySelectorAll('[data-key]').forEach(input => {
        input.addEventListener('input', () => {
            const key = input.getAttribute('data-key');
            _keys[key] = input.value;
            _saved = false;
        });
    });

    // Save button
    const saveBtn = container.querySelector('#save-keys-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            try {
                // Save each non-empty key individually
                const promises = [];
                for (const cfg of API_KEYS) {
                    const val = (_keys[cfg.key] || '').trim();
                    if (val) {
                        promises.push(api.saveSetting(cfg.key, val, 'api_keys'));
                    }
                }
                await Promise.all(promises);
                _saved = true;
                showToast('API keys saved', 'success');
                render(container);
                bind(container);
            } catch {
                showToast('Failed to save settings', 'error');
            }
        });
    }
}
