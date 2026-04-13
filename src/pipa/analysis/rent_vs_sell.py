"""Rent vs Sell analysis engine — pure functions, no I/O.

Given one assumption set, compute four strategies:
  - sell_now      — sell current home, redeploy proceeds into new home
  - keep_5y       — rent current home for 5 years, buy new home on 20% down
  - keep_10y      — same but 10 years
  - rent_then_sell — rent until a configurable sell date (default May 2029)

Design rules (see plan file):
  1. One assumption set -> all four strategies
  2. Sell case uses base down % + net sale proceeds (never hardcoded 55%)
  3. Growth inputs are total horizon changes spread linearly over months
  4. Economic reserve != tax deductions (parallel tracks)
  5. Section 121 with explicit depreciation recapture
  6. Landlord drag modeled explicitly (vacancy, bad debt, turnover, mgmt, maint, capex)
  7. Sell-case reinvestment of monthly savings is first-class
  8. Exit friction for sell-now and sell-later can differ

This engine is called by the API layer; it takes and returns plain dicts so it
can be serialized without Pydantic dependencies.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Versioning — bump CALC_VERSION when any formula changes
# ─────────────────────────────────────────────────────────────────────

CALC_VERSION = "1.1.0"
INPUT_SCHEMA_VERSION = "1.1.0"

LEAN_THRESHOLD_DOLLARS = 25_000.0  # |delta| below this -> "too_close"

# Hard clamps — prevent pathological inputs from crashing math or eating memory.
MAX_HORIZON_MONTHS = 600             # 50 years
MIN_GROWTH_RATE = -0.999             # (1 + pct) ** (1/12) explodes near -1
MAX_GROWTH_RATE = 1.0                # +100% annual is the outer bound
MAX_LOAN_TERM_MONTHS = 600
MAX_CAPEX_RECURRENCES = 240          # per-item cap inside the horizon


# ─────────────────────────────────────────────────────────────────────
# Core primitives
# ─────────────────────────────────────────────────────────────────────


def _safe_float(x: Any, default: float = 0.0) -> float:
    """Coerce to a finite float or return `default`.

    Protects mortgage/growth math from inf / nan / None / strings the
    frontend might send after parseFloat('') etc.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return v


def _clamp_growth(pct: float) -> float:
    """Clamp a growth rate so `(1 + pct) ** (1/12)` is always defined."""
    v = _safe_float(pct, 0.0)
    if v <= MIN_GROWTH_RATE:
        return MIN_GROWTH_RATE
    if v > MAX_GROWTH_RATE:
        return MAX_GROWTH_RATE
    return v


def monthly_payment(principal: float, annual_rate: float, term_months: int) -> float:
    """Standard amortization formula."""
    principal = max(0.0, _safe_float(principal))
    annual_rate = _safe_float(annual_rate)
    term_months = max(0, int(term_months or 0))
    if principal <= 0 or term_months <= 0:
        return 0.0
    if annual_rate <= 0:
        return principal / term_months
    r = annual_rate / 12.0
    factor = (1 + r) ** term_months
    return principal * (r * factor) / (factor - 1)


def mortgage_schedule(
    principal: float, annual_rate: float, term_months: int
) -> list[dict]:
    """Return month-by-month schedule.

    Each row: {month, payment, principal, interest, balance}. Month index
    starts at 1. Length = min(term_months, MAX_LOAN_TERM_MONTHS).
    """
    principal = max(0.0, _safe_float(principal))
    annual_rate = _safe_float(annual_rate)
    term_months = max(0, min(int(term_months or 0), MAX_LOAN_TERM_MONTHS))
    schedule: list[dict] = []
    if principal <= 0 or term_months <= 0:
        return schedule
    payment = monthly_payment(principal, annual_rate, term_months)
    r = annual_rate / 12.0
    balance = principal
    for m in range(1, term_months + 1):
        interest = balance * r
        prin = payment - interest
        balance = max(0.0, balance - prin)
        schedule.append(
            {
                "month": m,
                "payment": payment,
                "principal": prin,
                "interest": interest,
                "balance": balance,
            }
        )
    return schedule


def refi_schedule(
    original: list[dict],
    refi_month: int,
    new_rate: float,
    new_term_months: int,
    refi_cost_pct: float,
) -> tuple[list[dict], float]:
    """Splice original[:refi_month] with a new loan at the current balance.

    Returns (new_schedule, refi_cost_dollars). The new schedule uses month
    numbering continuous with the original so callers can slice by month.
    """
    if refi_month <= 0 or refi_month >= len(original):
        return original, 0.0
    # Balance at end of refi_month (i.e., after that month's payment)
    balance_at_refi = original[refi_month - 1]["balance"]
    if balance_at_refi <= 0:
        return original, 0.0
    new_payment = monthly_payment(balance_at_refi, new_rate, new_term_months)
    r = new_rate / 12.0
    new_part: list[dict] = []
    bal = balance_at_refi
    for i in range(new_term_months):
        month_num = refi_month + 1 + i
        interest = bal * r
        prin = new_payment - interest
        bal = max(0.0, bal - prin)
        new_part.append(
            {
                "month": month_num,
                "payment": new_payment,
                "principal": prin,
                "interest": interest,
                "balance": bal,
            }
        )
    spliced = original[:refi_month] + new_part
    refi_cost = balance_at_refi * refi_cost_pct
    return spliced, refi_cost


def linear_growth_path(start: float, total_change_pct: float, months: int) -> list[float]:
    """Spread total change evenly over months.

    Returns `months + 1` values so both endpoints are accessible. path[0] is
    the starting value and path[months] is the endpoint.
    """
    start = _safe_float(start)
    total_change_pct = _clamp_growth(total_change_pct)
    months = max(0, min(int(months or 0), MAX_HORIZON_MONTHS))
    if months <= 0:
        return [start]
    return [start * (1 + total_change_pct * (m / months)) for m in range(months + 1)]


def compute_depreciation(
    adjusted_basis: float,
    building_pct: float,
    months_active: int,
    fmv_at_conversion: float | None = None,
    mid_month_start: bool = True,
    mid_month_end: bool = False,
) -> float:
    """Total depreciation taken over `months_active`.

    `depreciable = min(adjusted_basis, fmv_at_conversion) * building_pct`
    (the min matters for former-PR-to-rental conversions where FMV > basis).
    Annual depreciation = depreciable / 27.5 (residential rental, straight-line).

    Mid-month convention: the placed-in-service month and the disposition
    month (when present) each count as half a month. A property held through
    12 full months starting mid-month gets `annual * 11.5 / 12` — NOT
    `annual * 11 / 12`, which was the previous bug.

    Args:
        mid_month_start: True if the property's first month is partial
            (placed in service mid-month). Default True — applies to most
            rental conversions.
        mid_month_end: True if the last month is partial (disposition
            during the model horizon). Default False — set to True for
            rent-then-sell scenarios closing mid-month.
    """
    adjusted_basis = max(0.0, _safe_float(adjusted_basis))
    building_pct = max(0.0, min(1.0, _safe_float(building_pct)))
    months_active = max(0, int(months_active or 0))
    if fmv_at_conversion is not None:
        fmv = max(0.0, _safe_float(fmv_at_conversion))
        basis_for_dep = min(adjusted_basis, fmv)
    else:
        basis_for_dep = adjusted_basis
    depreciable = basis_for_dep * building_pct
    annual = depreciable / 27.5
    if months_active == 0:
        return 0.0
    # Effective months after half-month adjustments
    effective = float(months_active)
    if mid_month_start:
        effective -= 0.5
    if mid_month_end:
        effective -= 0.5
    # Single-month hold with both flags: clamp to 0.5 months so we never
    # return negative or zero depreciation for a real partial month.
    if effective <= 0:
        effective = 0.5 if months_active >= 1 else 0.0
    return annual * (effective / 12.0)


def monthly_owner_cost_path(
    start_monthly: float, annual_growth_pct: float, months: int
) -> list[float]:
    """Compound a monthly cost over `months`.

    Uses annual compounding converted to a monthly rate so property taxes
    and insurance track reasonably over the horizon. Returns `months + 1`
    values.
    """
    start_monthly = _safe_float(start_monthly)
    annual_growth_pct = _clamp_growth(annual_growth_pct)
    months = max(0, min(int(months or 0), MAX_HORIZON_MONTHS))
    if months <= 0:
        return [start_monthly]
    monthly_rate = (1 + annual_growth_pct) ** (1 / 12) - 1
    return [start_monthly * ((1 + monthly_rate) ** m) for m in range(months + 1)]


def reinvestment_path(monthly_contributions: list[float], annual_return_pct: float) -> float:
    """Monthly-compound a stream of contributions and return the ending value."""
    if not monthly_contributions:
        return 0.0
    annual_return_pct = _clamp_growth(annual_return_pct)
    monthly_rate = (1 + annual_return_pct) ** (1 / 12) - 1
    balance = 0.0
    for contrib in monthly_contributions:
        balance = balance * (1 + monthly_rate) + _safe_float(contrib)
    return balance


# ─────────────────────────────────────────────────────────────────────
# Landlord-drag primitives
# ─────────────────────────────────────────────────────────────────────


def vacancy_and_turnover_path(
    rent_path: list[float],
    months: int,
    vacancy_months_per_year: float,
    bad_debt_pct: float,
    leasing_fee_pct_annual: float,
    turnover_cost: float,
    turnover_frequency_months: int,
    initial_lease_up_vacancy_months: float,
) -> list[dict]:
    """Compute per-month landlord-loss economics.

    Vacancy is applied as a pro-rata monthly loss (vacancy_months / 12).
    Turnover cost + leasing fee fire every `turnover_frequency_months`.
    The initial lease-up zeros out rent for the first
    `initial_lease_up_vacancy_months` months.
    """
    out: list[dict] = []
    monthly_vacancy_fraction = vacancy_months_per_year / 12.0
    turnover_months_used = (
        turnover_frequency_months if turnover_frequency_months and turnover_frequency_months > 0 else 0
    )
    for m in range(months):
        gross = rent_path[m] if m < len(rent_path) else 0.0
        # Lease-up: first N months have zero rent collection
        if m < initial_lease_up_vacancy_months:
            # Treat partial months as fractional loss
            lease_up_loss = gross * max(0.0, min(1.0, initial_lease_up_vacancy_months - m))
        else:
            lease_up_loss = 0.0
        stabilized_vacancy_loss = gross * monthly_vacancy_fraction
        vacancy_loss = min(gross, lease_up_loss + stabilized_vacancy_loss)

        bad_debt_loss = max(0.0, gross - vacancy_loss) * bad_debt_pct

        leasing_fee = 0.0
        turnover_fee = 0.0
        # Turnover events hit every N months, but NOT at m=0 (first tenant
        # leasing fee is captured by the initial lease-up event)
        if turnover_months_used and m > 0 and (m % turnover_months_used) == 0:
            turnover_fee = turnover_cost
            annual_rent_estimate = gross * 12
            leasing_fee = annual_rent_estimate * leasing_fee_pct_annual
        # Month 0 — initial lease-up also triggers a leasing fee (one-time)
        if m == 0:
            leasing_fee = gross * 12 * leasing_fee_pct_annual

        collected = max(0.0, gross - vacancy_loss - bad_debt_loss)
        out.append(
            {
                "month": m + 1,
                "gross_rent": gross,
                "vacancy_loss": vacancy_loss,
                "bad_debt_loss": bad_debt_loss,
                "leasing_fee": leasing_fee,
                "turnover_cost": turnover_fee,
                "collected_rent": collected,
            }
        )
    return out


