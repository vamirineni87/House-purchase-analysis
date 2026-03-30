/**
 * Hash-based router with parameter and query-string support.
 *
 * Route patterns use a simple `:param` syntax:
 *   '#dashboard'
 *   '#properties'
 *   '#property/:id'          -> params.id
 *
 * Query parameters after "?" are parsed automatically:
 *   '#property/abc123?tab=Financial'  -> params.id='abc123', query.tab='Financial'
 *
 * Usage:
 *   import { initRouter, navigate, getCurrentRoute } from './router.js';
 *
 *   initRouter({
 *       'dashboard':    renderDashboard,
 *       'properties':   renderProperties,
 *       'property/:id': renderPropertyDetail,
 *       'alerts':       renderAlerts,
 *       'comparison':   renderComparison,
 *       'settings':     renderSettings,
 *   });
 *
 *   navigate('property/abc123?tab=Financial');
 */

import { emit } from './events.js';

/** @type {Array<{pattern: string, segments: string[], handler: Function}>} */
let _routes = [];

/** @type {{name: string, params: Record<string, string>, query: Record<string, string>}|null} */
let _current = null;

// ── Public API ──────────────────────────────────────────────────────

/**
 * Register routes and start listening for hash changes.
 * The first matched route wins.  An unmatched hash falls back to the
 * first route in the map (typically 'dashboard').
 *
 * @param {Record<string, Function>} routeMap  pattern -> handler(params, query)
 */
export function initRouter(routeMap) {
    _routes = Object.entries(routeMap).map(([pattern, handler]) => ({
        pattern,
        segments: pattern.split('/'),
        handler,
    }));

    window.addEventListener('hashchange', _onHashChange);

    // Handle initial load
    _onHashChange();
}

/**
 * Programmatically navigate to a hash route.
 *
 * @param {string} hash  e.g. 'property/abc123?tab=Financial'
 */
export function navigate(hash) {
    // Strip leading '#' if caller included it
    const clean = hash.startsWith('#') ? hash.slice(1) : hash;
    window.location.hash = clean;
}

/**
 * Return the currently active route info, or null before init.
 *
 * @returns {{name: string, params: Record<string, string>, query: Record<string, string>}|null}
 */
export function getCurrentRoute() {
    return _current;
}

// ── Internals ───────────────────────────────────────────────────────

/** Parse window.location.hash and dispatch to the matching handler. */
function _onHashChange() {
    const raw = window.location.hash.slice(1) || ''; // drop '#'
    const [pathPart, queryPart] = raw.split('?');
    const pathSegments = pathPart.split('/').filter(Boolean);
    const query = _parseQuery(queryPart || '');

    for (const route of _routes) {
        const match = _matchRoute(route.segments, pathSegments);
        if (match) {
            _current = { name: route.pattern, params: match, query };
            emit('route:changed', _current);
            route.handler(match, query);
            return;
        }
    }

    // No match — fall back to the first registered route
    if (_routes.length > 0) {
        const fallback = _routes[0];
        _current = { name: fallback.pattern, params: {}, query: {} };
        emit('route:changed', _current);
        fallback.handler({}, {});
    }
}

/**
 * Try to match a route pattern's segments against the actual URL segments.
 * Returns a params object on match, or null on mismatch.
 *
 * @param {string[]} patternSegments  e.g. ['property', ':id']
 * @param {string[]} pathSegments     e.g. ['property', 'abc123']
 * @returns {Record<string, string>|null}
 */
function _matchRoute(patternSegments, pathSegments) {
    if (patternSegments.length !== pathSegments.length) return null;

    /** @type {Record<string, string>} */
    const params = {};

    for (let i = 0; i < patternSegments.length; i++) {
        const pat = patternSegments[i];
        const val = pathSegments[i];

        if (pat.startsWith(':')) {
            params[pat.slice(1)] = decodeURIComponent(val);
        } else if (pat !== val) {
            return null;
        }
    }

    return params;
}

/**
 * Parse a query string like "tab=Financial&foo=bar" into an object.
 *
 * @param {string} qs
 * @returns {Record<string, string>}
 */
function _parseQuery(qs) {
    if (!qs) return {};
    /** @type {Record<string, string>} */
    const result = {};
    for (const pair of qs.split('&')) {
        const [key, ...rest] = pair.split('=');
        if (key) {
            result[decodeURIComponent(key)] = decodeURIComponent(rest.join('='));
        }
    }
    return result;
}
