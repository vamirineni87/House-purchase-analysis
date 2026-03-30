/**
 * Tiny publish / subscribe event bus.
 *
 * Usage:
 *   import { on, off, emit } from './events.js';
 *   const unsub = on('pipeline:completed', (data) => { ... });
 *   emit('pipeline:completed', { propertyId, runId });
 *   unsub();                      // or off('pipeline:completed', handler)
 *
 * Well-known events:
 *   'property:added'        { property }
 *   'property:deleted'      { propertyId }
 *   'pipeline:started'      { propertyId, runId }
 *   'pipeline:completed'    { propertyId, runId, status }
 *   'tab:changed'           { propertyId, tab }
 *   'route:changed'         { route, params }
 *   'settings:saved'        { key, value }
 *   'store:updated'         { path, value }
 */

/** @type {Map<string, Set<Function>>} */
const _listeners = new Map();

/**
 * Subscribe to an event.
 * @param {string} event
 * @param {Function} handler
 * @returns {Function} unsubscribe function
 */
export function on(event, handler) {
    if (!_listeners.has(event)) {
        _listeners.set(event, new Set());
    }
    _listeners.get(event).add(handler);

    // Return a convenient unsubscribe function
    return () => off(event, handler);
}

/**
 * Unsubscribe a specific handler from an event.
 * @param {string} event
 * @param {Function} handler
 */
export function off(event, handler) {
    const handlers = _listeners.get(event);
    if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
            _listeners.delete(event);
        }
    }
}

/**
 * Emit an event, calling all subscribed handlers synchronously.
 * @param {string} event
 * @param {*} data  — payload passed to every handler
 */
export function emit(event, data) {
    const handlers = _listeners.get(event);
    if (!handlers) return;

    for (const handler of handlers) {
        try {
            handler(data);
        } catch (err) {
            console.error(`[events] Error in handler for "${event}":`, err);
        }
    }
}

/**
 * Subscribe to an event for a single invocation, then auto-unsubscribe.
 * @param {string} event
 * @param {Function} handler
 * @returns {Function} unsubscribe (in case you need to cancel before it fires)
 */
export function once(event, handler) {
    const wrapper = (data) => {
        off(event, wrapper);
        handler(data);
    };
    return on(event, wrapper);
}