def capex_events_for_horizon(
    capex_items: list[dict], months: int, home_scope: str
) -> list[float]:
    """Expand CapexItem records into a month-indexed list of cash events.

    Returns `months` entries. Each element is the total capex cash flow
    in that month. Items filter by `applies_to ∈ {current_home, new_home, both}`.

    Hardened against malicious / malformed `recurring_months` values:
    - fractional values truncate to 0 and are treated as non-recurring
    - each item can fire at most `MAX_CAPEX_RECURRENCES` times
    """
    months = max(0, min(int(months or 0), MAX_HORIZON_MONTHS))
    out = [0.0] * months
    if not capex_items or months == 0:
        return out
    for item in capex_items:
        if not isinstance(item, dict):
            continue
        applies_to = item.get("applies_to", "current_home")
        if applies_to not in (home_scope, "both"):
            continue
        amount = _safe_float(item.get("amount"))
        try:
            month_offset = int(item.get("month_offset", 0) or 0)
        except (TypeError, ValueError):
            continue
        if amount == 0 or month_offset < 0:
            continue
        # First hit
        if 0 <= month_offset < months:
            out[month_offset] += amount
        # Recurring hits — coerce step to int FIRST, then check > 0
        step = 0
        try:
            step = int(_safe_float(item.get("recurring_months"), 0))
        except (TypeError, ValueError):
            step = 0
        if step <= 0:
            continue
        next_m = month_offset + step
        fired = 0
        while next_m < months and fired < MAX_CAPEX_RECURRENCES:
            out[next_m] += amount
            next_m += step
            fired += 1
    return out


def maintenance_path(
    rent_path: list[float],
    months: int,
    routine_maintenance_pct_of_rent: float,
    maintenance_inflation_annual_pct: float,
) -> list[float]:
    """Routine maintenance as a percent of contract rent, inflation-aware.

    The percentage itself inflates over time at `maintenance_inflation_annual_pct`.
    """
    monthly_inflation = (1 + maintenance_inflation_annual_pct) ** (1 / 12) - 1
    out: list[float] = []
    pct = routine_maintenance_pct_of_rent
    for m in range(months):
        rent = rent_path[m] if m < len(rent_path) else 0.0
        out.append(rent * pct)
        pct *= 1 + monthly_inflation
    return out


# ─────────────────────────────────────────────────────────────────────
# Output dataclasses
# ─────────────────────────────────────────────────────────────────────


@dataclass
class AnnualTaxModel:
    year: int
    taxable_rental_income: float = 0.0
    depreciation_taken: float = 0.0
    suspended_loss_created: float = 0.0
    suspended_loss_balance_end: float = 0.0
    current_tax_paid: float = 0.0
    current_tax_saved: float = 0.0


@dataclass
class SaleTaxModel:
    gross_gain: float = 0.0
    section_121_excluded_gain: float = 0.0
    depreciation_recap_bucket: float = 0.0
    taxable_cap_gain_bucket: float = 0.0
    estimated_sale_tax: float = 0.0
    suspended_loss_used_at_sale: float = 0.0
    suspended_loss_remainder: float = 0.0
    suspended_loss_tax_benefit: float = 0.0


@dataclass
class RentalOperationsModel:
    year: int
    gross_rent: float = 0.0
    vacancy_loss: float = 0.0
    bad_debt_loss: float = 0.0
    leasing_fee: float = 0.0
    turnover_cost: float = 0.0
    management_fee: float = 0.0
    collected_rent: float = 0.0


@dataclass
class MaintenanceCapexModel:
    year: int
    routine_maintenance: float = 0.0
    explicit_capex_total: float = 0.0
    explicit_capex_events: list[dict] = field(default_factory=list)
    sale_prep_cost: float = 0.0
    pre_sale_vacancy_cost: float = 0.0


@dataclass
class ReinvestmentModel:
    monthly_savings_invested: float = 0.0
    surplus_cash_invested: float = 0.0
    ending_investment_value: float = 0.0


@dataclass
class StrategyDriverBridge:
    trapped_equity_redeployment_benefit: float = 0.0
    extra_new_home_interest_cost: float = 0.0
    rental_cashflow_after_tax: float = 0.0
    vacancy_and_bad_debt_drag: float = 0.0
    leasing_and_turnover_drag: float = 0.0
    property_management_drag: float = 0.0
    routine_maintenance_drag: float = 0.0
    capex_drag_current_home: float = 0.0
    capex_drag_new_home: float = 0.0
    current_home_appreciation_effect: float = 0.0
    current_home_principal_paydown: float = 0.0
    ownership_cost_growth_effect: float = 0.0
    sale_tax_difference: float = 0.0
    future_sale_friction_difference: float = 0.0
    reinvestment_benefit_sell_case: float = 0.0
    refi_effect: float = 0.0
    reserve_drag: float = 0.0
    residual_other: float = 0.0


@dataclass
class StrategyOutput:
    name: str
    net_worth_end: float = 0.0
    monthly_stress: float = 0.0
    monthly_stress_delta_vs_sell: float = 0.0
    annual_tax_model: list[AnnualTaxModel] = field(default_factory=list)
    rental_ops_model: list[RentalOperationsModel] | None = None
    maintenance_capex_model: list[MaintenanceCapexModel] | None = None
    reinvestment_model: ReinvestmentModel | None = None
    sale_tax_model: SaleTaxModel | None = None
    driver_bridge_vs_sell: StrategyDriverBridge | None = None
    tax_disclaimer_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Internal / detail fields useful for charts
    net_worth_path: list[float] = field(default_factory=list)
    monthly_cashflow_path: list[float] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# Input helpers — tolerant getters for plain dicts
# ─────────────────────────────────────────────────────────────────────


def _get(d: dict, key: str, default: Any = None) -> Any:
    if not d:
        return default
    val = d.get(key, default)
    return default if val is None else val


_MONTH_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})\s*$")


def _parse_month(s: str | None) -> date | None:
    """Parse a strict 'YYYY-MM' string. Returns None for any malformed input."""
    if not isinstance(s, str):
        return None
    m = _MONTH_RE.match(s)
    if not m:
        return None
    try:
        year = int(m.group(1))
        month = int(m.group(2))
        if not (1900 <= year <= 2100) or not (1 <= month <= 12):
            return None
        return date(year, month, 1)
    except (ValueError, OverflowError):
        return None


def _month_diff(a: str | None, b: str | None) -> int:
    """Return months from month-string `a` (YYYY-MM) to `b` (YYYY-MM).

    Strict parse — returns 0 if either side is malformed.
    """
    pa = _parse_month(a)
    pb = _parse_month(b)
    if pa is None or pb is None:
        return 0
    return (pb.year - pa.year) * 12 + (pb.month - pa.month)


# ─────────────────────────────────────────────────────────────────────
# Strategy computations
# ─────────────────────────────────────────────────────────────────────


def _new_home_monthly_carry(new_home: dict, loan_payment: float) -> float:
    """Total monthly carrying cost for the new home."""
    return (
        loan_payment
        + _get(new_home, "monthly_hoa", 0)
        + _get(new_home, "monthly_taxes", 0)
        + _get(new_home, "monthly_insurance", 0)
    )


def _combined_tax_rate(taxes: dict) -> float:
    """Effective combined marginal rate (ordinary + VA + optional NIIT)."""
    rate = _get(taxes, "federal_ordinary_rate", 0.24) + _get(taxes, "virginia_rate", 0.0575)
    if _get(taxes, "niit_enabled", False):
        rate += _get(taxes, "niit_rate", 0.038)
    return rate


def _ltcg_tax_rate(taxes: dict) -> float:
    rate = _get(taxes, "federal_ltcg_rate", 0.15) + _get(taxes, "virginia_rate", 0.0575)
    if _get(taxes, "niit_enabled", False):
        rate += _get(taxes, "niit_rate", 0.038)
    return rate


def _new_home_schedule_with_refi(new_home: dict, refinance: dict) -> tuple[list[dict], float]:
    """Build new-home amortization + apply the selected refi path, if any."""
    price = _get(new_home, "purchase_price", 0)
    base_down = _get(new_home, "base_down_pct", 0.20)
    rate = _get(new_home, "initial_rate", 0.0646)
    term_months = int(_get(new_home, "loan_term_years", 30)) * 12
    down_payment = price * base_down
    loan_amount = max(0.0, price - down_payment)
    schedule = mortgage_schedule(loan_amount, rate, term_months)

    refi_cost = 0.0
    selected = _get(refinance, "selected_path", "none")
    if _get(refinance, "enabled", False) and selected != "none":
        year_map = {"year3": (3, _get(refinance, "year3_rate", 0.055)),
                    "year5": (5, _get(refinance, "year5_rate", 0.0475)),
                    "year7": (7, _get(refinance, "year7_rate", 0.0425))}
        if selected in year_map:
            yr, new_rate = year_map[selected]
            refi_month = yr * 12
            remaining_term = max(term_months - refi_month, 60)
            schedule, refi_cost = refi_schedule(
                schedule,
                refi_month,
                new_rate,
                remaining_term,
                _get(refinance, "cost_pct", 0.015),
            )
    return schedule, refi_cost


