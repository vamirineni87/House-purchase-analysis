/**
 * Section §4: Key Metrics — dense grid
 *
 * Flat metric cells (no card wrappers) in a responsive grid.
 * Sources: L=listing, C=county, ==computed.
 * Covers listing fields, county building details, and computed values.
 */

import { formatCurrency, formatNumber, escapeHtml } from '../../../utils.js';

// ── Section interface ──────────────────────────────────────────────

export const TITLE = 'Key Metrics';
export const ID = 'key-metrics';
export const DEFAULT_EXPANDED = false;

export function shouldAutoExpand(_state) { return false; }

export function getStateBadge(state) {
    const hasCounty = !!state.countyData;
    const hasListing = !!(state.listingData?.price || state.listingData?.sqft);

    if (hasCounty && hasListing) return { label: 'Complete', variant: 'success' };
    if (hasListing) return { label: 'Partial', variant: 'warning' };
    // Check if county data fetch might be in progress
    const latestTasks = state.latestRun?.tasks || [];
    const countyTask = latestTasks.find(t => /county/i.test(t.task_name));
    if (countyTask && countyTask.status === 'running') return { label: 'Loading', variant: 'info' };
    return { label: 'Not run', variant: 'not-run' };
}

export function headerExtra(_state) { return ''; }

// ── Helpers ────────────────────────────────────────────────────────

/**
 * Render a single flat metric cell.
 * @param {string} label  - Metric label
 * @param {string} value  - Display value
 * @param {string} source - Source hint: L, C, =
 */
function metricCell(label, value, source) {
    const sourceHint = source
        ? `<span class="source-hint">${escapeHtml(source)}</span>`
        : '';
    const safeVal = escapeHtml(value != null ? String(value) : '--');
    const dimmed = safeVal === '--' ? 'opacity-30' : '';
    return `
    <div class="metric-cell">
        <div class="data-label">${escapeHtml(label)}${sourceHint}</div>
        <div class="data-value text-sm ${dimmed}">${safeVal}</div>
    </div>`;
}

/** Strip commas/$  from county values like "3,272" or "$348,800" before converting. */
function _clean(v) {
    if (v == null || v === '') return NaN;
    return Number(String(v).replace(/[$,]/g, ''));
}

function fmtNum(n) {
    const v = _clean(n);
    if (Number.isNaN(v)) return null;
    return v.toLocaleString();
}

function fmtCur(n) {
    const v = _clean(n);
    if (Number.isNaN(v)) return null;
    return formatCurrency(v);
}

/**
 * Extract county building data from countyData.summary
 * (the _summary from the Loudoun County scrape raw_payload).
 *
 * Field names match the LoudounParcelScraper._build_summary() output:
 * sqft_above_grade, full_baths, half_baths, stories, basement_total_sqft,
 * basement_finished_sqft, exterior_wall, roof_type, roof_material,
 * heating_ac, foundation, fireplaces, attic_type, subdivision, condition, grade, etc.
 */
function getCountyFields(state) {
    const cd = state.countyData;
    if (!cd) return {};

    // The summary comes directly from the county scrape raw_payload._summary
    const s = cd.summary || {};

    return {
        sqft_above_grade: s.sqft_above_grade,
        full_baths: s.full_baths,
        half_baths: s.half_baths,
        stories: s.stories,
        basement_total_sqft: s.basement_total_sqft,
        basement_finished_sqft: s.basement_finished_sqft,
        exterior_wall: s.exterior_wall,
        roof_type: s.roof_type,
        roof_material: s.roof_material,
        heating_ac: s.heating_ac,
        foundation: s.foundation,
        fireplaces: s.fireplaces,
        attic_type: s.attic_type,
        subdivision: s.subdivision,
        condition: s.condition,
        grade: s.grade,
        year_built: s.year_built,
        style: s.style,
        model: s.model,
        basement_entrance: s.basement_entrance,
        assessed_total: s.assessed_total,
        assessed_land: s.assessed_land,
        assessed_building: s.assessed_building,
        lot_acres: s.lot_acres,
        owner: s.owner,
        parcel_id: s.parcel_id,
    };
}

// ── Render ─────────────────────────────────────────────────────────

