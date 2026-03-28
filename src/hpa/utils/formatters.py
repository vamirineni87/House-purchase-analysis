"""Formatting utilities for currency, percentages, and numbers."""

from __future__ import annotations


def format_currency(value: float) -> str:
    """Format a numeric value as US-dollar currency.

    Parameters
    ----------
    value:
        The amount to format.

    Returns
    -------
    str
        A string like ``"$1,234.56"`` or ``"-$1,234.56"`` for negative values.
    """
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format a decimal fraction as a percentage string.

    Parameters
    ----------
    value:
        A fraction (e.g. ``0.1234`` for 12.34%).
    decimals:
        Number of decimal places in the output.

    Returns
    -------
    str
        A string like ``"12.34%"``.
    """
    return f"{value * 100:,.{decimals}f}%"


def format_number(value: float, decimals: int = 0) -> str:
    """Format a number with thousands separators.

    Parameters
    ----------
    value:
        The number to format.
    decimals:
        Number of decimal places.

    Returns
    -------
    str
        A string like ``"1,234"`` or ``"1,234.50"``.
    """
    return f"{value:,.{decimals}f}"
