/**
 * Minimal reactive store for application state.
 *
 * The store is a plain object tree.  `updateStore()` sets values at a
 * dot-delimited path and emits a 'store:updated' event so any interested
 * module can react.
 *
 * Usage:
 *   import { Store, updateStore, getStore, clearViewState } from './store.js';
 *   updateStore('views.dashboard.loaded', true);
 *   const loaded = getStore('views.dashboard.loaded');
 */

import { emit } from './events.js';

// ── State tree ──────────────────────────────────────────────────────

export const Store = {
    /** Normalised entity maps for quick lookup by ID. */
    entities: {
        /** @type {Record<string, object>} */
        propertiesById: {},
        /** @type {Record<string, object>} */
        pipelineRunsById: {},
    },

    /** Per-view transient state. */
    views: {
        dashboard: {
            loaded: false,
            properties: [],
            alerts: [],
            stats: null,
        },
        properties: {
            loaded: false,
            list: [],
        },
        propertyDetail: {
            propertyId: null,
            activeTab: 'Summary',
            property: null,
            listingData: null,
            analysisResults: null,
            pipelineRuns: [],
        },
        comparison: {
            selectedIds: [],
            result: null,
        },
        alerts: {
            loaded: false,
            list: [],
        },
        settings: {
            loaded: false,
            grouped: {},
        },
    },

    /** Shared UI state. */
    ui: {
        /** Key of the action currently in-flight (for loading spinners). */
        actionLoading: null,
        /** Active toast objects managed internally by toast.js. */
        toasts: [],
    },
};

// ── Helpers ─────────────────────────────────────────────────────────

/**
 * Set a value at a dot-delimited path inside the Store and emit a
 * `store:updated` event.
 *
 * @param {string} path   e.g. "views.dashboard.loaded"
 * @param {*}      value
 */
export function updateStore(path, value) {
    const keys = path.split('.');
    let target = Store;

    for (let i = 0; i < keys.length - 1; i++) {
        const k = keys[i];
        if (target[k] == null || typeof target[k] !== 'object') {
            target[k] = {};
        }
        target = target[k];
    }

    const lastKey = keys[keys.length - 1];
    target[lastKey] = value;

    emit('store:updated', { path, value });
}

/**
 * Read a value at a dot-delimited path.  Returns `undefined` for
 * missing segments rather than throwing.
 *
 * @param {string} path
 * @returns {*}
 */
export function getStore(path) {
    const keys = path.split('.');
    let target = Store;

    for (const k of keys) {
        if (target == null || typeof target !== 'object') return undefined;
        target = target[k];
    }
    return target;
}

/**
 * Reset a view's state to its initial values.
 *
 * @param {'dashboard'|'properties'|'propertyDetail'|'comparison'|'alerts'|'settings'} view
 */
export function clearViewState(view) {
    const defaults = {
        dashboard:      { loaded: false, properties: [], alerts: [], stats: null },
        properties:     { loaded: false, list: [] },
        propertyDetail: { propertyId: null, activeTab: 'Summary', property: null, listingData: null, analysisResults: null, pipelineRuns: [] },
        comparison:     { selectedIds: [], result: null },
        alerts:         { loaded: false, list: [] },
        settings:       { loaded: false, grouped: {} },
    };

    if (defaults[view]) {
        updateStore(`views.${view}`, { ...defaults[view] });
    }
}

/**
 * Upsert an entity into the normalised entity map and return it.
 *
 * @param {'propertiesById'|'pipelineRunsById'} collection
 * @param {string} id
 * @param {object} data
 * @returns {object}
 */
export function upsertEntity(collection, id, data) {
    const existing = Store.entities[collection][id];
    const merged = existing ? { ...existing, ...data } : data;
    Store.entities[collection][id] = merged;
    emit('store:updated', { path: `entities.${collection}.${id}`, value: merged });
    return merged;
}
