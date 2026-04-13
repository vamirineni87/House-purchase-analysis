/**
 * Rent vs Sell — assumption input cards (4 collapsible).
 *
 * Pure render + bind helpers. Caller owns state and passes in a
 * scheduleRecompute callback that fires on each field change.
 */

import { escapeHtml } from '../../utils.js';

const CARDS = [
    { key: 'current_home', label: 'Current Home' },
    { key: 'new_home', label: 'New Home' },
    { key: 'market', label: 'Market Assumptions' },
    { key: 'advanced', label: 'Advanced (Refi + Tax)' },
];

export function renderInputs(state) {
    const cardHtml = CARDS.map(c => {
        const expanded = state.expanded[c.key];
        return `
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <button data-rvs-toggle="${escapeHtml(c.key)}" class="w-full flex items-center justify-between px-3 py-2 bg-gray-50 border-b text-left">
                <span class="text-xs font-semibold text-gray-700 uppercase">${escapeHtml(c.label)}</span>
                <span class="text-gray-400">${expanded ? '▾' : '▸'}</span>
            </button>
            ${expanded ? `<div class="p-3">${renderCardFields(c.key, state)}</div>` : ''}
        </div>`;
    }).join('');

    return `<div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">${cardHtml}</div>`;
}

function field(state, path, label, opts = {}) {
    const [group, key] = path.split('.');
    const val = state.inputs[group]?.[key];
    const type = opts.type || (typeof val === 'boolean' ? 'checkbox' : 'number');
    const step = opts.step || 'any';
    const help = opts.help || '';
    if (type === 'checkbox') {
        return `
        <label class="flex items-center gap-1.5 mt-2">
            <input data-rvs-path="${escapeHtml(path)}" type="checkbox" ${val ? 'checked' : ''}
                   class="text-blue-600 border-gray-300 rounded" />
            <span class="text-[11px] text-gray-600">${escapeHtml(label)}</span>
        </label>`;
    }
    if (type === 'select') {
        const opts_ = opts.options || [];
        return `
        <label class="block">
            <span class="text-[11px] text-gray-500">${escapeHtml(label)}</span>
            <select data-rvs-path="${escapeHtml(path)}" class="block w-full mt-0.5 px-2 py-1 text-sm border border-gray-300 rounded">
                ${opts_.map(([k, l]) => `<option value="${escapeHtml(k)}" ${k === val ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}
            </select>
        </label>`;
    }
    if (type === 'text') {
        return `
        <label class="block">
            <span class="text-[11px] text-gray-500">${escapeHtml(label)}</span>
            <input data-rvs-path="${escapeHtml(path)}" type="text" value="${escapeHtml(String(val ?? ''))}"
                   class="block w-full mt-0.5 px-2 py-1 text-sm border border-gray-300 rounded" />
        </label>`;
    }
    return `
    <label class="block">
        <span class="text-[11px] text-gray-500">${escapeHtml(label)}</span>
        <input data-rvs-path="${escapeHtml(path)}" type="number" step="${escapeHtml(step)}" value="${val ?? ''}"
               class="block w-full mt-0.5 px-2 py-1 text-sm border border-gray-300 rounded" />
        ${help ? `<span class="text-[9px] text-gray-400">${escapeHtml(help)}</span>` : ''}
    </label>`;
}

function renderCardFields(cardKey, state) {
    const num = (path, label, step = 'any', help = '') => field(state, path, label, { type: 'number', step, help });
    const check = (path, label) => field(state, path, label, { type: 'checkbox' });
    const text = (path, label) => field(state, path, label, { type: 'text' });
    const select = (path, label, options) => field(state, path, label, { type: 'select', options });

    if (cardKey === 'current_home') {
        return `<div class="grid grid-cols-2 gap-2">
            ${num('current_home.value_today', 'Value today ($)')}
            ${num('current_home.basis', 'Adjusted basis ($)')}
            ${num('current_home.loan_balance', 'Loan balance ($)')}
            ${num('current_home.mortgage_rate', 'Mortgage rate (0.025 = 2.5%)', '0.001')}
            ${num('current_home.monthly_principal_interest', 'Monthly P&I ($)')}
            ${num('current_home.monthly_taxes', 'Monthly taxes ($)')}
            ${num('current_home.monthly_insurance', 'Monthly insurance ($)')}
            ${num('current_home.monthly_hoa', 'Monthly HOA ($)')}
            ${num('current_home.monthly_misc_owner_paid', 'Monthly misc owner-paid ($)')}
            ${num('current_home.insurance_conversion_bump_pct', 'Insurance conversion bump (0.15 = +15%)', '0.01')}
            ${num('current_home.initial_lease_up_vacancy_months', 'Initial lease-up vacancy (months)', '0.5')}
            ${num('current_home.monthly_rent_base', 'Base monthly rent ($)')}
            ${num('current_home.sell_cost_pct_now', 'Sell cost % (0.07 = 7%)', '0.01')}
            ${text('current_home.move_out_month', 'Move out (YYYY-MM)')}
            ${text('current_home.rent_start_month', 'Rent start (YYYY-MM)')}
            ${num('current_home.land_pct', 'Land % (0.30)', '0.01')}
            ${num('current_home.building_pct', 'Building % (0.70)', '0.01')}
            <div class="col-span-2 border-t pt-2 mt-2 text-[10px] font-semibold text-gray-500 uppercase">Landlord operations</div>
            ${check('current_home.self_manage', 'Self-manage')}
            ${num('current_home.property_management_pct', 'Property management % (0.08 = 8%)', '0.01')}
            ${num('current_home.vacancy_months_per_year_base', 'Vacancy months/yr', '0.1')}
            ${num('current_home.bad_debt_pct_of_gross_rent', 'Bad debt %', '0.001')}
            ${num('current_home.leasing_fee_pct_of_annual_rent', 'Leasing fee %', '0.01')}
            ${num('current_home.turnover_cost_per_event', 'Turnover cost ($)')}
            ${num('current_home.turnover_frequency_months', 'Turnover every (months)')}
            ${num('current_home.routine_maintenance_pct_of_rent', 'Maintenance %', '0.01')}
        </div>`;
    }
    if (cardKey === 'new_home') {
        return `<div class="grid grid-cols-2 gap-2">
            ${num('new_home.purchase_price', 'Purchase price ($)')}
            ${num('new_home.base_down_pct', 'Base down % (0.20)', '0.01')}
            ${num('new_home.initial_rate', 'Initial rate (0.0646)', '0.0001')}
            ${num('new_home.loan_term_years', 'Loan term (years)')}
            ${num('new_home.monthly_taxes', 'Monthly taxes ($)')}
            ${num('new_home.monthly_insurance', 'Monthly insurance ($)')}
            ${num('new_home.monthly_hoa', 'Monthly HOA ($)')}
            ${num('new_home_drag.new_home_maintenance_pct_of_home_value_annual', 'New home maintenance %/yr', '0.001')}
        </div>`;
    }
    if (cardKey === 'market') {
        return `<div class="grid grid-cols-2 gap-2">
            ${num('current_home.total_value_change_5y', 'Value change total (5Y)', '0.01', '-0.10 = -10% over 5 years')}
            ${num('current_home.total_value_change_10y', 'Value change total (10Y)', '0.01')}
            ${num('current_home.total_rent_change_5y', 'Rent change total (5Y)', '0.01')}
            ${num('current_home.total_rent_change_10y', 'Rent change total (10Y)', '0.01')}
            ${num('current_home.current_home_sell_cost_pct_future', 'Future sell cost %', '0.01')}
            ${num('current_home.sale_prep_cost_flat', 'Sale prep cost ($)')}
            <div class="col-span-2 border-t pt-2 mt-2 text-[10px] font-semibold text-gray-500 uppercase">Ownership cost growth</div>
            ${num('ownership_cost_growth.current_home_tax_growth_annual_pct', 'Current tax growth', '0.001')}
            ${num('ownership_cost_growth.current_home_insurance_growth_annual_pct', 'Current insurance growth', '0.001')}
            ${num('ownership_cost_growth.new_home_tax_growth_annual_pct', 'New tax growth', '0.001')}
            ${num('ownership_cost_growth.new_home_insurance_growth_annual_pct', 'New insurance growth', '0.001')}
        </div>`;
    }
    if (cardKey === 'advanced') {
        return `<div class="grid grid-cols-2 gap-2">
            ${check('refinance.enabled', 'Refinance enabled')}
            ${select('refinance.selected_path', 'Refi path', [['none','None'],['year3','Year 3'],['year5','Year 5'],['year7','Year 7']])}
            ${num('refinance.year3_rate', 'Y3 rate (0.055)', '0.0001')}
            ${num('refinance.year5_rate', 'Y5 rate (0.0475)', '0.0001')}
            ${num('refinance.year7_rate', 'Y7 rate (0.0425)', '0.0001')}
            ${num('refinance.cost_pct', 'Refi cost %', '0.001')}
            <div class="col-span-2 border-t pt-2 mt-2 text-[10px] font-semibold text-gray-500 uppercase">Taxes</div>
            ${num('taxes.federal_ordinary_rate', 'Federal ordinary rate', '0.01')}
            ${num('taxes.federal_ltcg_rate', 'Federal LTCG rate', '0.01')}
            ${num('taxes.virginia_rate', 'Virginia rate', '0.001')}
            ${check('taxes.niit_enabled', 'NIIT 3.8% on passive income')}
            ${check('taxes.release_suspended_losses_on_taxable_disposition', 'Release suspended losses at sale')}
            <div class="col-span-2 border-t pt-2 mt-2 text-[10px] font-semibold text-gray-500 uppercase">Sell-case reinvestment</div>
            ${check('reinvestment.invest_monthly_sell_savings', 'Reinvest monthly savings')}
            ${num('reinvestment.monthly_savings_reinvestment_return_annual_pct', 'Reinvestment return', '0.01')}
            <div class="col-span-2 border-t pt-2 mt-2 text-[10px] font-semibold text-gray-500 uppercase">Modeling</div>
            ${text('modeling.rent_then_sell_date', 'Rent-Then-Sell date (YYYY-MM)')}
        </div>`;
    }
    return '';
}

export function bindInputs(container, state, handlers) {
    const { onToggleCard, onFieldChange } = handlers;
    container.querySelectorAll('[data-rvs-toggle]').forEach(btn => {
        btn.addEventListener('click', () => onToggleCard(btn.dataset.rvsToggle));
    });
    container.querySelectorAll('[data-rvs-path]').forEach(el => {
        el.addEventListener('change', () => {
            const [group, key] = el.dataset.rvsPath.split('.');
            let val;
            if (el.type === 'checkbox') val = el.checked;
            else if (el.type === 'number') val = el.value === '' ? 0 : parseFloat(el.value);
            else val = el.value;
            onFieldChange(group, key, val);
        });
    });
}
