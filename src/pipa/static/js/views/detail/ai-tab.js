/**
 * AI Analysis tab — AI Pass 1 (extracted components, red flags),
 * AI Pass 2 (pros/cons, questions for agent, interpretation),
 * Listing vs County validation. Handles empty state.
 */

import { api } from '../../api.js';
import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderBadge } from '../../components/badge.js';

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const { packet, pipelineRuns } = state;

    // Extract AI pass results from pipeline tasks
    let aiPass1 = null;
    let aiPass2 = null;

    for (const run of (pipelineRuns || [])) {
        for (const task of (run.tasks || [])) {
            if (task.task_name === 'ai_pass_1' && task.result_summary) {
                aiPass1 = task.result_summary;
            }
            if (task.task_name === 'ai_pass_2' && task.result_summary) {
                aiPass2 = task.result_summary;
            }
        }
        if (aiPass1 || aiPass2) break;
    }

    // AI Pass 1 section
    let pass1Html;
    if (aiPass1) {
        let componentsHtml = '';
        if (Array.isArray(aiPass1.components)) {
            const badges = aiPass1.components.map(c => renderBadge(String(c), 'info', 'sm')).join(' ');
            componentsHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Extracted Components</h4>
                <div class="flex flex-wrap gap-1">${badges}</div>
            </div>`;
        }

        let redFlagsHtml = '';
        if (Array.isArray(aiPass1.red_flags) && aiPass1.red_flags.length > 0) {
            const items = aiPass1.red_flags.map(f => `<li>! ${escapeHtml(String(f))}</li>`).join('');
            redFlagsHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Red Flags</h4>
                <ul class="text-sm text-red-700 space-y-0.5">${items}</ul>
            </div>`;
        }

        let upgradesHtml = '';
        if (Array.isArray(aiPass1.upgrades) && aiPass1.upgrades.length > 0) {
            const items = aiPass1.upgrades.map(u => `<li>+ ${escapeHtml(String(u))}</li>`).join('');
            upgradesHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Detected Upgrades</h4>
                <ul class="text-sm text-green-700 space-y-0.5">${items}</ul>
            </div>`;
        }

        // Fallback raw display
        let fallback = '';
        if (!Array.isArray(aiPass1.components) && !Array.isArray(aiPass1.red_flags) && !Array.isArray(aiPass1.upgrades)) {
            fallback = `<pre class="text-xs text-gray-600 whitespace-pre-wrap">${escapeHtml(JSON.stringify(aiPass1, null, 2))}</pre>`;
        }

        pass1Html = `
        <div class="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
            ${componentsHtml}
            ${redFlagsHtml}
            ${upgradesHtml}
            ${fallback}
        </div>`;
    } else {
        pass1Html = `
        <div class="text-sm text-gray-500 bg-gray-50 rounded-lg p-4 text-center">
            No AI Pass 1 data. Run the full pipeline.
        </div>`;
    }

    // AI Pass 2 section
    let pass2Html;
    if (aiPass2) {
        let prosHtml = '';
        if (Array.isArray(aiPass2.pros) && aiPass2.pros.length > 0) {
            const items = aiPass2.pros.map(p => `<li>+ ${escapeHtml(String(p))}</li>`).join('');
            prosHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Pros</h4>
                <ul class="text-sm text-green-700 space-y-0.5">${items}</ul>
            </div>`;
        }

        let consHtml = '';
        if (Array.isArray(aiPass2.cons) && aiPass2.cons.length > 0) {
            const items = aiPass2.cons.map(c => `<li>- ${escapeHtml(String(c))}</li>`).join('');
            consHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Cons</h4>
                <ul class="text-sm text-red-700 space-y-0.5">${items}</ul>
            </div>`;
        }

        let questionsHtml = '';
        if (Array.isArray(aiPass2.questions_for_agent) && aiPass2.questions_for_agent.length > 0) {
            const items = aiPass2.questions_for_agent.map(q => `<li>? ${escapeHtml(String(q))}</li>`).join('');
            questionsHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Questions for Agent</h4>
                <ul class="text-sm text-gray-700 space-y-0.5">${items}</ul>
            </div>`;
        }

        let interpHtml = '';
        if (typeof aiPass2.interpretation === 'string') {
            interpHtml = `
            <div>
                <h4 class="text-xs text-gray-500 mb-1">Interpretation</h4>
                <p class="text-sm text-gray-700">${escapeHtml(aiPass2.interpretation)}</p>
            </div>`;
        }

        // Fallback raw display
        let fallback = '';
        if (!Array.isArray(aiPass2.pros) && !Array.isArray(aiPass2.cons) && !Array.isArray(aiPass2.questions_for_agent) && typeof aiPass2.interpretation !== 'string') {
            fallback = `<pre class="text-xs text-gray-600 whitespace-pre-wrap">${escapeHtml(JSON.stringify(aiPass2, null, 2))}</pre>`;
        }

        pass2Html = `
        <div class="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
            ${prosHtml}
            ${consHtml}
            ${questionsHtml}
            ${interpHtml}
            ${fallback}
        </div>`;
    } else {
        pass2Html = `
        <div class="text-sm text-gray-500 bg-gray-50 rounded-lg p-4 text-center">
            No AI Pass 2 data. Run the full pipeline.
        </div>`;
    }

    // Listing vs County validation (from decision packet)
    let validationHtml;
    if (packet) {
        let hiddenCostItems = '';
        if (packet.hidden_cost?.capex_items && packet.hidden_cost.capex_items.length > 0) {
            hiddenCostItems = `
            <ul class="space-y-0.5">
                ${packet.hidden_cost.capex_items.map(item => `
                <li class="text-gray-700 text-xs">
                    ${escapeHtml(String(item.name || item.type || 'Item'))}${item.cost ? `: ${formatCurrency(Number(item.cost))}` : ''}
                </li>`).join('')}
            </ul>`;
        } else {
            hiddenCostItems = '<span class="text-gray-400 text-xs">None identified</span>';
        }

        let permitConcerns = '';
        if (packet.hidden_cost?.permit_concerns && packet.hidden_cost.permit_concerns.length > 0) {
            permitConcerns = `
            <ul class="space-y-0.5">
                ${packet.hidden_cost.permit_concerns.map(c => `<li class="text-amber-700 text-xs">${escapeHtml(c)}</li>`).join('')}
            </ul>`;
        } else {
            permitConcerns = '<span class="text-gray-400 text-xs">None</span>';
        }

        validationHtml = `
        <div class="bg-white border border-gray-200 rounded-lg p-4">
            <div class="grid grid-cols-2 gap-3 text-sm">
                <div>
                    <div class="text-xs text-gray-500 mb-1">Hidden Costs</div>
                    ${hiddenCostItems}
                </div>
                <div>
                    <div class="text-xs text-gray-500 mb-1">Permit Concerns</div>
                    ${permitConcerns}
                </div>
            </div>
        </div>`;
    } else {
        validationHtml = `
        <div class="text-sm text-gray-500 bg-gray-50 rounded-lg p-4 text-center">
            No validation data. Run the full pipeline to generate.
        </div>`;
    }

    container.innerHTML = `
    <div class="space-y-6">
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">AI Pass 1: Component Extraction</h3>
            ${pass1Html}
        </div>
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">AI Pass 2: Interpretation</h3>
            ${pass2Html}
        </div>
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Listing vs County Validation</h3>
            ${validationHtml}
        </div>
    </div>`;
}

export function bind(container, state) {
    // AI tab is read-only
}
