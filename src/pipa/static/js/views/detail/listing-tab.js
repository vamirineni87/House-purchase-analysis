/**
 * Listing tab — DOM/CDOM metrics, price history, AND the rich
 * facts_and_features data parsed by the Zillow scraper:
 *   - Construction (style, materials, foundation, roof, builder)
 *   - HVAC + appliances + laundry
 *   - Interior features (flooring, windows, basement, fireplaces)
 *   - Parking + lot + exterior
 *   - HOA (name, fee, amenities, services)
 *   - Utilities + community
 *   - Per-room layout table
 *   - Tax / financial extras (listing-side)
 *
 * Sections only render when their data exists, so listings with sparse
 * facts collapse cleanly.
 */

import { formatCurrency, escapeHtml } from '../../utils.js';
import { renderMetricCard } from '../../components/metric-card.js';
import { renderBadge } from '../../components/badge.js';

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

/** Render a 2-column key/value table. Skips rows whose value is empty. */
function renderFactTable(title, rows) {
    const filled = rows.filter(([_, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0));
    if (filled.length === 0) return '';
    const body = filled.map(([label, value]) => {
        let display;
        if (Array.isArray(value)) {
            display = value.map(escapeHtml).join(', ');
        } else if (typeof value === 'boolean') {
            display = value ? 'Yes' : 'No';
        } else {
            display = escapeHtml(String(value));
        }
        return `
        <tr>
            <td class="px-3 py-2 text-gray-600 align-top whitespace-nowrap">${escapeHtml(label)}</td>
            <td class="px-3 py-2 text-gray-900">${display}</td>
        </tr>`;
    }).join('');
    return `
    <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-2">${escapeHtml(title)}</h3>
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="min-w-full text-sm">
                <tbody class="divide-y divide-gray-100">${body}</tbody>
            </table>
        </div>
    </div>`;
}

/** Render a chip-style list of strings. */
function renderChipList(title, items) {
    if (!items || items.length === 0) return '';
    const chips = items.map(item =>
        `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700 border border-gray-200">${escapeHtml(item)}</span>`
    ).join(' ');
    return `
    <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-2">${escapeHtml(title)}</h3>
        <div class="flex flex-wrap gap-1">${chips}</div>
    </div>`;
}

/** Render the rooms table — name, level, area sqft, dimensions, features. */
function renderRoomsTable(rooms) {
    if (!rooms || rooms.length === 0) return '';
    const rows = rooms.map(r => {
        const dim = r.dimensions
            ? `${r.dimensions.width} × ${r.dimensions.length}`
            : '';
        const features = (r.features || []).join(', ');
        return `
        <tr>
            <td class="px-3 py-2 font-medium text-gray-900">${escapeHtml(r.name || '')}</td>
            <td class="px-3 py-2 text-gray-600">${escapeHtml(r.level || '--')}</td>
            <td class="px-3 py-2 text-right text-gray-700">${r.area_sqft != null ? r.area_sqft + ' sqft' : '--'}</td>
            <td class="px-3 py-2 text-right text-gray-600">${escapeHtml(dim || '--')}</td>
            <td class="px-3 py-2 text-gray-600 text-xs">${escapeHtml(features)}</td>
        </tr>`;
    }).join('');
    return `
    <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-2">Rooms (${rooms.length})</h3>
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table class="min-w-full text-sm">
                <thead>
                    <tr class="bg-gray-50 text-gray-600 text-left">
                        <th class="px-3 py-2 font-medium">Room</th>
                        <th class="px-3 py-2 font-medium">Level</th>
                        <th class="px-3 py-2 font-medium text-right">Area</th>
                        <th class="px-3 py-2 font-medium text-right">Dim</th>
                        <th class="px-3 py-2 font-medium">Features</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">${rows}</tbody>
            </table>
        </div>
    </div>`;
}

// ---------------------------------------------------------------
// Render
// ---------------------------------------------------------------

export function render(container, state) {
    const ld = state.listingData || {};
    const priceHistory = ld.price_history || [];
    const dom = ld.days_on_zillow || ld.dom || ld.days_on_market;
    const cdom = ld.cdom || ld.cumulative_dom;
    const originalAsk = ld.original_ask;
    const totalReduction = ld.total_reduction;
    const isRelist = ld.is_relist || (cdom && dom && cdom > dom * 1.5);

    // ============================================================
    // Top metrics row (DOM, CDOM, original ask, reductions)
    // ============================================================
    const metricsHtml = `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${renderMetricCard('DOM', dom !== undefined ? String(dom) : '--')}
        ${renderMetricCard('CDOM', cdom !== undefined ? String(cdom) : '--')}
        ${renderMetricCard('Original List', originalAsk ? formatCurrency(Number(originalAsk)) : '--')}
        ${renderMetricCard('Total Reduction', totalReduction ? formatCurrency(Number(totalReduction)) : '--')}
    </div>`;

    // Relist badge
    let relistHtml = '';
    if (isRelist) {
        relistHtml = `
        <div class="flex items-center gap-2">
            ${renderBadge('Relist Detected', 'warning', 'md')}
            <span class="text-xs text-gray-500">CDOM significantly exceeds DOM, indicating a prior listing attempt.</span>
        </div>`;
    }

    // Source link
    let sourceHtml = '';
    const source = ld.source || ld.listing_source || ld._source || '';
    const listingUrl = ld.url || ld.listing_url || ld._url || '';
    if (source || listingUrl) {
        sourceHtml = `
        <div class="flex items-center gap-3 text-xs text-gray-500">
            ${source ? renderBadge(source, 'muted', 'sm') : ''}
            ${listingUrl ? `<a href="${escapeHtml(listingUrl)}" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-700 truncate">${escapeHtml(listingUrl)}</a>` : ''}
        </div>`;
    }

    // ============================================================
    // Bedrooms / Bathrooms
    // ============================================================
    const bedBathTable = renderFactTable('Bedrooms & Bathrooms', [
        ['Bedrooms', ld.bedrooms],
        ['Bathrooms', ld.bathrooms],
        ['Full bathrooms', ld.full_bathrooms],
        ['Half bathrooms', ld.half_bathrooms],
        ['Main level bathrooms', ld.main_level_bathrooms],
    ]);

    // ============================================================
    // Construction & style
    // ============================================================
    const constructionTable = renderFactTable('Construction & Style', [
        ['Architectural style', ld.architectural_style],
        ['Property subtype', ld.property_subtype],
        ['Home type', ld.home_type_listing || ld.home_type],
        ['Year built', ld.year_built],
        ['New construction', ld.is_new_construction],
        ['Builder model', ld.builder_model],
        ['Builder name', ld.builder_name],
        ['Levels', ld.levels],
        ['Stories', ld.stories],
        ['Zillow condition', ld.zillow_condition],
        ['Foundation', ld.foundation_type],
        ['Roof', ld.roof_material],
        ['Exterior materials', ld.exterior_materials],
    ]);

    // ============================================================
    // HVAC + appliances + laundry
    // ============================================================
    const hvacTable = renderFactTable('Heating, Cooling & Appliances', [
        ['Heating', ld.heating_features],
        ['Heating fuel', ld.heating_fuel],
        ['Cooling', ld.cooling_features],
        ['Cooling fuel', ld.cooling_fuel],
        ['Appliances', ld.appliances_included],
        ['Laundry', ld.laundry_features],
    ]);

    // ============================================================
    // Interior features
    // ============================================================
    const interiorTable = renderFactTable('Interior Features', [
        ['Flooring', ld.flooring],
        ['Windows', ld.windows_features],
        ['Basement', ld.basement_features],
        ['Fireplaces', ld.fireplaces_count],
        ['Fireplace features', ld.fireplace_features],
        ['Total structure area', ld.total_structure_area ? `${ld.total_structure_area.toLocaleString()} sqft` : null],
        ['Total livable area', ld.total_livable_area ? `${ld.total_livable_area.toLocaleString()} sqft` : null],
        ['Above ground (finished)', ld.finished_above_ground ? `${ld.finished_above_ground.toLocaleString()} sqft` : null],
        ['Below ground (finished)', ld.finished_below_ground ? `${ld.finished_below_ground.toLocaleString()} sqft` : null],
    ]);
    const interiorChips = renderChipList('Other Interior Features', ld.interior_features);

    // ============================================================
    // Parking
    // ============================================================
    const parkingTable = renderFactTable('Parking', [
        ['Total spaces', ld.parking_total_spaces],
        ['Attached garage spaces', ld.attached_garage_spaces],
        ['Covered spaces', ld.covered_spaces],
        ['Uncovered spaces', ld.uncovered_spaces],
        ['Carport spaces', ld.carport_spaces],
        ['Parking features', ld.parking_features],
    ]);

    // ============================================================
    // Lot & exterior
    // ============================================================
    const lotTable = renderFactTable('Lot & Exterior', [
        ['Lot size', ld.lot_sqft_listing ? `${ld.lot_sqft_listing.toLocaleString()} sqft` : null],
        ['Lot features', ld.lot_features],
        ['Fencing', ld.fencing],
        ['Patio & porch', ld.patio_porch],
        ['Pool', ld.pool_features],
        ['Additional structures', ld.additional_structures],
    ]);

    // ============================================================
    // HOA
    // ============================================================
    let hoaSection = '';
    if (ld.has_hoa || ld.hoa_name || ld.hoa_monthly) {
        const hoaTable = renderFactTable('HOA', [
            ['Has HOA', ld.has_hoa],
            ['HOA name', ld.hoa_name],
            ['Fee', ld.hoa_monthly ? `$${ld.hoa_monthly}/${ld.hoa_frequency || 'mo'}` : null],
        ]);
        const amenitiesChips = renderChipList('HOA Amenities', ld.hoa_amenities);
        const servicesChips = renderChipList('HOA Services Included', ld.hoa_services);
        hoaSection = `${hoaTable}${amenitiesChips}${servicesChips}`;
    }

    // ============================================================
    // Community / utilities
    // ============================================================
    const communityTable = renderFactTable('Community & Utilities', [
        ['Subdivision', ld.subdivision || ld.subdivision_listing],
        ['Region', ld.region],
        ['Security', ld.security_features],
        ['Sewer', ld.sewer],
        ['Water', ld.water],
        ['Utilities', ld.utilities],
        ['Electric', ld.electric],
    ]);

    // ============================================================
    // Tax & financial extras
    // ============================================================
    const financialTable = renderFactTable('Financial & Listing Details', [
        ['Asking price', ld.price ? formatCurrency(Number(ld.price)) : null],
        ['Price per sqft', ld.price_per_sqft ? `$${ld.price_per_sqft}/sqft` : null],
        ['Tax assessed value (listing)', ld.tax_assessed_value_listing ? formatCurrency(Number(ld.tax_assessed_value_listing)) : null],
        ['Annual tax (listing)', ld.annual_tax_listing ? formatCurrency(Number(ld.annual_tax_listing)) : null],
        ['Date on market', ld.date_on_market],
        ['Listing agreement', ld.listing_agreement],
        ['Ownership', ld.ownership_type],
        ['Zoning', ld.zoning],
        ['Special conditions', ld.special_conditions],
        ['MLS ID', ld.mls_id],
        ['Parcel number', ld.parcel_number || ld.parcel_id],
    ]);

    // ============================================================
    // Rooms table
    // ============================================================
    const roomsTable = renderRoomsTable(ld.rooms);

    // ============================================================
    // Price history (existing)
    // ============================================================
    let historyHtml;
    if (priceHistory.length > 0) {
        const rows = priceHistory.map(event => {
            const eventType = event.event_type || event.event || 'unknown';
            const eventVariant = eventType === 'price_change' ? 'warning'
                : eventType === 'listed' ? 'info'
                : eventType === 'sold' ? 'success' : 'muted';
            const price = event.price ? formatCurrency(Number(event.price)) : '--';
            const change = event.change_amount ? formatCurrency(Number(event.change_amount)) : '--';
            const changeClass = event.change_amount && Number(event.change_amount) < 0 ? 'text-green-600' : '';
            return `
            <tr>
                <td class="px-3 py-2">${escapeHtml(event.date || '--')}</td>
                <td class="px-3 py-2">${renderBadge(eventType.replace(/_/g, ' '), eventVariant, 'sm')}</td>
                <td class="px-3 py-2 text-right font-medium">${price}</td>
                <td class="px-3 py-2 text-right ${changeClass}">${change}</td>
            </tr>`;
        }).join('');
        historyHtml = `
        <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">Price History</h3>
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="bg-gray-50 text-gray-600 text-left">
                            <th class="px-3 py-2 font-medium">Date</th>
                            <th class="px-3 py-2 font-medium">Event</th>
                            <th class="px-3 py-2 font-medium text-right">Price</th>
                            <th class="px-3 py-2 font-medium text-right">Change</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">${rows}</tbody>
                </table>
            </div>
        </div>`;
    } else {
        historyHtml = '';
    }

    container.innerHTML = `
    <div class="space-y-6">
        ${metricsHtml}
        ${relistHtml}
        ${sourceHtml}
        ${bedBathTable}
        ${constructionTable}
        ${hvacTable}
        ${interiorTable}
        ${interiorChips}
        ${parkingTable}
        ${lotTable}
        ${hoaSection}
        ${communityTable}
        ${financialTable}
        ${roomsTable}
        ${historyHtml}
    </div>`;
}

export function bind(container, state) {
    // Listing tab is read-only
}