def _sell_case_new_home_schedule(
    new_home: dict, refinance: dict, extra_proceeds: float
) -> tuple[list[dict], float, float]:
    """Build the new-home schedule with extra proceeds applied to down payment.

    Returns (schedule, refi_cost, effective_down_payment_dollars).
    """
    price = _get(new_home, "purchase_price", 0)
    base_down_pct = _get(new_home, "base_down_pct", 0.20)
    base_down = price * base_down_pct
    total_down = min(price, base_down + max(0.0, extra_proceeds))
    loan_amount = max(0.0, price - total_down)
    rate = _get(new_home, "initial_rate", 0.0646)
    term_months = int(_get(new_home, "loan_term_years", 30)) * 12
    schedule = mortgage_schedule(loan_amount, rate, term_months)

    refi_cost = 0.0
    selected = _get(refinance, "selected_path", "none")
    if _get(refinance, "enabled", False) and selected != "none":
        year_map = {"year3": (3, _get(refinance, "year3_rate", 0.055)),
                    "year5": (5, _get(refinance, "year5_rate", 0.0475)),
                    "year7": (7, _get(refinance, "year7_rate", 0.0425))}
        if selected in year_map:
            yr, new_rate = year_map[selected]
            refi_month = yr * 12
            remaining_term = max(term_months - refi_month, 60)
            schedule, refi_cost = refi_schedule(
                schedule,
                refi_month,
                new_rate,
                remaining_term,
                _get(refinance, "cost_pct", 0.015),
            )
    return schedule, refi_cost, total_down


def compute_sell_now(inputs: dict, horizon_months: int) -> StrategyOutput:
    """Sell the current home immediately and redeploy all proceeds."""
    ch = inputs.get("current_home", {})
    nh = inputs.get("new_home", {})
    refi = inputs.get("refinance", {})
    taxes = inputs.get("taxes", {})
    reinv = inputs.get("reinvestment", {})

    value_today = _get(ch, "value_today", 0)
    sell_cost_pct = _get(ch, "sell_cost_pct_now", 0.07)
    loan_balance = _get(ch, "loan_balance", 0)
    basis = _get(ch, "basis", value_today)
    sale_prep = _get(ch, "sale_prep_cost_flat", 3000)

    gross_proceeds = value_today * (1 - sell_cost_pct) - sale_prep
    gain = gross_proceeds - basis
    exclusion = _get(taxes, "section_121_mfj", 500_000)
    excluded = min(max(gain, 0.0), exclusion)
    taxable_gain = max(0.0, gain - excluded)
    sale_tax = taxable_gain * _ltcg_tax_rate(taxes)
    net_after_tax_proceeds = max(0.0, gross_proceeds - loan_balance - sale_tax)

    schedule, refi_cost, effective_down = _sell_case_new_home_schedule(
        nh, refi, net_after_tax_proceeds
    )

    # New-home ownership costs over horizon
    nh_price = _get(nh, "purchase_price", 0)
    tax_path = monthly_owner_cost_path(
        _get(nh, "monthly_taxes", 0),
        _get(inputs.get("ownership_cost_growth", {}), "new_home_tax_growth_annual_pct", 0.03),
        horizon_months,
    )
    ins_path = monthly_owner_cost_path(
        _get(nh, "monthly_insurance", 0),
        _get(inputs.get("ownership_cost_growth", {}), "new_home_insurance_growth_annual_pct", 0.05),
        horizon_months,
    )
    hoa_path = monthly_owner_cost_path(
        _get(nh, "monthly_hoa", 0),
        _get(inputs.get("ownership_cost_growth", {}), "new_home_hoa_growth_annual_pct", 0.03),
        horizon_months,
    )

    # New-home maintenance + capex drag
    nh_maint_pct = _get(inputs.get("new_home_drag", {}), "new_home_maintenance_pct_of_home_value_annual", 0.01)
    nh_monthly_maint = (nh_price * nh_maint_pct) / 12.0
    nh_capex = capex_events_for_horizon(inputs.get("new_home_capex_items", []), horizon_months, "new_home")

    # Monthly net worth path + monthly cashflow path
    nw_path: list[float] = []
    cf_path: list[float] = []
    cumulative_maint_drag = 0.0
    cumulative_capex_drag = 0.0
    cumulative_cost_growth = 0.0
    baseline_tax_ins_hoa = tax_path[0] + ins_path[0] + hoa_path[0]
    for m in range(horizon_months):
        row = schedule[m] if m < len(schedule) else {"payment": 0.0, "balance": 0.0, "interest": 0.0}
        monthly_payment_total = row["payment"] + tax_path[m] + ins_path[m] + hoa_path[m] + nh_monthly_maint + nh_capex[m]
        cf_path.append(-monthly_payment_total)
        cumulative_maint_drag += nh_monthly_maint
        cumulative_capex_drag += nh_capex[m]
        cumulative_cost_growth += (tax_path[m] + ins_path[m] + hoa_path[m]) - baseline_tax_ins_hoa
        equity = max(0.0, nh_price - row["balance"])
        nw_path.append(equity)

    loan_balance_end = schedule[horizon_months - 1]["balance"] if horizon_months <= len(schedule) else 0.0
    new_home_equity_end = max(0.0, nh_price - loan_balance_end)

    # Reinvestment — populated later in aggregator when we know the keep payment
    reinvestment_model = None
    if _get(reinv, "invest_initial_sale_surplus_cash", False):
        surplus = max(0.0, effective_down - nh_price * _get(nh, "base_down_pct", 0.20) - nh_price * 0 - 0)
        # Surplus beyond what could be applied to the house itself is rare; left as 0 unless price-cap
        surplus_ending = 0.0
        reinvestment_model = ReinvestmentModel(
            monthly_savings_invested=0.0,
            surplus_cash_invested=0.0,
            ending_investment_value=surplus_ending,
        )

    monthly_stress = _new_home_monthly_carry(
        nh, schedule[0]["payment"] if schedule else 0.0
    ) + nh_monthly_maint

    return StrategyOutput(
        name="sell_now",
        net_worth_end=(
            new_home_equity_end
            - refi_cost
            - cumulative_capex_drag
            - cumulative_maint_drag
        ),
        monthly_stress=monthly_stress,
        monthly_stress_delta_vs_sell=0.0,  # baseline
        annual_tax_model=[],  # no rental operations
        rental_ops_model=None,
        maintenance_capex_model=None,
        reinvestment_model=reinvestment_model,
        sale_tax_model=SaleTaxModel(
            gross_gain=gain,
            section_121_excluded_gain=excluded,
            depreciation_recap_bucket=0.0,
            taxable_cap_gain_bucket=taxable_gain,
            estimated_sale_tax=sale_tax,
        ),
        driver_bridge_vs_sell=None,
        tax_disclaimer_flags=["section_121_assumed"],
        warnings=_sell_now_warnings(inputs, net_after_tax_proceeds),
        net_worth_path=nw_path,
        monthly_cashflow_path=cf_path,
    )


def _sell_now_warnings(inputs: dict, net_after_tax: float) -> list[str]:
    w: list[str] = []
    if net_after_tax < 0:
        w.append("negative_sell_proceeds")
    elif net_after_tax < 10_000:
        w.append("tiny_sell_proceeds")
    return w


