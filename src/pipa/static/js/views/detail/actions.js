/**
 * Action bar — 5 buttons: Run Full Pipeline, Refresh Listing,
 * Refresh County, Run Deep Comp, Rerun AI.
 * Each disables all buttons while one is running.
 */

import { renderActionButton } from '../../components/action-button.js';

/**
 * Render the action bar.
 * @param {string|null} actionLoading - Key of the currently running action, or null.
 * @returns {string} HTML string
 */
export function renderActionBar(actionLoading) {
    const anyLoading = actionLoading !== null;

    return `
    <div class="flex flex-wrap gap-2 mb-6">
        ${renderActionButton('action-run-pipeline', 'Run Full Pipeline', 'primary', anyLoading, actionLoading === 'action-run-pipeline')}
        ${renderActionButton('action-refresh-listing', 'Refresh Listing', 'secondary', anyLoading, actionLoading === 'action-refresh-listing')}
        ${renderActionButton('action-refresh-county', 'Refresh County', 'secondary', anyLoading, actionLoading === 'action-refresh-county')}
        ${renderActionButton('action-deep-comp', 'Run Deep Comp', 'secondary', anyLoading, actionLoading === 'action-deep-comp')}
        ${renderActionButton('action-rerun-ai', 'Rerun AI', 'secondary', anyLoading, actionLoading === 'action-rerun-ai')}
    </div>`;
}
