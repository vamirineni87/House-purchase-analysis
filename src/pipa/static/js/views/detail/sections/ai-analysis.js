/**
 * Section §11: AI Analysis.
 *
 * AI Pass 1 (extraction): components, red flags, upgrades.
 * AI Pass 2 (interpretation): pros, cons, questions, narrative.
 * Rerun AI button in header. Stale detection when county data is newer.
 */

import { escapeHtml } from '../../../utils.js';
import { renderBadge } from '../../../components/badge.js';
import { showToast } from '../../../toast.js';
import { api } from '../../../api.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'AI Analysis';
export const ID = 'ai-analysis';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(_state) { return false; }

export function getStateBadge(state) {
    const { pass1, pass2 } = extractPasses(state);
    if (!pass1 && !pass2) return { label: 'Not run', variant: 'not-run' };

    // Check staleness: if county data was refreshed after the AI run
    if (pass1 || pass2) {
        const aiRunDate = getAiRunDate(state);
        const countyRefreshDate = state.freshness?.county?.last_fetched || state.freshness?.county?.updated_at;
        if (aiRunDate && countyRefreshDate && new Date(countyRefreshDate) > new Date(aiRunDate)) {
            return { label: 'Stale', variant: 'warning' };
        }
    }

    if (pass1 && pass2) return { label: 'Complete', variant: 'success' };
    return { label: 'Partial', variant: 'warning' };
}

export function headerExtra(state) {
    const loading = state.actionLoading?.rerunAi;
    return `
    <button class="ai-rerun-btn px-2.5 py-1 text-xs font-medium rounded border transition-colors
        ${loading ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed' : 'bg-white text-blue-600 border-blue-300 hover:bg-blue-50'}"
        ${loading ? 'disabled' : ''}>
        ${loading ? 'Running...' : 'Rerun AI'}
    </button>`;
}

// ── Helpers ────────────────────────────────────────────────────────

/**
 * Extract AI pass 1 and pass 2 results from pipeline runs or analysis results.
 */
function extractPasses(state) {
    let pass1 = null;
    let pass2 = null;

    // Try from analysisResults first
    if (state.analysisResults) {
        if (state.analysisResults.ai_extraction || state.analysisResults.ai_pass_1) {
            pass1 = state.analysisResults.ai_extraction || state.analysisResults.ai_pass_1;
        }
        if (state.analysisResults.ai_interpretation || state.analysisResults.ai_pass_2) {
            pass2 = state.analysisResults.ai_interpretation || state.analysisResults.ai_pass_2;
        }
    }

    // Fall back to pipeline task results
    if (!pass1 || !pass2) {
        const runs = state.pipelineRuns || [];
        for (const run of runs) {
            for (const task of (run.tasks || [])) {
                const name = task.task_name || '';
                if (!pass1 && (name === 'ai_pass_1' || name.includes('ai_extract')) && task.result_summary) {
                    pass1 = task.result_summary;
                }
                if (!pass2 && (name === 'ai_pass_2' || name.includes('ai_interpret')) && task.result_summary) {
                    pass2 = task.result_summary;
                }
            }
            if (pass1 && pass2) break;
        }
    }

    // Also try latestRun
    if (!pass1 || !pass2) {
        const tasks = state.latestRun?.tasks || [];
        for (const task of tasks) {
            const name = task.task_name || '';
            if (!pass1 && (name === 'ai_pass_1' || name.includes('ai_extract')) && task.result_summary) {
                pass1 = task.result_summary;
            }
            if (!pass2 && (name === 'ai_pass_2' || name.includes('ai_interpret')) && task.result_summary) {
                pass2 = task.result_summary;
            }
        }
    }

    return { pass1, pass2 };
}

/**
 * Get the date when the AI analysis was last run.
 */
function getAiRunDate(state) {
    const runs = state.pipelineRuns || [];
    for (const run of runs) {
        for (const task of (run.tasks || [])) {
            const name = task.task_name || '';
            if ((name === 'ai_pass_1' || name === 'ai_pass_2' || name.includes('ai_extract') || name.includes('ai_interpret')) && task.completed_at) {
                return task.completed_at;
            }
        }
        // Also check run-level date
        if (run.completed_at) return run.completed_at;
    }
    return state.latestRun?.completed_at || null;
}