def compute_keep_rental(
    inputs: dict, horizon_months: int, strategy_name: str
) -> StrategyOutput:
    """Keep current home as rental, buy new home on base 20% down.

    `strategy_name` is one of "keep_5y" / "keep_10y" / "rent_then_sell" —
    controls how the ending net worth is computed and whether a sale closes
    inside the horizon.
    """
    ch = inputs.get("current_home", {})
    nh = inputs.get("new_home", {})
    refi = inputs.get("refinance", {})
    taxes = inputs.get("taxes", {})
    reinv = inputs.get("reinvestment", {})

    value_today = _get(ch, "value_today", 0)
    loan_balance = _get(ch, "loan_balance", 0)
    mortgage_rate = _get(ch, "mortgage_rate", 0.025)
    basis = _get(ch, "basis", value_today)
    monthly_rent_base = _get(ch, "monthly_rent_base", 0)

    # Growth paths
    total_value_change = _get(
        ch,
        "total_value_change_10y" if horizon_months >= 120 else "total_value_change_5y",
        0.0,
    )
    total_rent_change = _get(
        ch,
        "total_rent_change_10y" if horizon_months >= 120 else "total_rent_change_5y",
        0.0,
    )
    value_path = linear_growth_path(value_today, total_value_change, horizon_months)
    rent_path = linear_growth_path(monthly_rent_base, total_rent_change, horizon_months)

    # Current mortgage remaining amortization. Prefer an explicit remaining
    # term from the user; fall back to deriving from the existing monthly PI
    # payment; last-resort 360 months.
    remaining_term_months = int(_get(ch, "remaining_term_months", 0) or 0)
    if remaining_term_months <= 0:
        explicit_pi = _safe_float(_get(ch, "monthly_principal_interest", 0))
        if explicit_pi > 0 and loan_balance > 0 and mortgage_rate > 0:
            # Solve for n: PI = P * r(1+r)^n / ((1+r)^n - 1)
            # -> (1+r)^n = PI / (PI - P*r)
            r = mortgage_rate / 12.0
            denom = explicit_pi - loan_balance * r
            if denom > 0:
                try:
                    n = math.log(explicit_pi / denom) / math.log(1 + r)
                    remaining_term_months = max(1, int(round(n)))
                except (ValueError, ZeroDivisionError):
                    remaining_term_months = 360
            else:
                remaining_term_months = 360
        else:
            remaining_term_months = 360
    remaining_term_months = max(horizon_months, min(remaining_term_months, MAX_LOAN_TERM_MONTHS))
    ch_schedule = mortgage_schedule(loan_balance, mortgage_rate, remaining_term_months)

    # Vacancy / turnover / bad debt
    vac_turn = vacancy_and_turnover_path(
        rent_path,
        horizon_months,
        vacancy_months_per_year=_get(ch, "vacancy_months_per_year_base", 0.5),
        bad_debt_pct=_get(ch, "bad_debt_pct_of_gross_rent", 0.005),
        leasing_fee_pct_annual=_get(ch, "leasing_fee_pct_of_annual_rent", 0.05),
        turnover_cost=_get(ch, "turnover_cost_per_event", 2500),
        turnover_frequency_months=int(_get(ch, "turnover_frequency_months", 24)),
        initial_lease_up_vacancy_months=_get(ch, "initial_lease_up_vacancy_months", 1.0),
    )

    # Maintenance
    maint = maintenance_path(
        rent_path,
        horizon_months,
        _get(ch, "routine_maintenance_pct_of_rent", 0.05),
        _get(ch, "maintenance_inflation_annual_pct", 0.03),
    )

    # Capex events
    ch_capex = capex_events_for_horizon(inputs.get("current_home_capex_items", []), horizon_months, "current_home")

    # Ocg — ownership cost growth applied to each bucket
    ocg = inputs.get("ownership_cost_growth", {})
    tax_path = monthly_owner_cost_path(
        _get(ch, "monthly_taxes", 0),
        _get(ocg, "current_home_tax_growth_annual_pct", 0.03),
        horizon_months,
    )
    starting_insurance = _get(ch, "monthly_insurance", 0) * (
        1 + _get(ch, "insurance_conversion_bump_pct", 0.15)
    )
    ins_path = monthly_owner_cost_path(
        starting_insurance,
        _get(ocg, "current_home_insurance_growth_annual_pct", 0.05),
        horizon_months,
    )
    hoa_path = monthly_owner_cost_path(
        _get(ch, "monthly_hoa", 0),
        _get(ocg, "current_home_hoa_growth_annual_pct", 0.03),
        horizon_months,
    )
    misc_path = monthly_owner_cost_path(
        _get(ch, "monthly_misc_owner_paid", 0),
        _get(ocg, "current_home_misc_growth_annual_pct", 0.03),
        horizon_months,
    )

    # Property management fee
    mgmt_pct = 0.0 if _get(ch, "self_manage", True) else _get(ch, "property_management_pct", 0.08)

    # Depreciation (27.5yr residential SL). Mid-month convention gives the
    # first calendar year 11.5/12 of the annual amount, full years after
    # that, and a final partial year when rent_then_sell closes inside
    # the horizon.
    building_pct = _safe_float(_get(ch, "building_pct", 0.7))
    dep_basis_total = min(_safe_float(basis), _safe_float(value_today))
    building_basis = dep_basis_total * building_pct
    annual_depreciation = building_basis / 27.5
    # First-year proration via compute_depreciation helper
    first_year_dep = compute_depreciation(
        adjusted_basis=basis,
        building_pct=building_pct,
        months_active=12,
        fmv_at_conversion=value_today,
        mid_month_start=True,
        mid_month_end=False,
    )

    # Loop per month; collect cashflow, then fold into annual tax model
    cf_path: list[float] = []
    nw_path: list[float] = []
    cumulative_rental_cashflow = 0.0
    cumulative_rental_cashflow_after_tax = 0.0
    cumulative_vacancy_bad_debt = 0.0
    cumulative_leasing_turnover = 0.0
    cumulative_management = 0.0
    cumulative_maintenance = 0.0
    cumulative_capex_current = 0.0

    annual_tax_models: list[AnnualTaxModel] = []
    rental_ops_annual: list[RentalOperationsModel] = []
    maint_capex_annual: list[MaintenanceCapexModel] = []

    suspended_balance = 0.0
    year_agg = {
        "gross_rent": 0.0, "vacancy_loss": 0.0, "bad_debt_loss": 0.0,
        "leasing_fee": 0.0, "turnover_cost": 0.0, "management_fee": 0.0,
        "collected_rent": 0.0, "mortgage_interest": 0.0, "routine_maint": 0.0,
        "capex_current": 0.0, "taxes_paid_ops": 0.0, "insurance_paid": 0.0,
        "hoa_paid": 0.0, "misc_paid": 0.0,
    }

    for m in range(horizon_months):
        ch_row = ch_schedule[m] if m < len(ch_schedule) else {"payment": 0.0, "interest": 0.0, "principal": 0.0, "balance": 0.0}
        vt = vac_turn[m]
        maint_m = maint[m]
        capex_m = ch_capex[m]
        mgmt_fee = vt["collected_rent"] * mgmt_pct
        carry = (
            ch_row["payment"]
            + tax_path[m]
            + ins_path[m]
            + hoa_path[m]
            + misc_path[m]
        )
        net_cf = (
            vt["collected_rent"]
            - vt["leasing_fee"]
            - vt["turnover_cost"]
            - mgmt_fee
            - maint_m
            - capex_m
            - carry
        )
        cumulative_rental_cashflow += net_cf
        cf_path.append(net_cf)
        cumulative_vacancy_bad_debt += vt["vacancy_loss"] + vt["bad_debt_loss"]
        cumulative_leasing_turnover += vt["leasing_fee"] + vt["turnover_cost"]
        cumulative_management += mgmt_fee
        cumulative_maintenance += maint_m
        cumulative_capex_current += capex_m

        # Aggregate into year bucket
        year_agg["gross_rent"] += vt["gross_rent"]
        year_agg["vacancy_loss"] += vt["vacancy_loss"]
        year_agg["bad_debt_loss"] += vt["bad_debt_loss"]
        year_agg["leasing_fee"] += vt["leasing_fee"]
        year_agg["turnover_cost"] += vt["turnover_cost"]
        year_agg["management_fee"] += mgmt_fee
        year_agg["collected_rent"] += vt["collected_rent"]
        year_agg["mortgage_interest"] += ch_row["interest"]
        year_agg["routine_maint"] += maint_m
        year_agg["capex_current"] += capex_m
        year_agg["taxes_paid_ops"] += tax_path[m]
        year_agg["insurance_paid"] += ins_path[m]
        year_agg["hoa_paid"] += hoa_path[m]
        year_agg["misc_paid"] += misc_path[m]

        # End of year (or end of horizon) — close annual tax model
        is_year_end = ((m + 1) % 12 == 0) or (m == horizon_months - 1)
        if is_year_end:
            year_num = (m // 12) + 1
            # Deductible capex portion: anything not flagged ignore_for_tax_model
            # For MVP, treat routine maintenance as fully deductible and capex as
            # ignored for tax (to be conservative; real capex capitalizes into basis).
            deductible_expenses = (
                year_agg["mortgage_interest"]
                + year_agg["taxes_paid_ops"]
                + year_agg["insurance_paid"]
                + year_agg["hoa_paid"]
                + year_agg["routine_maint"]
                + year_agg["management_fee"]
                + year_agg["leasing_fee"]
            )
            # First-year partial (mid-month conv) vs full-year amount after
            dep_this_year = first_year_dep if year_num == 1 else annual_depreciation
            taxable = (
                year_agg["collected_rent"]
                - deductible_expenses
                - dep_this_year
            )
            created_loss = max(0.0, -taxable)
            tax_paid_this_year = 0.0
            if taxable > 0:
                tax_paid_this_year = taxable * _combined_tax_rate(taxes)
                # If suspended losses exist, allow up to the positive taxable to offset
                offset = min(taxable, suspended_balance)
                if offset > 0:
                    tax_paid_this_year = (taxable - offset) * _combined_tax_rate(taxes)
                    suspended_balance -= offset
            else:
                suspended_balance += created_loss

            annual_tax_models.append(
                AnnualTaxModel(
                    year=year_num,
                    taxable_rental_income=taxable,
                    depreciation_taken=dep_this_year,
                    suspended_loss_created=created_loss,
                    suspended_loss_balance_end=suspended_balance,
                    current_tax_paid=tax_paid_this_year,
                    current_tax_saved=0.0,
                )
            )
            cumulative_rental_cashflow_after_tax += -tax_paid_this_year

            rental_ops_annual.append(
                RentalOperationsModel(
                    year=year_num,
                    gross_rent=year_agg["gross_rent"],
                    vacancy_loss=year_agg["vacancy_loss"],
                    bad_debt_loss=year_agg["bad_debt_loss"],
                    leasing_fee=year_agg["leasing_fee"],
                    turnover_cost=year_agg["turnover_cost"],
                    management_fee=year_agg["management_fee"],
                    collected_rent=year_agg["collected_rent"],
                )
            )
            maint_capex_annual.append(
                MaintenanceCapexModel(
                    year=year_num,
                    routine_maintenance=year_agg["routine_maint"],
                    explicit_capex_total=year_agg["capex_current"],
                    explicit_capex_events=[],
                    sale_prep_cost=0.0,
                    pre_sale_vacancy_cost=0.0,
                )
            )
            year_agg = {k: 0.0 for k in year_agg}

        # Net worth at this month: raw current-home equity (value - balance) + new-home
        # equity (filled after loop). Sell-cost discount is applied only at the true
        # ending point of a sell-style strategy, not every month of a hold.
        ch_equity_now = value_path[m + 1] - ch_row["balance"]
        nw_path.append(ch_equity_now)  # new-home equity added below

    cumulative_rental_cashflow_after_tax += cumulative_rental_cashflow

    # New home: base 20% down + refi path
    nh_schedule, nh_refi_cost = _new_home_schedule_with_refi(nh, refi)
    nh_price = _get(nh, "purchase_price", 0)

    nh_tax_path = monthly_owner_cost_path(
        _get(nh, "monthly_taxes", 0),
        _get(ocg, "new_home_tax_growth_annual_pct", 0.03),
        horizon_months,
    )
    nh_ins_path = monthly_owner_cost_path(
        _get(nh, "monthly_insurance", 0),
        _get(ocg, "new_home_insurance_growth_annual_pct", 0.05),
        horizon_months,
    )
    nh_hoa_path = monthly_owner_cost_path(
        _get(nh, "monthly_hoa", 0),
        _get(ocg, "new_home_hoa_growth_annual_pct", 0.03),
        horizon_months,
    )
    nh_maint_pct = _get(inputs.get("new_home_drag", {}), "new_home_maintenance_pct_of_home_value_annual", 0.01)
    nh_monthly_maint = (nh_price * nh_maint_pct) / 12.0
    nh_capex = capex_events_for_horizon(inputs.get("new_home_capex_items", []), horizon_months, "new_home")
    cumulative_nh_capex = sum(nh_capex)
    cumulative_nh_maint_drag = nh_monthly_maint * horizon_months

    # Fold new-home equity into nw_path
    for m in range(horizon_months):
        nh_row = nh_schedule[m] if m < len(nh_schedule) else {"balance": 0.0, "payment": 0.0}
        nh_equity = max(0.0, nh_price - nh_row["balance"])
        nw_path[m] += nh_equity
        cf_path[m] -= (nh_row["payment"] + nh_tax_path[m] + nh_ins_path[m] + nh_hoa_path[m] + nh_monthly_maint + nh_capex[m])

    # Ending totals
    ch_balance_end = ch_schedule[horizon_months - 1]["balance"] if horizon_months <= len(ch_schedule) else 0.0
    nh_balance_end = nh_schedule[horizon_months - 1]["balance"] if horizon_months <= len(nh_schedule) else 0.0

    sale_tax_model: SaleTaxModel | None = None
    net_worth_end: float

    if strategy_name == "rent_then_sell":
        # Sell at the horizon end (rent_then_sell_date is enforced by caller)
        future_value = value_path[horizon_months]
        future_sell_cost_pct = _get(ch, "current_home_sell_cost_pct_future", 0.07)
        sale_prep = _get(ch, "sale_prep_cost_flat", 3000)
        concession = _get(ch, "concession_pct_at_sale", 0.0)
        gross_proceeds = future_value * (1 - future_sell_cost_pct) * (1 - concession) - sale_prep
        net_proceeds_before_tax = max(0.0, gross_proceeds - ch_balance_end)

        # Depreciation taken over rental period
        total_dep = annual_depreciation * (horizon_months / 12.0)
        depreciation_recap = min(total_dep, max(0.0, gross_proceeds - basis))
        gross_gain = gross_proceeds - basis - depreciation_recap
        exclusion = _get(taxes, "section_121_mfj", 500_000)

        # §121 eligibility: sell within 3 years of move_out_month keeps 2-of-5 test alive
        move_out = _get(ch, "move_out_month")
        rent_start = _get(ch, "rent_start_month")
        # Approximate sell date = rent_start + horizon_months
        rs = _parse_month(rent_start) or _parse_month(move_out)
        window_open = True
        if rs:
            months_after_move_out = horizon_months + _month_diff(move_out, rent_start)
            # §121 generally requires 2-of-5 use; closing within 3 years after move-out is the safe window
            window_open = months_after_move_out <= 36

        excluded = min(max(gross_gain, 0.0), exclusion) if window_open else 0.0
        taxable_gain = max(0.0, gross_gain - excluded)
        cap_gain_tax = taxable_gain * _ltcg_tax_rate(taxes)
        recap_rate = min(_get(taxes, "depreciation_recovery_rate", 0.25), _get(taxes, "federal_ordinary_rate", 0.24)) + _get(taxes, "virginia_rate", 0.0575)
        recap_tax = depreciation_recap * recap_rate

        # Suspended-loss release
        susp_used = 0.0
        susp_benefit = 0.0
        if _get(taxes, "release_suspended_losses_on_taxable_disposition", True):
            susp_used = suspended_balance
            susp_benefit = susp_used * _combined_tax_rate(taxes)
        total_sale_tax = max(0.0, cap_gain_tax + recap_tax - susp_benefit)
        susp_remainder = max(0.0, suspended_balance - susp_used)

        sale_tax_model = SaleTaxModel(
            gross_gain=gross_gain + depreciation_recap,
            section_121_excluded_gain=excluded,
            depreciation_recap_bucket=depreciation_recap,
            taxable_cap_gain_bucket=taxable_gain,
            estimated_sale_tax=total_sale_tax,
            suspended_loss_used_at_sale=susp_used,
            suspended_loss_remainder=susp_remainder,
            suspended_loss_tax_benefit=susp_benefit,
        )
        nh_equity_end = max(0.0, nh_price - nh_balance_end)
        net_worth_end = (
            (net_proceeds_before_tax - total_sale_tax)
            + nh_equity_end
            + cumulative_rental_cashflow_after_tax
            - nh_refi_cost
            - cumulative_nh_capex
            - cumulative_nh_maint_drag
        )
    else:
        # keep_5y / keep_10y: don't sell, carry current-home equity forward
        future_value = value_path[horizon_months]
        future_sell_cost_pct = _get(ch, "current_home_sell_cost_pct_future", 0.07)
        ch_equity_end = future_value * (1 - future_sell_cost_pct) - ch_balance_end
        nh_equity_end = max(0.0, nh_price - nh_balance_end)
        net_worth_end = (
            ch_equity_end
            + nh_equity_end
            + cumulative_rental_cashflow_after_tax
            - nh_refi_cost
            - cumulative_nh_capex
            - cumulative_nh_maint_drag
        )

    monthly_stress = _new_home_monthly_carry(
        nh, nh_schedule[0]["payment"] if nh_schedule else 0.0
    ) + nh_monthly_maint

    warnings: list[str] = []
    if cumulative_rental_cashflow < 0:
        warnings.append("negative_rental_cashflow")
    if suspended_balance > 0 and not _get(taxes, "release_suspended_losses_on_taxable_disposition", True):
        warnings.append("suspended_losses_not_released")
    # Capex concentration in first 24 months
    early_capex = sum(ch_capex[:24])
    if early_capex > 20_000:
        warnings.append("high_early_capex")

    return StrategyOutput(
        name=strategy_name,
        net_worth_end=net_worth_end,
        monthly_stress=monthly_stress,
        monthly_stress_delta_vs_sell=0.0,  # filled in aggregator
        annual_tax_model=annual_tax_models,
        rental_ops_model=rental_ops_annual,
        maintenance_capex_model=maint_capex_annual,
        reinvestment_model=None,
        sale_tax_model=sale_tax_model,
        driver_bridge_vs_sell=None,  # filled in aggregator
        tax_disclaimer_flags=["section_121_assumed", "passive_loss_limited"],
        warnings=warnings,
        net_worth_path=nw_path,
        monthly_cashflow_path=cf_path,
    )


# ─────────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────────


def compute_rent_then_sell(inputs: dict) -> StrategyOutput:
    """Compute the rent-then-sell strategy. Thin wrapper around
    compute_keep_rental that auto-derives the horizon from
    ``rent_start_month`` → ``rent_then_sell_date``.
    """
    horizon = _compute_rent_then_sell_horizon_months(inputs)
    return compute_keep_rental(inputs, horizon, "rent_then_sell")


def _compute_rent_then_sell_horizon_months(inputs: dict) -> int:
    """Months from rent_start_month to rent_then_sell_date.

    Clamped to `[1, MAX_HORIZON_MONTHS]` so a malformed or adversarial date
    string cannot allocate enormous amortization / growth lists.
    """
    ch = inputs.get("current_home", {})
    modeling = inputs.get("modeling", {})
    rent_start = _get(ch, "rent_start_month")
    sell_date = _get(modeling, "rent_then_sell_date", "2029-05")
    months = _month_diff(rent_start, sell_date)
    if months <= 0:
        return 1
    return min(MAX_HORIZON_MONTHS, months)


def _build_driver_bridge(
    keep: StrategyOutput, sell: StrategyOutput, inputs: dict, horizon_months: int
) -> StrategyDriverBridge:
    """Compute an explicit bucket breakdown of keep.net_worth_end - sell.net_worth_end."""
    ch = inputs.get("current_home", {})
    delta = keep.net_worth_end - sell.net_worth_end

    # Rental cashflow contribution (already net of tax for keep)
    rental_cf = 0.0
    if keep.annual_tax_model:
        for yr in keep.annual_tax_model:
            rental_cf -= yr.current_tax_paid
    if keep.rental_ops_model:
        for yr in keep.rental_ops_model:
            rental_cf += yr.collected_rent - yr.leasing_fee - yr.turnover_cost - yr.management_fee

    vacancy_drag = 0.0
    leasing_turnover = 0.0
    mgmt_drag = 0.0
    if keep.rental_ops_model:
        for yr in keep.rental_ops_model:
            vacancy_drag -= yr.vacancy_loss + yr.bad_debt_loss
            leasing_turnover -= yr.leasing_fee + yr.turnover_cost
            mgmt_drag -= yr.management_fee

    maint_drag = 0.0
    capex_ch = 0.0
    if keep.maintenance_capex_model:
        for yr in keep.maintenance_capex_model:
            maint_drag -= yr.routine_maintenance
            capex_ch -= yr.explicit_capex_total

    # Appreciation: prorate the horizon-matched total change over the actual
    # number of months this strategy ran. For RTS (e.g. 36 months), using the
    # raw 5Y total would overstate appreciation by ~60/36.
    value_today = _safe_float(_get(ch, "value_today", 0))
    if horizon_months >= 120:
        total_value_change = _safe_float(_get(ch, "total_value_change_10y", 0.0))
        total_value_months = 120
    else:
        total_value_change = _safe_float(_get(ch, "total_value_change_5y", 0.0))
        total_value_months = 60
    prorated_change = total_value_change * (horizon_months / total_value_months) if total_value_months else 0
    appreciation = value_today * prorated_change * (
        1 - _safe_float(_get(ch, "current_home_sell_cost_pct_future", 0.07))
    )

    loan_balance = _safe_float(_get(ch, "loan_balance", 0))
    rate = _safe_float(_get(ch, "mortgage_rate", 0.025))
    # Use the same term logic the main engine uses so the bridge matches reality
    remaining_term = max(horizon_months, 60)
    sched = mortgage_schedule(loan_balance, rate, remaining_term)
    paydown = 0.0
    if sched and horizon_months > 0:
        balance_end = sched[min(horizon_months, len(sched)) - 1]["balance"]
        paydown = loan_balance - balance_end

    sale_tax_diff = 0.0
    if keep.sale_tax_model:
        sale_tax_diff = -keep.sale_tax_model.estimated_sale_tax
    if sell.sale_tax_model:
        sale_tax_diff += sell.sale_tax_model.estimated_sale_tax

    reinvestment_benefit_sell = 0.0
    if sell.reinvestment_model:
        reinvestment_benefit_sell = -sell.reinvestment_model.ending_investment_value

    computed_sum = (
        rental_cf
        + vacancy_drag
        + leasing_turnover
        + mgmt_drag
        + maint_drag
        + capex_ch
        + appreciation
        + paydown
        + sale_tax_diff
        + reinvestment_benefit_sell
    )
    residual = delta - computed_sum

    return StrategyDriverBridge(
        trapped_equity_redeployment_benefit=0.0,
        extra_new_home_interest_cost=0.0,
        rental_cashflow_after_tax=rental_cf,
        vacancy_and_bad_debt_drag=vacancy_drag,
        leasing_and_turnover_drag=leasing_turnover,
        property_management_drag=mgmt_drag,
        routine_maintenance_drag=maint_drag,
        capex_drag_current_home=capex_ch,
        capex_drag_new_home=0.0,
        current_home_appreciation_effect=appreciation,
        current_home_principal_paydown=paydown,
        ownership_cost_growth_effect=0.0,
        sale_tax_difference=sale_tax_diff,
        future_sale_friction_difference=0.0,
        reinvestment_benefit_sell_case=reinvestment_benefit_sell,
        refi_effect=0.0,
        reserve_drag=0.0,
        residual_other=residual,
    )


# Module-local LRU for breakeven bisection results. Breakevens are expensive
# (25 compute_full_analysis calls per bisection × 2 per /calculate) so we
# memoize by a hash of the inputs subset that matters. Each /calculate during
# debounced typing that touches an UNRELATED field becomes a cache hit.
_BREAKEVEN_CACHE: dict[str, float | None] = {}
_BREAKEVEN_CACHE_MAX = 128


def _breakeven_cache_key(inputs: dict, horizon_key: str, strategy_name: str) -> str:
    """Hash the assumption subset that breakeven math depends on.

    Intentionally EXCLUDES `horizon_key` from the inputs snapshot because
    the bisection sweeps that field; including it would make every call a
    miss. We DO include the horizon_key name + strategy_name so different
    bisection targets get different cache slots.
    """
    subset_keys = (
        "current_home", "new_home", "refinance", "taxes",
        "ownership_cost_growth", "reinvestment", "new_home_drag",
        "current_home_capex_items", "new_home_capex_items", "modeling",
    )
    subset = {k: inputs.get(k) for k in subset_keys}
    # Strip the axis field since bisection sweeps it
    if isinstance(subset.get("current_home"), dict):
        ch = dict(subset["current_home"])
        ch.pop(horizon_key, None)
        subset["current_home"] = ch
    payload = json.dumps(
        {
            "v": CALC_VERSION,
            "a": subset,
            "axis": horizon_key,
            "strat": strategy_name,
        },
        sort_keys=True,
        default=repr,
    )
    return hashlib.sha1(payload.encode()).hexdigest()


def _breakeven_appreciation(
    inputs: dict,
    horizon_key: str,  # "total_value_change_5y" or "total_value_change_10y"
    strategy_name: str,  # "keep_5y" or "keep_10y"
    horizon_months: int,
) -> float | None:
    """Bisect for the total value-change that makes keep == sell at horizon.

    Returns None if no crossover exists in the ±30% bracket.
    """
    # Memo cache hit?
    cache_key = _breakeven_cache_key(inputs, horizon_key, strategy_name)
    if cache_key in _BREAKEVEN_CACHE:
        return _BREAKEVEN_CACHE[cache_key]

    sell_key = "sell_now_10y" if horizon_months >= 120 else "sell_now"
    # Only request the two strategies this comparison actually reads. Every
    # extra strategy multiplies the cost by ~1x; with 24 bisection iterations
    # × 2 horizons per /calculate, trimming from 4 to 2 strategies saves ~35%
    # of the breakeven latency.
    needed = frozenset((sell_key, strategy_name))

    def delta_at(pct: float) -> float | None:
        clone = _clone_inputs_for_sensitivity(inputs)
        clone.setdefault("current_home", {})[horizon_key] = pct
        try:
            result = compute_full_analysis(
                clone,
                strategies_needed=needed,
                build_driver_bridges=False,
            )
        except Exception:
            return None
        keep = result["strategies"].get(strategy_name, {}).get("net_worth_end")
        sell_nw = result["strategies"].get(sell_key, {}).get("net_worth_end")
        if keep is None or sell_nw is None:
            return None
        return keep - sell_nw

    def _store(value: float | None) -> float | None:
        if len(_BREAKEVEN_CACHE) >= _BREAKEVEN_CACHE_MAX:
            _BREAKEVEN_CACHE.pop(next(iter(_BREAKEVEN_CACHE)))
        _BREAKEVEN_CACHE[cache_key] = value
        return value

    lo, hi = -0.30, 0.30
    d_lo, d_hi = delta_at(lo), delta_at(hi)
    if d_lo is None or d_hi is None:
        return _store(None)
    if d_lo == 0:
        return _store(lo)
    if d_hi == 0:
        return _store(hi)
    if (d_lo > 0 and d_hi > 0) or (d_lo < 0 and d_hi < 0):
        return _store(None)
    for _ in range(24):
        mid = (lo + hi) / 2
        d_mid = delta_at(mid)
        if d_mid is None:
            return _store(None)
        if abs(d_mid) < 100.0:
            return _store(mid)
        if (d_mid > 0) == (d_lo > 0):
            lo, d_lo = mid, d_mid
        else:
            hi, d_hi = mid, d_mid
    return _store((lo + hi) / 2)


def _compute_top_line(
    sell: StrategyOutput | None,
    keep_5y: StrategyOutput | None,
    keep_10y: StrategyOutput | None,
    rts: StrategyOutput | None,
    inputs: dict,
    compute_breakevens: bool = True,
) -> dict:
    ch = inputs.get("current_home", {})
    nh = inputs.get("new_home", {})
    value_today = _safe_float(_get(ch, "value_today", 0))
    sell_cost = _safe_float(_get(ch, "sell_cost_pct_now", 0.07))
    loan_balance = _safe_float(_get(ch, "loan_balance", 0))
    trapped_equity = value_today * (1 - sell_cost) - loan_balance

    move_out = _get(ch, "move_out_month", "")
    window_status = "open"
    mo = _parse_month(move_out) if move_out else None
    if mo:
        today = date.today()
        months_after = (today.year - mo.year) * 12 + (today.month - mo.month)
        if months_after > 36:
            window_status = "closed"
        elif months_after > 24:
            window_status = "closing"

    # Monthly stress delta (keep vs sell, month 1)
    monthly_stress_delta = 0.0
    if keep_5y is not None and sell is not None:
        monthly_stress_delta = keep_5y.monthly_stress - sell.monthly_stress

    # Extra new-home loan: keep-case loan − sell-case loan (both at month 0)
    nh_price = _safe_float(_get(nh, "purchase_price", 0))
    base_down_pct = _safe_float(_get(nh, "base_down_pct", 0.20))
    keep_loan = nh_price * (1 - base_down_pct)

    # Sell-case loan: factor in net-after-tax proceeds applied to the down
    # payment. This mirrors what compute_sell_now does for sizing.
    taxes = inputs.get("taxes", {})
    gross_proceeds = value_today * (1 - sell_cost) - _safe_float(
        _get(ch, "sale_prep_cost_flat", 3000)
    )
    basis = _safe_float(_get(ch, "basis", value_today))
    gain = gross_proceeds - basis
    exclusion = _safe_float(_get(taxes, "section_121_mfj", 500000))
    taxable_gain = max(0.0, gain - min(max(gain, 0.0), exclusion))
    sale_tax = taxable_gain * (
        _safe_float(_get(taxes, "federal_ltcg_rate", 0.15))
        + _safe_float(_get(taxes, "virginia_rate", 0.0575))
        + (_safe_float(_get(taxes, "niit_rate", 0.038)) if _get(taxes, "niit_enabled", False) else 0)
    )
    net_after_tax_proceeds = max(0.0, gross_proceeds - loan_balance - sale_tax)
    sell_loan = max(0.0, nh_price - (nh_price * base_down_pct + net_after_tax_proceeds))
    extra_new_home_loan = keep_loan - sell_loan

    # Net interest drag at month 1 = total interest paid in the keep case
    # minus total interest paid in the sell case.
    # Keep case interest = new-home interest at 20%-down loan + old-home
    # interest (the low-rate mortgage continues). Sell case interest = new-home
    # interest at ~53%-down loan (old mortgage is paid off).
    # A POSITIVE drag means the keep case burns more interest per month.
    new_rate = max(0.0, _safe_float(_get(nh, "initial_rate", 0.0646)))
    old_rate = max(0.0, _safe_float(_get(ch, "mortgage_rate", 0.025)))
    keep_new_home_interest_month1 = max(0.0, keep_loan) * (new_rate / 12)
    sell_new_home_interest_month1 = max(0.0, sell_loan) * (new_rate / 12)
    current_home_interest_month1 = max(0.0, loan_balance) * (old_rate / 12)
    net_interest_drag_monthly = (
        keep_new_home_interest_month1
        + current_home_interest_month1
        - sell_new_home_interest_month1
    )

    # Required appreciation to break even — bisected against the current
    # inputs. Only computed during full runs (sensitivity skips via flag).
    breakeven_5y = None
    breakeven_10y = None
    if compute_breakevens and keep_5y is not None and sell is not None:
        try:
            breakeven_5y = _breakeven_appreciation(
                inputs, "total_value_change_5y", "keep_5y", 60
            )
        except Exception:
            breakeven_5y = None
    if compute_breakevens and keep_10y is not None:
        try:
            breakeven_10y = _breakeven_appreciation(
                inputs, "total_value_change_10y", "keep_10y", 120
            )
        except Exception:
            breakeven_10y = None

    return {
        "trapped_equity": trapped_equity,
        "extra_new_home_loan": extra_new_home_loan,
        "net_interest_drag_monthly": net_interest_drag_monthly,
        "monthly_stress_delta": monthly_stress_delta,
        "monthly_stress_sell": sell.monthly_stress if sell else None,
        "monthly_stress_keep": keep_5y.monthly_stress if keep_5y else None,
        "required_appreciation_to_breakeven_5y": breakeven_5y,
        "required_appreciation_to_breakeven_10y": breakeven_10y,
        "section_121_window_status": window_status,
        "sell_now_net_worth_5y": None,  # populated by compute_full_analysis
        "keep_5y_net_worth": keep_5y.net_worth_end if keep_5y else None,
        "keep_10y_net_worth": keep_10y.net_worth_end if keep_10y else None,
        "rent_then_sell_net_worth": rts.net_worth_end if rts else None,
    }


def compute_full_analysis(
    inputs: dict,
    strategies_needed: frozenset[str] | None = None,
    build_driver_bridges: bool = True,
) -> dict:
    """Run the requested strategies from one assumption set.

    Args:
        inputs: the assumption dict
        strategies_needed: optional set of strategy names to compute. If None,
            computes all five (sell_now, sell_now_10y, keep_5y, keep_10y,
            rent_then_sell). The sensitivity grid passes a subset to avoid
            paying for strategies it never reads.
        build_driver_bridges: if False, skip the driver-bridge computation.
            Sensitivity grids don't need per-cell bridges.

    Returns a plain dict (no Pydantic) so the API layer can serialize it.
    """
    all_names = frozenset(("sell_now", "sell_now_10y", "keep_5y", "keep_10y", "rent_then_sell"))
    needed = all_names if strategies_needed is None else (strategies_needed & all_names)
    if not needed:
        needed = all_names

    horizon_5y = 60
    horizon_10y = 120
    rts_months = _compute_rent_then_sell_horizon_months(inputs)

    sell_5y = compute_sell_now(inputs, horizon_5y) if "sell_now" in needed or "keep_5y" in needed or "rent_then_sell" in needed else None
    sell_10y = compute_sell_now(inputs, horizon_10y) if "sell_now_10y" in needed or "keep_10y" in needed else None
    keep_5y = compute_keep_rental(inputs, horizon_5y, "keep_5y") if "keep_5y" in needed else None
    keep_10y = compute_keep_rental(inputs, horizon_10y, "keep_10y") if "keep_10y" in needed else None
    rts = compute_keep_rental(inputs, rts_months, "rent_then_sell") if "rent_then_sell" in needed else None

    # Sell-case reinvestment: monthly savings relative to keep case
    reinv = inputs.get("reinvestment", {})
    reinvest_rate = _get(reinv, "monthly_savings_reinvestment_return_annual_pct", 0.04)
    if _get(reinv, "invest_monthly_sell_savings", True) and sell_5y is not None and keep_5y is not None:
        monthly_savings = max(0.0, keep_5y.monthly_stress - sell_5y.monthly_stress)
        if monthly_savings > 0:
            contributions = [monthly_savings] * horizon_5y
            ending_5y = reinvestment_path(contributions, reinvest_rate)
            sell_5y.reinvestment_model = ReinvestmentModel(
                monthly_savings_invested=monthly_savings * horizon_5y,
                surplus_cash_invested=0.0,
                ending_investment_value=ending_5y,
            )
            sell_5y.net_worth_end += ending_5y
            if sell_10y is not None:
                contributions_10y = [monthly_savings] * horizon_10y
                ending_10y = reinvestment_path(contributions_10y, reinvest_rate)
                sell_10y.reinvestment_model = ReinvestmentModel(
                    monthly_savings_invested=monthly_savings * horizon_10y,
                    surplus_cash_invested=0.0,
                    ending_investment_value=ending_10y,
                )
                sell_10y.net_worth_end += ending_10y

    # Monthly stress deltas
    if sell_5y is not None:
        for strat in (keep_5y, keep_10y, rts):
            if strat is not None:
                strat.monthly_stress_delta_vs_sell = strat.monthly_stress - sell_5y.monthly_stress

    # Driver bridges — skipped entirely in sensitivity mode
    if build_driver_bridges:
        if keep_5y is not None and sell_5y is not None:
            keep_5y.driver_bridge_vs_sell = _build_driver_bridge(keep_5y, sell_5y, inputs, horizon_5y)
        if keep_10y is not None and sell_10y is not None:
            keep_10y.driver_bridge_vs_sell = _build_driver_bridge(keep_10y, sell_10y, inputs, horizon_10y)
        if rts is not None and sell_5y is not None:
            rts.driver_bridge_vs_sell = _build_driver_bridge(rts, sell_5y, inputs, rts_months)

    # Top-line metrics (only when the full flight is computed)
    strategies_out: dict[str, Any] = {}
    if sell_5y is not None:
        strategies_out["sell_now"] = asdict(sell_5y)
    if sell_10y is not None:
        strategies_out["sell_now_10y"] = asdict(sell_10y)
    if keep_5y is not None:
        strategies_out["keep_5y"] = asdict(keep_5y)
    if keep_10y is not None:
        strategies_out["keep_10y"] = asdict(keep_10y)
    if rts is not None:
        strategies_out["rent_then_sell"] = asdict(rts)

    top_line = _compute_top_line(
        sell_5y, keep_5y, keep_10y, rts, inputs,
        # Breakeven bisection itself calls compute_full_analysis, so only run
        # it when the caller wants full output (not inside sensitivity cells).
        compute_breakevens=build_driver_bridges,
    )
    top_line["sell_now_net_worth_5y"] = sell_5y.net_worth_end if sell_5y else None
    top_line["sell_now_net_worth_10y"] = sell_10y.net_worth_end if sell_10y else None

    # Lean — only meaningful if both sides of the 5Y comparison were computed
    if keep_5y is not None and sell_5y is not None:
        delta_5y = keep_5y.net_worth_end - sell_5y.net_worth_end
        if abs(delta_5y) < LEAN_THRESHOLD_DOLLARS:
            lean = "too_close"
        elif delta_5y > 0:
            lean = "leans_keep"
        else:
            lean = "leans_sell"
    else:
        lean = "n/a"

    return {
        "strategies": strategies_out,
        "top_line": top_line,
        "lean": lean,
        "calc_version": CALC_VERSION,
        "input_schema_version": INPUT_SCHEMA_VERSION,
    }


# ─────────────────────────────────────────────────────────────────────
# Sensitivity grid
# ─────────────────────────────────────────────────────────────────────


_SENSITIVITY_STEPS = [-0.10, -0.08, -0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06, 0.08, 0.10]


def _clone_inputs_for_sensitivity(inputs: dict) -> dict:
    """Shallow-copy top-level + targeted deep-copy of the mutable subset.

    The sensitivity loop only mutates `current_home`, `refinance`,
    `reinvestment`, and `current_home_capex_items`. Copy those subtrees;
    share everything else by reference. This is ~10x faster than a full
    deepcopy and ~2-3x less memory per cell.
    """
    out = dict(inputs)
    for k in ("current_home", "refinance", "reinvestment"):
        if k in out and isinstance(out[k], dict):
            out[k] = dict(out[k])
    # capex items: shallow list copy is enough since we only append
    if "current_home_capex_items" in out and isinstance(out["current_home_capex_items"], list):
        out["current_home_capex_items"] = list(out["current_home_capex_items"])
    return out


def _strategy_net_worth(result: dict, name: str) -> float | None:
    """Return the strategy's net worth at horizon, or None if the strategy
    was not computed / not present. Callers must distinguish None (missing)
    from 0.0 (legitimate zero) — conflating them silently breaks bisection.
    """
    strat = result.get("strategies", {}).get(name)
    if not strat:
        return None
    nw = strat.get("net_worth_end")
    if nw is None:
        return None
    return nw


def compute_sensitivity_grid(
    inputs: dict,
    preset: str = "value_x_rent",
    comparator: str = "sell_vs_keep_5y",
    horizon: str = "5y",
) -> dict:
    """Run a preset-driven sensitivity grid.

    preset:
      value_x_rent, value_x_capex, value_x_refi, rent_x_vacancy, rent_x_reinvest
    comparator:
      sell_vs_keep_5y, sell_vs_keep_10y, sell_vs_rent_then_sell
    horizon:
      5y, 10y
    """
    x_label, y_label = "", ""
    x_values: list = []
    y_values: list = []
    if preset == "value_x_rent":
        x_label = "Value change"
        y_label = "Rent change"
        x_values = _SENSITIVITY_STEPS
        y_values = _SENSITIVITY_STEPS
    elif preset == "value_x_capex":
        x_label = "Value change"
        y_label = "Capex shock ($)"
        x_values = _SENSITIVITY_STEPS
        y_values = [0, 5000, 10000, 15000, 20000, 25000, 30000]
    elif preset == "value_x_refi":
        x_label = "Value change"
        y_label = "Refi path"
        x_values = _SENSITIVITY_STEPS
        y_values = ["none", "year3", "year5", "year7"]
    elif preset == "rent_x_vacancy":
        x_label = "Rent change"
        y_label = "Vacancy months/yr"
        x_values = _SENSITIVITY_STEPS
        y_values = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    elif preset == "rent_x_reinvest":
        x_label = "Rent change"
        y_label = "Reinvest return"
        x_values = _SENSITIVITY_STEPS
        y_values = [0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
    else:
        raise ValueError(f"Unknown preset: {preset}")

    # Parse comparator
    if comparator == "sell_vs_keep_5y":
        a_name, b_name = "sell_now", "keep_5y"
    elif comparator == "sell_vs_keep_10y":
        a_name, b_name = "sell_now_10y", "keep_10y"
    elif comparator == "sell_vs_rent_then_sell":
        a_name, b_name = "sell_now", "rent_then_sell"
    else:
        raise ValueError(f"Unknown comparator: {comparator}")

    # Only compute the two strategies this comparator actually reads. Cuts
    # work from 5 strategies/cell to ~2-3 and skips driver-bridge work.
    needed = frozenset((a_name, b_name))

    cells = []
    for yi, y in enumerate(y_values):
        row = []
        for xi, x in enumerate(x_values):
            clone = _clone_inputs_for_sensitivity(inputs)
            _apply_preset_cell(clone, preset, x, y, horizon)
            result = compute_full_analysis(
                clone,
                strategies_needed=needed,
                build_driver_bridges=False,
            )
            a_nw = _strategy_net_worth(result, a_name)
            b_nw = _strategy_net_worth(result, b_name)
            if a_nw is None or b_nw is None:
                # Missing strategy: surface as a 0 delta with "n/a" winner
                # so the grid cell renders an obvious "something is off" state
                # instead of misreporting a confident winner.
                row.append({"x": x, "y": y, "delta": 0.0, "winner": "n/a"})
                continue
            delta = b_nw - a_nw
            winner = "keep" if delta > 0 else "sell"
            row.append({"x": x, "y": y, "delta": delta, "winner": winner})
        cells.append(row)

    # Breakeven metrics — bisected against the current baseline. Only
    # meaningful for the axes this preset exercises.
    breakevens = _compute_grid_breakevens(inputs, preset, comparator, horizon, a_name, b_name)

    return {
        "preset": preset,
        "comparator": comparator,
        "horizon": horizon,
        "x_label": x_label,
        "y_label": y_label,
        "x_values": x_values,
        "y_values": y_values,
        "cells": cells,
        **breakevens,
    }


def _bisect_breakeven(
    inputs: dict,
    a_name: str,
    b_name: str,
    mutate: Any,  # Callable[[dict, float], None]
    lo: float,
    hi: float,
    tolerance: float = 200.0,
    max_iter: int = 24,
) -> float | None:
    """Bisect to find the mutation value at which b_nw - a_nw == 0."""
    def delta_at(v: float) -> float | None:
        clone = _clone_inputs_for_sensitivity(inputs)
        mutate(clone, v)
        try:
            result = compute_full_analysis(
                clone,
                strategies_needed=frozenset((a_name, b_name)),
                build_driver_bridges=False,
            )
        except Exception:
            return None
        a_nw = _strategy_net_worth(result, a_name)
        b_nw = _strategy_net_worth(result, b_name)
        if a_nw is None or b_nw is None:
            return None
        return b_nw - a_nw

    d_lo, d_hi = delta_at(lo), delta_at(hi)
    if d_lo is None or d_hi is None:
        return None
    # Zero at an endpoint — the crossover is exactly there
    if d_lo == 0:
        return lo
    if d_hi == 0:
        return hi
    if (d_lo > 0 and d_hi > 0) or (d_lo < 0 and d_hi < 0):
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        d_mid = delta_at(mid)
        if d_mid is None:
            return None
        if abs(d_mid) < tolerance:
            return mid
        if (d_mid > 0) == (d_lo > 0):
            lo, d_lo = mid, d_mid
        else:
            hi, d_hi = mid, d_mid
    return (lo + hi) / 2


def _compute_grid_breakevens(
    inputs: dict,
    preset: str,
    comparator: str,
    horizon: str,
    a_name: str,
    b_name: str,
) -> dict:
    """Return crossover-line breakevens for the preset's two axes.

    Always attempts rent + value breakevens. Capex breakeven only when the
    preset exercises a capex axis.
    """
    if horizon not in ("5y", "10y"):
        raise ValueError(f"Unknown horizon for grid breakevens: {horizon!r}")
    is_10y = horizon == "10y"

    def set_value(c: dict, v: float) -> None:
        ch = c.setdefault("current_home", {})
        ch["total_value_change_10y" if is_10y else "total_value_change_5y"] = v

    def set_rent(c: dict, v: float) -> None:
        ch = c.setdefault("current_home", {})
        ch["total_rent_change_10y" if is_10y else "total_rent_change_5y"] = v

    def set_capex(c: dict, v: float) -> None:
        items = c.setdefault("current_home_capex_items", [])
        items.append(
            {"name": "Breakeven probe", "amount": v, "month_offset": 12,
             "applies_to": "current_home"}
        )

    be_value = _bisect_breakeven(inputs, a_name, b_name, set_value, -0.30, 0.30)
    be_rent = _bisect_breakeven(inputs, a_name, b_name, set_rent, -0.30, 0.30)
    be_capex = None
    if preset == "value_x_capex":
        be_capex = _bisect_breakeven(
            inputs, a_name, b_name, set_capex, 0.0, 200_000.0, tolerance=500.0
        )

    return {
        "breakeven_value_change_pct": be_value,
        "breakeven_rent_change_pct": be_rent,
        "breakeven_capex_shock_dollars": be_capex,
    }


def _apply_preset_cell(clone: dict, preset: str, x: Any, y: Any, horizon: str) -> None:
    """Mutate `clone` inputs for a single sensitivity cell."""
    ch = clone.setdefault("current_home", {})
    if preset == "value_x_rent":
        if horizon == "10y":
            ch["total_value_change_10y"] = x
            ch["total_rent_change_10y"] = y
        else:
            ch["total_value_change_5y"] = x
            ch["total_rent_change_5y"] = y
    elif preset == "value_x_capex":
        if horizon == "10y":
            ch["total_value_change_10y"] = x
        else:
            ch["total_value_change_5y"] = x
        # Add a single capex event at month 12
        items = clone.setdefault("current_home_capex_items", [])
        items.append({"name": "Sensitivity Capex", "amount": y, "month_offset": 12, "applies_to": "current_home"})
    elif preset == "value_x_refi":
        if horizon == "10y":
            ch["total_value_change_10y"] = x
        else:
            ch["total_value_change_5y"] = x
        refi = clone.setdefault("refinance", {})
        refi["enabled"] = y != "none"
        refi["selected_path"] = y
    elif preset == "rent_x_vacancy":
        if horizon == "10y":
            ch["total_rent_change_10y"] = x
        else:
            ch["total_rent_change_5y"] = x
        ch["vacancy_months_per_year_base"] = y
    elif preset == "rent_x_reinvest":
        if horizon == "10y":
            ch["total_rent_change_10y"] = x
        else:
            ch["total_rent_change_5y"] = x
        reinv = clone.setdefault("reinvestment", {})
        reinv["invest_monthly_sell_savings"] = True
        reinv["monthly_savings_reinvestment_return_annual_pct"] = y


# ─────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────


__all__ = [
    "CALC_VERSION",
    "INPUT_SCHEMA_VERSION",
    "monthly_payment",
    "mortgage_schedule",
    "refi_schedule",
    "linear_growth_path",
    "monthly_owner_cost_path",
    "reinvestment_path",
    "vacancy_and_turnover_path",
    "capex_events_for_horizon",
    "maintenance_path",
    "compute_depreciation",
    "compute_sell_now",
    "compute_keep_rental",
    "compute_rent_then_sell",
    "compute_full_analysis",
    "compute_sensitivity_grid",
]


# ─────────────────────────────────────────────────────────────────────
# CLI — fixture generation
# ─────────────────────────────────────────────────────────────────────


def _starter_base_inputs() -> dict:
    """The canonical base-case inputs used by tests and fixtures."""
    return {
        "current_home": {
            "value_today": 790000, "basis": 478000, "loan_balance": 295413,
            "mortgage_rate": 0.025,
            "monthly_principal_interest": 1245,
            "monthly_taxes": 620, "monthly_insurance": 120,
            "monthly_hoa": 0, "monthly_misc_owner_paid": 80,
            "insurance_conversion_bump_pct": 0.15,
            "initial_lease_up_vacancy_months": 1.0,
            "sell_cost_pct_now": 0.07,
            "current_home_sell_cost_pct_future": 0.07,
            "monthly_rent_base": 3500,
            "land_pct": 0.2974, "building_pct": 0.7026,
            "move_out_month": "2026-05", "rent_start_month": "2026-06",
            "reserve_months_per_year": 2, "self_manage": True,
            "property_management_pct": 0.0,
            "vacancy_months_per_year_base": 0.5,
            "bad_debt_pct_of_gross_rent": 0.005,
            "leasing_fee_pct_of_annual_rent": 0.05,
            "turnover_cost_per_event": 2500,
            "turnover_frequency_months": 24,
            "routine_maintenance_pct_of_rent": 0.05,
            "maintenance_inflation_annual_pct": 0.03,
            "sale_prep_cost_flat": 3000,
            "pre_sale_vacancy_months": 0.5,
            "concession_pct_at_sale": 0.0,
            "total_value_change_5y": 0.10, "total_value_change_10y": 0.20,
            "total_rent_change_5y": 0.0, "total_rent_change_10y": 0.0,
        },
        "new_home": {
            "purchase_price": 1315000, "base_down_pct": 0.20,
            "initial_rate": 0.0646, "loan_term_years": 30,
            "monthly_hoa": 0, "monthly_taxes": 800, "monthly_insurance": 150,
        },
        "refinance": {
            "enabled": False, "selected_path": "none", "cost_pct": 0.015,
            "year3_rate": 0.055, "year5_rate": 0.0475, "year7_rate": 0.0425,
        },
        "taxes": {
            "federal_ordinary_rate": 0.24, "federal_ltcg_rate": 0.15,
            "virginia_rate": 0.0575, "niit_enabled": False, "niit_rate": 0.038,
            "section_121_mfj": 500000, "depreciation_recovery_rate": 0.25,
            "release_suspended_losses_on_taxable_disposition": True,
        },
        "ownership_cost_growth": {
            "current_home_tax_growth_annual_pct": 0.03,
            "current_home_insurance_growth_annual_pct": 0.05,
            "current_home_hoa_growth_annual_pct": 0.03,
            "current_home_misc_growth_annual_pct": 0.03,
            "new_home_tax_growth_annual_pct": 0.03,
            "new_home_insurance_growth_annual_pct": 0.05,
            "new_home_hoa_growth_annual_pct": 0.03,
        },
        "reinvestment": {
            "invest_monthly_sell_savings": True,
            "monthly_savings_reinvestment_return_annual_pct": 0.04,
            "invest_initial_sale_surplus_cash": False,
        },
        "new_home_drag": {
            "new_home_maintenance_pct_of_home_value_annual": 0.01,
        },
        "modeling": {"rent_then_sell_date": "2029-05"},
    }


def _fixture_inputs(name: str) -> dict:
    """Return the inputs for a named fixture scenario."""
    inputs = _starter_base_inputs()
    if name == "base_case":
        return inputs
    if name == "recession_case":
        inputs["current_home"]["total_value_change_5y"] = -0.10
        inputs["current_home"]["total_value_change_10y"] = -0.10
        inputs["current_home"]["total_rent_change_5y"] = -0.10
        inputs["current_home"]["total_rent_change_10y"] = -0.10
        return inputs
    if name == "refi_year5_case":
        inputs["refinance"]["enabled"] = True
        inputs["refinance"]["selected_path"] = "year5"
        inputs["refinance"]["year5_rate"] = 0.0475
        return inputs
    if name == "capex_shock_case":
        inputs["current_home_capex_items"] = [
            {"name": "HVAC replacement", "amount": 30000, "month_offset": 18,
             "applies_to": "current_home"},
            {"name": "Water heater", "amount": 8000, "month_offset": 30,
             "applies_to": "current_home"},
        ]
        return inputs
    if name == "turnover_heavy_case":
        inputs["current_home"]["turnover_frequency_months"] = 12
        inputs["current_home"]["vacancy_months_per_year_base"] = 1.5
        return inputs
    if name == "sell_reinvestment_case":
        inputs["reinvestment"]["invest_monthly_sell_savings"] = True
        inputs["reinvestment"]["monthly_savings_reinvestment_return_annual_pct"] = 0.04
        return inputs
    raise ValueError(f"Unknown fixture name: {name}")


FIXTURE_NAMES = (
    "base_case",
    "recession_case",
    "refi_year5_case",
    "capex_shock_case",
    "turnover_heavy_case",
    "sell_reinvestment_case",
)


def _emit_fixture(name: str, out_dir: str) -> str:
    """Compute a named scenario and write {inputs, expected_top_line,
    expected_strategy_net_worths} to a JSON file. Returns the output path.
    """
    import json as _json
    import os as _os

    inputs = _fixture_inputs(name)
    result = compute_full_analysis(inputs)
    strategies = result.get("strategies", {})
    expected = {
        "calc_version": CALC_VERSION,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "inputs": inputs,
        "expected": {
            "lean": result.get("lean"),
            "top_line": result.get("top_line"),
            "strategy_net_worths": {
                k: strategies.get(k, {}).get("net_worth_end") for k in strategies
            },
        },
    }
    _os.makedirs(out_dir, exist_ok=True)
    path = _os.path.join(out_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(expected, f, indent=2, sort_keys=True, default=str)
    return path


def _default_fixture_dir() -> str:
    """Anchor the default fixture dir to the repo root so the CLI works from
    any cwd. `rent_vs_sell.py` lives at src/pipa/analysis/rent_vs_sell.py,
    so the repo root is three parents up.
    """
    import pathlib
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    return str(repo_root / "tests" / "fixtures" / "rent_vs_sell")


def _main_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Rent vs Sell engine CLI")
    parser.add_argument(
        "--emit-fixture",
        choices=FIXTURE_NAMES + ("all",),
        help="Emit a golden fixture JSON to tests/fixtures/rent_vs_sell/",
    )
    parser.add_argument(
        "--fixture-dir",
        default=_default_fixture_dir(),
        help="Directory to write fixtures into (default: <repo>/tests/fixtures/rent_vs_sell)",
    )
    args = parser.parse_args()

    if args.emit_fixture:
        names = FIXTURE_NAMES if args.emit_fixture == "all" else (args.emit_fixture,)
        for name in names:
            path = _emit_fixture(name, args.fixture_dir)
            print(f"wrote {path}")


if __name__ == "__main__":
    _main_cli()
