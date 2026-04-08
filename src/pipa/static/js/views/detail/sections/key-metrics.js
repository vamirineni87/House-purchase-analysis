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
        ? `<span class="text-[10px] text-gray-300 ml-0.5 align-super">${escapeHtml(source)}</span>`
        : '';
    const safeVal = escapeHtml(value != null ? String(value) : '--');
    const dimmed = safeVal === '--' ? 'opacity-30' : '';
    return `
    <div class="py-1">
        <div class="text-[11px] text-gray-500 uppercase tracking-wide leading-tight">${escapeHtml(label)}${sourceHint}</div>
        <div class="text-sm font-semibold text-gray-900 leading-snug ${dimmed}">${safeVal}</div>
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

/**
 * Render a side-by-side comparison cell when both listing and county
 * have a value. Highlights when they don't agree.
 *
 * Returns a single cell with both values stacked, or a normal cell when
 * only one source has data.
 */
function comparisonCell(label, listingVal, countyVal) {
    const lShow = (listingVal != null && listingVal !== '');
    const cShow = (countyVal != null && countyVal !== '');
    if (!lShow && !cShow) {
        return metricCell(label, '--', '');
    }
    if (lShow && !cShow) {
        return metricCell(label, String(listingVal), 'L');
    }
    if (!lShow && cShow) {
        return metricCell(label, String(countyVal), 'C');
    }
    // Both — stack them; flag mismatch.
    const lStr = String(listingVal).toLowerCase().trim();
    const cStr = String(countyVal).toLowerCase().trim();
    const mismatch = lStr !== cStr;
    const mismatchClass = mismatch ? 'border-l-2 border-amber-400 pl-2' : '';
    return `
    <div class="py-1 ${mismatchClass}">
        <div class="text-[11px] text-gray-500 uppercase tracking-wide leading-tight">${escapeHtml(label)}</div>
        <div class="text-xs leading-snug">
            <span class="text-gray-300">L:</span>
            <span class="font-semibold text-gray-900">${escapeHtml(String(listingVal))}</span>
        </div>
        <div class="text-xs leading-snug">
            <span class="text-gray-300">C:</span>
            <span class="font-semibold text-gray-900">${escapeHtml(String(countyVal))}</span>
        </div>
    </div>`;
}

export function render(state) {
    const ld = state.listingData || {};
    const county = getCountyFields(state);
    const prop = state.property || {};

    const cells = [];

    // ── Pricing & core listing fields ─────────────────────────────
    const price = ld.price;
    cells.push(metricCell('Price', fmtCur(price) || '--', 'L'));
    cells.push(metricCell('Beds', ld.bedrooms || ld.beds || '--', 'L'));
    cells.push(metricCell('Baths', ld.bathrooms || ld.baths || '--', 'L'));

    const sqft = ld.sqft ? Number(ld.sqft) : null;
    cells.push(metricCell('Sqft', fmtNum(sqft) || '--', 'L'));

    const lotSqftListing = ld.lot_sqft_listing || ld.lot_sqft;
    const lotSqft = lotSqftListing ? Number(lotSqftListing) : null;
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

    cells.push(metricCell('Type', ld.home_type_listing || ld.home_type || '--', 'L'));

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

    // ── Side-by-side L vs C comparison cells ─────────────────────
    // These compare listing facts (parsed from facts_and_features) against
    // county records. When they differ, the cell is highlighted.
    cells.push(comparisonCell('Sqft Above',
        ld.finished_above_ground ? `${fmtNum(ld.finished_above_ground)} sf` : null,
        aboveGrade ? `${fmtNum(aboveGrade)} sf` : null));
    cells.push(comparisonCell('Sqft Below',
        ld.finished_below_ground ? `${fmtNum(ld.finished_below_ground)} sf` : null,
        bsmtFinished ? `${fmtNum(bsmtFinished)} sf` : null));
    cells.push(comparisonCell('Stories', ld.stories, county.stories));
    cells.push(comparisonCell('Full Baths', ld.full_bathrooms, county.full_baths));
    cells.push(comparisonCell('Half Baths', ld.half_bathrooms, county.half_baths));
    cells.push(comparisonCell('Fireplaces',
        ld.fireplaces_count != null ? ld.fireplaces_count : null,
        county.fireplaces));
    cells.push(comparisonCell('Subdivision',
        ld.subdivision || ld.subdivision_listing,
        county.subdivision));
    cells.push(comparisonCell('Condition',
        ld.zillow_condition,
        county.condition));
    cells.push(comparisonCell('Style',
        ld.architectural_style,
        county.style));
    cells.push(comparisonCell('Builder Model',
        ld.builder_model,
        county.model));
    cells.push(comparisonCell('Foundation',
        Array.isArray(ld.foundation_type) ? ld.foundation_type.join(', ') : ld.foundation_type,
        county.foundation));
    cells.push(comparisonCell('Roof',
        Array.isArray(ld.roof_material) ? ld.roof_material.join(', ') : ld.roof_material,
        county.roof_material));
    cells.push(comparisonCell('Exterior',
        Array.isArray(ld.exterior_materials) ? ld.exterior_materials.join(', ') : ld.exterior_materials,
        county.exterior_wall));
    cells.push(comparisonCell('Year Built',
        ld.year_built,
        county.year_built));

    // ── Listing-only structural facts (no county equivalent) ─────
    if (ld.heating_fuel) {
        cells.push(metricCell('Heating', ld.heating_fuel, 'L'));
    }
    if (ld.cooling_fuel) {
        cells.push(metricCell('Cooling', ld.cooling_fuel, 'L'));
    }
    if (ld.parking_total_spaces != null) {
        cells.push(metricCell('Parking', String(ld.parking_total_spaces), 'L'));
    }
    if (ld.attached_garage_spaces != null) {
        cells.push(metricCell('Garage', String(ld.attached_garage_spaces), 'L'));
    }
    if (ld.has_hoa && ld.hoa_name) {
        cells.push(metricCell('HOA Name', ld.hoa_name, 'L'));
    }
    if (Array.isArray(ld.hoa_amenities) && ld.hoa_amenities.length > 0) {
        cells.push(metricCell('HOA Amenities', `${ld.hoa_amenities.length} listed`, 'L'));
    }
    if (ld.sewer) {
        cells.push(metricCell('Sewer', ld.sewer, 'L'));
    }
    if (ld.water) {
        cells.push(metricCell('Water', ld.water, 'L'));
    }
    if (ld.zoning) {
        cells.push(metricCell('Zoning', ld.zoning, 'L'));
    }
    if (ld.region) {
        cells.push(metricCell('Region', ld.region, 'L'));
    }
    if (ld.tax_assessed_value_listing) {
        cells.push(metricCell('Tax Assessed', fmtCur(ld.tax_assessed_value_listing) || '--', 'L'));
    }
    if (ld.annual_tax_listing) {
        cells.push(metricCell('Annual Tax', fmtCur(ld.annual_tax_listing) || '--', 'L'));
    }
    if (ld.total_structure_area) {
        cells.push(metricCell('Total Struct.', `${fmtNum(ld.total_structure_area)} sf`, 'L'));
    }
    if (ld.total_livable_area) {
        cells.push(metricCell('Total Livable', `${fmtNum(ld.total_livable_area)} sf`, 'L'));
    }

    // ── County-only fields (no listing equivalent in facts) ───────
    if (county.bsmt_total_sqft || bsmtTotal) {
        cells.push(metricCell('Bsmt Total', bsmtTotal ? `${fmtNum(bsmtTotal)} sf` : '--', 'C'));
    }
    cells.push(metricCell('HVAC (county)', county.heating_ac || '--', 'C'));
    cells.push(metricCell('Roof Type', county.roof_type || '--', 'C'));
    cells.push(metricCell('Attic', county.attic_type || '--', 'C'));
    cells.push(metricCell('Grade', county.grade || '--', 'C'));

    // ── Flood Zone (FEMA) ───────────────────────────────────────
    const flood = state.floodZone;
    if (flood) {
        const riskColor = flood.risk === 'high' ? 'text-red-600 font-bold'
            : flood.risk === 'moderate' ? 'text-amber-600 font-semibold'
            : '';
        const zoneDisplay = `${flood.flood_zone}${flood.zone_subtype ? ' — ' + flood.zone_subtype : ''}`;
        cells.push(metricCell('Flood Zone', flood.flood_zone || '--', 'F'));
        cells.push(metricCell('Flood Risk', flood.risk || '--', 'F'));
        cells.push(metricCell('Flood Ins.', flood.insurance || '--', 'F'));
    }

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
