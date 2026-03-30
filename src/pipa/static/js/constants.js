/**
 * Shared constants used across the SPA.
 */

/** Tabs shown on the property detail page, in display order. */
export const TAB_IDS = [
    'Summary',
    'Financial',
    'County',
    'Condition',
    'Comps',
    'Offer',
    'Stress',
    'Decision',
    'Notes',
];

/** Pipeline run statuses. */
export const RUN_STATUSES = {
    QUEUED:          'queued',
    RUNNING:         'running',
    SUCCEEDED:       'succeeded',
    PARTIAL_SUCCESS: 'partial_success',
    FAILED:          'failed',
    CANCELLED:       'cancelled',
};

/** Individual pipeline task statuses. */
export const TASK_STATUSES = {
    PENDING:   'pending',
    RUNNING:   'running',
    SUCCEEDED: 'succeeded',
    FAILED:    'failed',
    SKIPPED:   'skipped',
};

/** Watchlist pipeline stages, in funnel order. */
export const STAGES = [
    'researching',
    'touring',
    'offer',
    'contract',
    'closed',
    'rejected',
];

/** Alert / warning severity levels, ascending. */
export const SEVERITY_LEVELS = ['info', 'warning', 'critical'];

/** Status badge color mapping (Tailwind class fragments). */
export const STATUS_COLORS = {
    queued:          'bg-gray-100 text-gray-700',
    pending:         'bg-gray-100 text-gray-700',
    running:         'bg-blue-100 text-blue-700',
    succeeded:       'bg-green-100 text-green-700',
    partial_success: 'bg-yellow-100 text-yellow-700',
    failed:          'bg-red-100 text-red-700',
    cancelled:       'bg-gray-200 text-gray-500',
    skipped:         'bg-gray-100 text-gray-500',
};

/** Severity badge color mapping. */
export const SEVERITY_COLORS = {
    info:     'bg-blue-100 text-blue-700',
    warning:  'bg-amber-100 text-amber-700',
    critical: 'bg-red-100 text-red-700',
};
