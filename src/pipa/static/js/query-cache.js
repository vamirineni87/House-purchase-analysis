/**
 * Simple in-memory cache for API responses.
 *
 * Keys are typically `propertyId:endpoint` strings.  Each entry stores
 * the data and an expiry timestamp; reads return `null` for stale entries.
 *
 * Usage:
 *   import { cache } from './query-cache.js';
 *   cache.set('abc123:county', countyData, 120_000);
 *   const hit = cache.get('abc123:county');  // data or null
 *   cache.invalidate('abc123:county');
 */

/** @type {Map<string, {data: *, expiresAt: number}>} */
const _store = new Map();

/** Default time-to-live in milliseconds (60 s). */
const DEFAULT_TTL_MS = 60_000;

/**
 * Store a value in the cache.
 *
 * @param {string} key     Cache key (e.g. `${propertyId}:freshness`)
 * @param {*}      data    Serializable data to cache
 * @param {number} [ttlMs] Time-to-live in ms (default: 60 000)
 */
export function set(key, data, ttlMs = DEFAULT_TTL_MS) {
    _store.set(key, {
        data,
        expiresAt: Date.now() + ttlMs,
    });
}

/**
 * Retrieve a cached value.  Returns `null` if the key is missing or stale.
 *
 * @param {string} key
 * @returns {*|null}
 */
export function get(key) {
    const entry = _store.get(key);
    if (!entry) return null;

    if (Date.now() > entry.expiresAt) {
        _store.delete(key);
        return null;
    }
    return entry.data;
}

/**
 * Check whether a fresh entry exists for the given key.
 *
 * @param {string} key
 * @returns {boolean}
 */
export function has(key) {
    return get(key) !== null;
}

/**
 * Invalidate a single cache entry.
 *
 * @param {string} key
 */
export function invalidate(key) {
    _store.delete(key);
}

/**
 * Invalidate every entry whose key starts with the given prefix.
 * Useful for clearing all data related to a single property:
 *   invalidatePrefix('abc123:')
 *
 * @param {string} prefix
 */
export function invalidatePrefix(prefix) {
    for (const key of _store.keys()) {
        if (key.startsWith(prefix)) {
            _store.delete(key);
        }
    }
}

/**
 * Drop every entry from the cache.
 */
export function invalidateAll() {
    _store.clear();
}

/**
 * Return the number of live (non-expired) entries.
 * Lazily prunes stale entries during the count.
 *
 * @returns {number}
 */
export function size() {
    const now = Date.now();
    let count = 0;
    for (const [key, entry] of _store) {
        if (now > entry.expiresAt) {
            _store.delete(key);
        } else {
            count++;
        }
    }
    return count;
}

/** Convenience namespace export. */
export const cache = { set, get, has, invalidate, invalidatePrefix, invalidateAll, size };
