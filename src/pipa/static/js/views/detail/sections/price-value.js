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
    const hasComps = !!(state.deepComp || state.quickComp);

    if (hasPrice && state.deepComp) return { label: 'Complete', variant: 'success' };
    if (hasPrice && hasComps) return { label: 'Partial', variant: 'warning' };
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
    const { listingData, packet, quickComp, deepComp } = state;
    const ld = listingData || {};
    const pv = packet?.price_view;

    // Prefer deep comp over quick comp when available
    const bestComp = deepComp?.value_range?.mid ? deepComp : quickComp;
    const bestValueBand = deepComp?.value_range?.mid ? deepComp.value_range : quickComp?.rough_value_band;
    const bestConfidence = deepComp?.confidence || quickComp?.quick_confidence;
    const bestAskVsComps = deepComp?.ai_interpretation?.asking_assessment || quickComp?.asking_vs_comps;

    const listPrice = ld.price || pv?.list_price || undefined;
    const zestimate = ld.zestimate || undefined;
    // Prefer county assessed value (current year) over Zillow's (often stale)
    const countyAssessments = state.countyData?.assessments || [];
    const latestCountyAssessed = countyAssessments.length > 0
        ? countyAssessments[0]?.total_value  // sorted newest first
        : undefined;
    const assessed = latestCountyAssessed || ld.tax_assessed_value || ld.tax_assessed || pv?.assessment_value || undefined;
    const compEstimate = deepComp?.value_range?.mid || deepComp?.ai_interpretation?.value_opinion?.mid || pv?.comp_estimate || quickComp?.rough_value_band?.mid || undefined;

    const parts = [];

    // ── Price Benchmarks ──────────────────────────────────────────
    parts.push(renderPriceBenchmarks(listPrice, zestimate, assessed, undefined, compEstimate));

    // ── Comp Value Band ───────────────────────────────────────────
    if (bestValueBand) {
        const vb = bestValueBand;
        const source = deepComp?.value_range?.mid ? 'Deep Comp (County-Verified)' : 'Quick Comp';
        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Comp Value Band <span class="text-gray-300 normal-case font-normal">${source}</span></div>
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

    // ── AI Value Opinion (deep comp) ─────────────────────────────
    if (deepComp?.ai_interpretation?.value_opinion) {
        const vo = deepComp.ai_interpretation.value_opinion;
        if (vo.reasoning) {
            parts.push(`
            <div class="bg-blue-50 border border-blue-200 rounded p-2.5">
                <div class="text-xs font-medium text-blue-800 mb-0.5">AI Value Opinion</div>
                <p class="text-xs text-blue-700">${escapeHtml(vo.reasoning)}</p>
            </div>`);
        }
    }

    // ── Ask vs Comps Assessment ───────────────────────────────────
    if (bestAskVsComps) {
        const assessment = bestAskVsComps;
        let variant = 'muted';
        if (/below|under/i.test(assessment)) variant = 'success';
        else if (/above|over|high/i.test(assessment)) variant = 'critical';
        else if (/fair|line|par|at/i.test(assessment)) variant = 'info';

        parts.push(`
        <div class="flex items-center gap-2">
            <span class="text-xs text-gray-500">Ask vs Comps:</span>
            ${renderBadge(typeof assessment === 'string' && assessment.length > 20 ? assessment.slice(0, 50) + '…' : assessment, variant, 'sm')}
            ${bestConfidence ? `<span class="text-xs text-gray-400">(${escapeHtml(bestConfidence)} confidence)</span>` : ''}
        </div>`);
    }

    // ── Market Indicators (Redfin) ─────────────────────────────────
    const mi = state.marketData?.indicators;
    if (mi && mi.market_type !== 'unknown') {
        const mktColor = mi.market_type === 'seller' ? 'text-red-600' : mi.market_type === 'buyer' ? 'text-green-600' : 'text-blue-600';
        const cells = [
            `<div><span class="text-[11px] text-gray-500 uppercase">Market</span><div class="text-sm font-semibold ${mktColor}">${escapeHtml(mi.market_type)}</div></div>`,
        ];
        if (mi.months_of_supply != null) cells.push(`<div><span class="text-[11px] text-gray-500 uppercase">Months Supply</span><div class="text-sm font-semibold">${mi.months_of_supply}</div></div>`);
        if (mi.median_dom != null) cells.push(`<div><span class="text-[11px] text-gray-500 uppercase">Median DOM</span><div class="text-sm font-semibold">${Math.round(mi.median_dom)} days</div></div>`);
        if (mi.sale_to_list_avg != null) cells.push(`<div><span class="text-[11px] text-gray-500 uppercase">Sale/List</span><div class="text-sm font-semibold">${(mi.sale_to_list_avg * 100).toFixed(1)}%</div></div>`);
        if (mi.price_trend) cells.push(`<div><span class="text-[11px] text-gray-500 uppercase">Price Trend</span><div class="text-sm font-semibold">${escapeHtml(mi.price_trend)}</div></div>`);
        if (mi.inventory_trend) cells.push(`<div><span class="text-[11px] text-gray-500 uppercase">Inventory</span><div class="text-sm font-semibold">${escapeHtml(mi.inventory_trend)}</div></div>`);

        parts.push(`
        <div>
            <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Market Conditions <span class="text-gray-300 normal-case font-normal">ZIP ${state.marketData?.zip_code || ''} · Redfin</span></div>
            <div class="grid grid-cols-3 sm:grid-cols-6 gap-3">${cells.join('')}</div>
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
