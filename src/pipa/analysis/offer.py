"""Offer strategy analysis — pure functions, no I/O.

Helpers for deciding max bid, walk-away price, escalation clauses,
and appraisal-gap risk.
"""

from __future__ import annotations

from pipa.analysis.financial import calculate_monthly_payment


def calculate_max_bid(
    appraisal_value: float,
    max_monthly_payment: float,
    max_cash_at_closing: float,
    interest_rate: float = 0.065,
    term_years: int = 30,
    down_payment_pct: float = 0.20,
    property_tax_rate: float = 0.012,
    insurance_rate: float = 0.0035,
    hoa_monthly: float = 0.0,
    closing_cost_pct: float = 0.03,
) -> dict:
    """Determine the maximum price a buyer can offer.

    Returns a dict with ``max_price`` and ``limiting_factor``
    (one of ``"payment"``, ``"cash"``, ``"appraisal"``).
    """
    # --- Constraint 1: monthly-payment ceiling ---
    # Back-solve: what loan amount yields max_monthly_payment after
    # subtracting tax, insurance, and HOA?
    monthly_tax_per_dollar = property_tax_rate / 12.0
    monthly_ins_per_dollar = insurance_rate / 12.0

    available_for_pi = max_monthly_payment - hoa_monthly
    # Each dollar of price adds tax + insurance to the monthly bill
    # available_for_pi must also cover tax/insurance on the final price.
    # P&I = calculate_monthly_payment(price * (1 - down_pct), rate, term)
    # monthly_tax = price * tax_rate / 12
    # monthly_ins = price * ins_rate / 12
    # Solve iteratively (Newton-ish, 10 iterations is plenty).
    price_payment = appraisal_value  # start guess
    for _ in range(20):
        loan = price_payment * (1 - down_payment_pct)
        pi = calculate_monthly_payment(loan, interest_rate, term_years)
        total = pi + price_payment * monthly_tax_per_dollar + price_payment * monthly_ins_per_dollar + hoa_monthly
        if total <= 0:
            break
        # Scale price proportionally to close the gap
        ratio = max_monthly_payment / total
        price_payment = price_payment * ratio
        if abs(total - max_monthly_payment) < 1.0:
            break
    price_payment = round(price_payment, 2)

    # --- Constraint 2: cash-at-closing ceiling ---
    # cash_needed = down_payment + closing_costs
    # down = price * down_pct, closing = price * closing_pct
    price_cash = round(max_cash_at_closing / (down_payment_pct + closing_cost_pct), 2)

    # --- Constraint 3: appraisal value ---
    price_appraisal = appraisal_value

    # Binding constraint is the minimum
    candidates = {
        "payment": price_payment,
        "cash": price_cash,
        "appraisal": price_appraisal,
    }
    limiting_factor = min(candidates, key=candidates.get)  # type: ignore[arg-type]
    max_price = round(min(candidates.values()), 2)

    return {
        "max_price": max_price,
        "limiting_factor": limiting_factor,
        "price_by_constraint": candidates,
    }


def calculate_walk_away_price(
    list_price: float,
    inspection_cost_threshold: float,
) -> float:
    """Return the effective walk-away price.

    If estimated repair costs from inspection exceed the threshold,
    the buyer should walk away or renegotiate.  The walk-away price
    is the list price plus the threshold — any offer above this
    level is unjustifiable given deferred maintenance risk.
    """
    return round(list_price + inspection_cost_threshold, 2)


def model_escalation_clause(
    base_price: float,
    increment: float,
    cap: float,
    competing_bids: list[float],
) -> list[dict]:
    """Model outcomes of an escalation clause against competing bids.

    Returns a list of dicts, one per competing bid, each containing:
    - ``competing_bid``: the other party's offer
    - ``your_price``: what you'd pay under escalation
    - ``won``: whether the escalation wins
    - ``over_cap``: whether the escalation hit the cap
    """
    outcomes: list[dict] = []
    for bid in sorted(competing_bids):
        if bid < base_price:
            # We already beat this bid at our base price
            your_price = base_price
            won = True
            over_cap = False
        else:
            # Escalate: match their bid plus increment
            escalated = bid + increment
            if escalated > cap:
                your_price = cap
                won = cap > bid
                over_cap = True
            else:
                your_price = escalated
                won = True
                over_cap = False

        outcomes.append(
            {
                "competing_bid": round(bid, 2),
                "your_price": round(your_price, 2),
                "won": won,
                "over_cap": over_cap,
            }
        )

    return outcomes


def analyze_appraisal_gap(
    offer_price: float,
    estimated_appraisal: float,
    cash_reserves: float,
) -> dict:
    """Analyze the risk of an appraisal gap.

    Returns a dict with:
    - ``gap_amount``: how much the offer exceeds the appraisal
    - ``required_cash``: extra cash needed to cover the gap
    - ``risk_level``: "none", "low", "moderate", "high"
    - ``can_cover``: whether cash reserves cover the gap
    """
    gap_amount = round(max(0.0, offer_price - estimated_appraisal), 2)

    # The lender will only lend against the appraised value, so the
    # buyer must bring the gap in cash on top of the normal down payment.
    required_cash = gap_amount
    can_cover = cash_reserves >= required_cash

    if gap_amount == 0:
        risk_level = "none"
    elif gap_amount <= estimated_appraisal * 0.03:
        risk_level = "low"
    elif gap_amount <= estimated_appraisal * 0.07:
        risk_level = "moderate"
    else:
        risk_level = "high"

    return {
        "gap_amount": gap_amount,
        "required_cash": required_cash,
        "risk_level": risk_level,
        "can_cover": can_cover,
        "gap_pct": round(gap_amount / estimated_appraisal, 4) if estimated_appraisal > 0 else 0.0,
    }
