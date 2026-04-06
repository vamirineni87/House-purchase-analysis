/**
 * Section §3: Price / Value
 *
 * Price benchmarks (ask vs zestimate/assessed/comp), comp value band
 * from quick comp, ask-vs-comps assessment, and pricing warnings.
 * Header has a [Run Quick Comp] button.
 */

import { formatCurrency, escapeHtml } from '../../../utils.js';
import { renderPriceBenchmarks } from '../../../components/price-benchmarks.js';
import { renderBadge } from '../../../components/badge.js';
import { api } from '../../../api.js';
import { showToast } from '../../../toast.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Price / Value';
export const ID = 'price-value';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(_state) { return false; }

export function getStateBadge(state) {
    const ld = state.listingData || {};
    const pv = state.packet?.price_view;
    const hasPrice = !!(ld.price || pv?.list_price);
    const hasComps = !!state.quickComp;

    if (hasPrice && hasComps) return { label: 'Complete', variant: 'success' };
    if (hasPrice) return { label: 'Partial', variant: 'warning' };
    return { label: 'Not run', variant: 'not-run' };
}

export function headerExtra(state) {
    const loading = state.actionLoading === 'quick-comp';
    return `<button data-action="run-quick-comp-header"
        class="pipa-btn pipa-btn-outline"
        onclick="event.stopPropagation()"
        ${loading ? 'disabled' : ''}>${loading ? 'Running...' : 'Run Quick Comp'}</button>`;
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const { listingData, packet, quickComp } = state;
    const ld = listingData || {};
    const pv = packet?.price_view;

    const listPrice = ld.price || pv?.list_price || undefined;
    const zestimate = ld.zestimate || undefined;
    // Prefer county assessed value (current year) over Zillow's (often stale)
    const countyAssessments = state.countyData?.assessments || [];
    const latestCountyAssessed = countyAssessments.length > 0
        ? countyAssessments[0]?.total_value  // sorted newest first
        : undefined;
    const assessed = latestCountyAssessed || ld.tax_assessed_value || ld.tax_assessed || pv?.assessment_value || undefined;
    const compEstimate = pv?.comp_estimate || quickComp?.rough_value_band?.mid || undefined;

    const parts = [];

    // ── Price Benchmarks ──────────────────────────────────────────
    parts.push(renderPriceBenchmarks(listPrice, zestimate, assessed, undefined, compEstimate));

    // ── Comp Value Band ───────────────────────────────────────────
    if (quickComp?.rough_value_band) {
        const vb = quickComp.rough_value_band;
        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Comp Value Band</div>
            <div class="flex items-center gap-6 text-sm">
                <div>
                    <span class="text-xs text-gray-400">Low</span>
                    <div class="text-green-600 font-semibold">${formatCurrency(vb.low)}</div>
                </div>
                <div>
                    <span class="text-xs text-gray-400">Mid</span>
                    <div class="text-blue-600 font-bold text-base">${formatCurrency(vb.mid)}</div>
                </div>
                <div>
                    <span class="text-xs text-gray-400">High</span>
                    <div class="text-red-600 font-semibold">${formatCurrency(vb.high)}</div>
                </div>
            </div>
        </div>`);
    }

    // ── Ask vs Comps Assessment ───────────────────────────────────
    if (quickComp?.asking_vs_comps) {
        const assessment = quickComp.asking_vs_comps;
        let variant = 'muted';
        if (/below|under/i.test(assessment)) variant = 'success';
        else if (/above|over|high/i.test(assessment)) variant = 'critical';
        else if (/fair|line|par/i.test(assessment)) variant = 'info';

        parts.push(`
        <div class="flex items-center gap-2">
            <span class="text-xs text-gray-500">Ask vs Comps:</span>
            ${renderBadge(assessment, variant, 'sm')}
            ${quickComp.quick_confidence ? `<span class="text-xs text-gray-400">(${escapeHtml(quickComp.quick_confidence)} confidence)</span>` : ''}
        </div>`);
    }

    // ── Pricing Warnings ──────────────────────────────────────────
    const warnings = quickComp?.warnings || [];
    if (warnings.length > 0) {
        const items = warnings
            .map(w => `<div class="text-xs text-amber-700 flex gap-1.5"><span class="shrink-0">!</span><span>${escapeHtml(w)}</span></div>`)
            .join('');
        parts.push(`
        <div class="bg-amber-50 border border-amber-200 rounded p-2.5">
            <div class="text-xs font-semibold text-amber-700 mb-1">Pricing Warnings</div>
            <div class="space-y-0.5">${items}</div>
        </div>`);
    }

    if (parts.length === 0) {
        return `
        <div class="bg-gray-50 border border-gray-200 rounded p-4 text-center">
            <p class="text-sm text-gray-500">No price data available. Run the pipeline to generate benchmarks.</p>
        </div>`;
    }

    return `<div class="space-y-4">${parts.join('')}</div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(container, state, actions) {
    // Run Quick Comp header button
    const btn = container.querySelector('[data-action="run-quick-comp-header"]');
    if (btn) {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            btn.disabled = true;
            btn.textContent = 'Running...';
            try {
                const r = await api.runCompsQuick(state.property?.id || state.propertyId);
                state.quickComp = r;
                showToast('Quick comp complete', 'success');
                if (actions?.reload) actions.reload();
            } catch (err) {
                showToast('Quick comp failed: ' + (err.message || 'unknown'), 'error');
                btn.disabled = false;
                btn.textContent = 'Run Quick Comp';
            }
        });
    }
}