export function render(state) {
    const ld = state.listingData || {};
    const county = getCountyFields(state);
    const prop = state.property || {};

    const cells = [];

    // ── Listing fields (L) ────────────────────────────────────────
    const price = ld.price;
    cells.push(metricCell('Price', fmtCur(price) || '--', 'L'));
    cells.push(metricCell('Beds', ld.bedrooms || ld.beds || '--', 'L'));
    cells.push(metricCell('Baths', ld.bathrooms || ld.baths || '--', 'L'));

    const sqft = ld.sqft ? Number(ld.sqft) : null;
    cells.push(metricCell('Sqft', fmtNum(sqft) || '--', 'L'));

    const lotSqft = ld.lot_sqft ? Number(ld.lot_sqft) : null;
    const lotAcres = ld.lot_acres ? Number(ld.lot_acres) : (county.lot_acres ? parseFloat(county.lot_acres) : null);
    const lotDisplay = lotSqft ? `${fmtNum(lotSqft)} sf` : lotAcres ? `${lotAcres.toFixed(2)} ac` : '--';
    cells.push(metricCell('Lot', lotDisplay, 'L'));

    cells.push(metricCell('Year Built', ld.year_built || '--', 'L'));

    const hoa = ld.hoa_monthly || ld.hoa;
    cells.push(metricCell('HOA', hoa ? `${fmtCur(hoa)}/mo` : '--', 'L'));

    const dom = ld.days_on_zillow ?? ld.dom ?? ld.days_on_market;
    const cdom = ld.cdom ?? ld.cumulative_dom;
    const domDisplay = dom != null
        ? (cdom != null && cdom !== dom ? `${dom} / ${cdom}` : String(dom))
        : '--';
    cells.push(metricCell('DOM/CDOM', domDisplay, 'L'));

    cells.push(metricCell('Type', ld.home_type || '--', 'L'));

    // ── Computed fields (=) ───────────────────────────────────────
    const priceSqft = (price && sqft) ? `${fmtCur(Math.round(price / sqft))}/sf` : '--';
    cells.push(metricCell('$/Sqft', priceSqft, '='));

    const aboveGrade = county.sqft_above_grade ? _clean(county.sqft_above_grade) : null;
    const bsmtFinished = county.basement_finished_sqft ? _clean(county.basement_finished_sqft) : null;
    const totalLivable = (aboveGrade || sqft)
        ? ((aboveGrade || sqft) + (bsmtFinished || 0))
        : null;
    cells.push(metricCell('Livable Sqft', fmtNum(totalLivable) || '--', '='));

    const bsmtTotal = county.basement_total_sqft ? _clean(county.basement_total_sqft) : null;
    const bsmtUnfinished = (bsmtTotal != null && bsmtFinished != null)
        ? bsmtTotal - bsmtFinished
        : null;
    cells.push(metricCell('Unfin. Bsmt', bsmtUnfinished != null && !Number.isNaN(bsmtUnfinished) ? `${fmtNum(bsmtUnfinished)} sf` : '--', '='));

    // ── County fields (C) ─────────────────────────────────────────
    cells.push(metricCell('Sqft Above', fmtNum(aboveGrade) || '--', 'C'));
    cells.push(metricCell('Full Baths', county.full_baths || '--', 'C'));
    cells.push(metricCell('Half Baths', county.half_baths || '--', 'C'));
    cells.push(metricCell('Stories', county.stories || '--', 'C'));
    cells.push(metricCell('Bsmt Total', bsmtTotal ? `${fmtNum(bsmtTotal)} sf` : '--', 'C'));
    cells.push(metricCell('Bsmt Fin.', bsmtFinished ? `${fmtNum(bsmtFinished)} sf` : '--', 'C'));
    cells.push(metricCell('Ext. Wall', county.exterior_wall || '--', 'C'));
    cells.push(metricCell('Roof Type', county.roof_type || '--', 'C'));
    cells.push(metricCell('Roof Matl', county.roof_material || '--', 'C'));
    cells.push(metricCell('HVAC', county.heating_ac || '--', 'C'));
    cells.push(metricCell('Foundation', county.foundation || '--', 'C'));
    cells.push(metricCell('Fireplaces', county.fireplaces != null ? String(county.fireplaces) : '--', 'C'));
    cells.push(metricCell('Attic', county.attic_type || '--', 'C'));
    cells.push(metricCell('Subdivision', county.subdivision || '--', 'C'));
    cells.push(metricCell('Condition', county.condition || '--', 'C'));
    cells.push(metricCell('Grade', county.grade || '--', 'C'));

    // ── Parcel ID ─────────────────────────────────────────────────
    const parcelId = (prop.parcel_identifiers && prop.parcel_identifiers.length > 0)
        ? prop.parcel_identifiers[0].identifier_value
        : null;
    if (parcelId) {
        cells.push(metricCell('Parcel ID', parcelId, ''));
    }

    return `
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-x-6 gap-y-0">
        ${cells.join('')}
    </div>`;
}

// ── Bind ───────────────────────────────────────────────────────────

export function bind(_container, _state, _actions) {
    // Key metrics section is read-only.
}
