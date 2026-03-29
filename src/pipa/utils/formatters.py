"""Formatting utilities for currency, percentages, and numbers."""

from __future__ import annotations


def format_currency(value: float) -> str:
    """Format a numeric value as US-dollar currency.

    >>> format_currency(1234.56)
    '$1,234.56'
    >>> format_currency(-500)
    '-$500.00'
    """
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format a decimal fraction as a percentage string.

    >>> format_percentage(0.1234)
    '12.34%'
    """
    return f"{value * 100:,.{decimals}f}%"


def format_number(value: float, decimals: int = 0) -> str:
    """Format a number with thousands separators.

    >>> format_number(1234)
    '1,234'
    """
    return f"{value:,.{decimals}f}"