function renderBulletList(items, icon, colorClass) {
    if (!items || items.length === 0) return '';
    const listItems = items.map(item =>
        `<li class="text-xs ${colorClass} flex gap-1.5 leading-snug"><span class="shrink-0">${icon}</span><span>${escapeHtml(String(item))}</span></li>`
    ).join('');
    return `<ul class="space-y-0.5">${listItems}</ul>`;
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const { pass1, pass2 } = extractPasses(state);

    if (!pass1 && !pass2) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">AI analysis not run. Run the pipeline to generate.</p>
        </div>`;
    }

    const parts = [];

    // ── AI Pass 1: Extraction ─────────────────────────────────────
    parts.push('<div>');
    parts.push('<h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">AI Pass 1: Extraction</h4>');

    if (pass1) {
        const subParts = [];

        // Extracted components
        const components = pass1.components || pass1.extracted_components || [];
        if (Array.isArray(components) && components.length > 0) {
            const badges = components.map(c => renderBadge(String(c), 'info', 'sm')).join(' ');
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Extracted Components</div>
                <div class="flex flex-wrap gap-1">${badges}</div>
            </div>`);
        }

        // Red flags
        const redFlags = pass1.red_flags || [];
        if (Array.isArray(redFlags) && redFlags.length > 0) {
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Red Flags</div>
                ${renderBulletList(redFlags, '!', 'text-red-700')}
            </div>`);
        }

        // Upgrades / improvements
        const upgrades = pass1.upgrades || pass1.improvements || [];
        if (Array.isArray(upgrades) && upgrades.length > 0) {
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Upgrades / Improvements</div>
                ${renderBulletList(upgrades, '+', 'text-green-700')}
            </div>`);
        }

        // Fallback: raw JSON if no structured data
        if (subParts.length === 0) {
            subParts.push(`<pre class="text-xs text-gray-600 whitespace-pre-wrap bg-gray-50 rounded p-2">${escapeHtml(JSON.stringify(pass1, null, 2))}</pre>`);
        }

        parts.push(`<div class="bg-white border border-gray-200 rounded-lg p-3 space-y-2.5">${subParts.join('')}</div>`);
    } else {
        parts.push('<p class="text-xs text-gray-500 bg-gray-50 rounded-lg p-3 text-center">No AI Pass 1 data.</p>');
    }
    parts.push('</div>');

    // ── AI Pass 2: Interpretation ─────────────────────────────────
    parts.push('<div>');
    parts.push('<h4 class="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">AI Pass 2: Interpretation</h4>');

    if (pass2) {
        const subParts = [];

        // Pros
        const pros = pass2.pros || [];
        if (Array.isArray(pros) && pros.length > 0) {
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Pros</div>
                ${renderBulletList(pros, '+', 'text-green-700')}
            </div>`);
        }

        // Cons
        const cons = pass2.cons || [];
        if (Array.isArray(cons) && cons.length > 0) {
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Cons</div>
                ${renderBulletList(cons, '-', 'text-red-700')}
            </div>`);
        }

        // Questions for agent
        const questions = pass2.questions_for_agent || pass2.questions || [];
        if (Array.isArray(questions) && questions.length > 0) {
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Questions for Agent</div>
                ${renderBulletList(questions, '?', 'text-gray-700')}
            </div>`);
        }

        // Interpretation narrative
        const interp = pass2.interpretation || pass2.narrative || '';
        if (typeof interp === 'string' && interp.trim()) {
            subParts.push(`
            <div>
                <div class="text-xs text-gray-500 mb-1">Interpretation</div>
                <p class="text-xs text-gray-700 leading-relaxed">${escapeHtml(interp)}</p>
            </div>`);
        }

        // Fallback: raw JSON if no structured data
        if (subParts.length === 0) {
            subParts.push(`<pre class="text-xs text-gray-600 whitespace-pre-wrap bg-gray-50 rounded p-2">${escapeHtml(JSON.stringify(pass2, null, 2))}</pre>`);
        }

        parts.push(`<div class="bg-white border border-gray-200 rounded-lg p-3 space-y-2.5">${subParts.join('')}</div>`);
    } else {
        parts.push('<p class="text-xs text-gray-500 bg-gray-50 rounded-lg p-3 text-center">No AI Pass 2 data. Run the full pipeline.</p>');
    }
    parts.push('</div>');

    return `<div class="space-y-5">${parts.join('')}</div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    const rerunBtn = container.querySelector('.ai-rerun-btn');
    if (!rerunBtn) return;

    rerunBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (rerunBtn.disabled) return;

        rerunBtn.disabled = true;
        rerunBtn.textContent = 'Running...';

        try {
            // Run both AI tasks via the pipeline
            await api.runTask(state.property.id, 'ai_pass_1');
            await api.runTask(state.property.id, 'ai_pass_2');
            showToast('AI analysis complete', 'success');
            if (actions?.rerenderSection) {
                actions.rerenderSection(ID);
            } else if (actions?.reload) {
                actions.reload();
            }
        } catch (err) {
            showToast('AI analysis failed: ' + (err.message || 'unknown'), 'error');
            rerunBtn.disabled = false;
            rerunBtn.textContent = 'Rerun AI';
        }
    });
}
