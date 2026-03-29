"""Stress testing — pure functions, no I/O.

Scenario analysis for interest-rate changes, insurance inflation,
and downside-sale outcomes.
"""

from __future__ import annotations

from pipa.analysis.financial import calculate_monthly_payment


def stress_test_rates(
    loan_amount: float,
    interest_rate: float,
    term_years: int,
    rate_deltas: list[float] | None = None,
) -> dict[float, dict]:
    """Test how rate changes affect the monthly P&I payment.

    Parameters
    ----------
    loan_amount:
        The mortgage principal.
    interest_rate:
        Current / base annual interest rate.
    term_years:
        Loan term.
    rate_deltas:
        List of rate deltas to test (e.g. ``[0.005, 0.01, 0.015]``).
        Defaults to half-point increments up to +1.5 %.

    Returns
    -------
    dict mapping each rate delta to a dict with ``new_rate``,
    ``new_payment``, ``base_payment``, ``payment_increase``, and
    ``annual_increase``.
    """
    if rate_deltas is None:
        rate_deltas = [0.005, 0.01, 0.015]

    base_payment = calculate_monthly_payment(loan_amount, interest_rate, term_years)
    results: dict[float, dict] = {}

    for delta in rate_deltas:
        new_rate = interest_rate + delta
        new_payment = calculate_monthly_payment(loan_amount, new_rate, term_years)
        increase = round(new_payment - base_payment, 2)
        results[delta] = {
            "new_rate": round(new_rate, 4),
            "base_payment": base_payment,
            "new_payment": new_payment,
            "payment_increase": increase,
            "annual_increase": round(increase * 12, 2),
        }

    return results


def stress_test_insurance(
    base_payment: float,
    inflation_rates: list[float],
    years: int,
) -> dict[float, list[float]]:
    """Project insurance costs under various annual inflation rates.

    Parameters
    ----------
    base_payment:
        Current annual insurance premium.
    inflation_rates:
        List of annual inflation rates to model (e.g. ``[0.05, 0.10, 0.15]``).
    years:
        Number of years to project.

    Returns
    -------
    dict mapping each inflation rate to a list of projected annual premiums
    (index 0 = year 1).
    """
    results: dict[float, list[float]] = {}

    for rate in inflation_rates:
        projections: list[float] = []
        current = base_payment
        for _ in range(years):
            current = round(current * (1 + rate), 2)
            projections.append(current)
        results[rate] = projections

    return results


def stress_test_downside_sale(
    purchase_price: float,
    depreciation_pcts: list[float],
    years_held: int,
    selling_costs_pct: float = 0.08,
    remaining_mortgage_balance: float | None = None,
    loan_amount: float | None = None,
    interest_rate: float | None = None,
    term_years: int | None = None,
) -> dict[float, dict]:
    """Model net proceeds from a forced sale at various depreciation levels.

    Parameters
    ----------
    purchase_price:
        Original purchase price.
    depreciation_pcts:
        List of price-decline percentages to model (e.g. ``[0.05, 0.10, 0.20]``).
    years_held:
        How many years before the forced sale.
    selling_costs_pct:
        Total selling costs as fraction of sale price.
    remaining_mortgage_balance:
        If provided, use this directly. Otherwise compute from loan params.
    loan_amount, interest_rate, term_years:
        Used to compute remaining balance if ``remaining_mortgage_balance``
        is not provided.

    Returns
    -------
    dict mapping each depreciation pct to a dict with ``sale_price``,
    ``selling_costs``, ``remaining_balance``, ``net_proceeds``, and
    ``loss_from_purchase``.
    """
    # Compute remaining balance if not provided
    if remaining_mortgage_balance is not None:
        balance = remaining_mortgage_balance
    elif loan_amount is not None and interest_rate is not None and term_years is not None:
        monthly_rate = interest_rate / 12.0
        monthly_pi = calculate_monthly_payment(loan_amount, interest_rate, term_years)
        balance = loan_amount
        months = min(years_held * 12, term_years * 12)
        for _ in range(months):
            interest = balance * monthly_rate
            principal = monthly_pi - interest
            balance -= principal
        balance = max(balance, 0.0)
    else:
        balance = 0.0

    results: dict[float, dict] = {}

    for pct in depreciation_pcts:
        sale_price = round(purchase_price * (1 - pct), 2)
        selling_costs = round(sale_price * selling_costs_pct, 2)
        net_proceeds = round(sale_price - selling_costs - balance, 2)
        loss = round(net_proceeds - purchase_price * (1 - selling_costs_pct), 2)

        results[pct] = {
            "sale_price": sale_price,
            "selling_costs": selling_costs,
            "remaining_balance": round(balance, 2),
            "net_proceeds": net_proceeds,
            "loss_from_purchase": round(purchase_price - sale_price, 2),
            "underwater": net_proceeds < 0,
        }

    return results


def run_stress_tests(
    list_price: float,
    loan_amount: float,
    interest_rate: float,
    term_years: int = 30,
    annual_insurance: float = 0.0,
    rate_deltas: list[float] | None = None,
    insurance_inflation_rates: list[float] | None = None,
    insurance_projection_years: int = 10,
    depreciation_pcts: list[float] | None = None,
    downside_years_held: int = 5,
    selling_costs_pct: float = 0.08,
) -> dict:
    """Run all stress tests and return a combined results dict.

    Parameters
    ----------
    list_price:
        Property purchase / list price.
    loan_amount:
        Mortgage principal.
    interest_rate:
        Annual rate.
    term_years:
        Loan term.
    annual_insurance:
        Current annual insurance premium (for insurance stress test).
    rate_deltas:
        Rate shocks to test. Defaults to ``[0.005, 0.01, 0.015]``.
    insurance_inflation_rates:
        Insurance inflation scenarios. Defaults to ``[0.05, 0.10, 0.15]``.
    insurance_projection_years:
        Years to project insurance costs.
    depreciation_pcts:
        Home-value decline scenarios. Defaults to ``[0.05, 0.10, 0.20]``.
    downside_years_held:
        Years before forced sale in downside scenario.
    selling_costs_pct:
        Total selling costs as a fraction of sale price.

    Returns
    -------
    dict with keys ``"rate_shock"``, ``"insurance_inflation"``,
    ``"downside_sale"``.
    """
    if insurance_inflation_rates is None:
        insurance_inflation_rates = [0.05, 0.10, 0.15]
    if depreciation_pcts is None:
        depreciation_pcts = [0.05, 0.10, 0.20]

    rate_shock = stress_test_rates(
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        term_years=term_years,
        rate_deltas=rate_deltas,
    )

    insurance = stress_test_insurance(
        base_payment=annual_insurance,
        inflation_rates=insurance_inflation_rates,
        years=insurance_projection_years,
    )

    downside = stress_test_downside_sale(
        purchase_price=list_price,
        depreciation_pcts=depreciation_pcts,
        years_held=downside_years_held,
        selling_costs_pct=selling_costs_pct,
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        term_years=term_years,
    )

    return {
        "rate_shock": rate_shock,
        "insurance_inflation": insurance,
        "downside_sale": downside,
    }
