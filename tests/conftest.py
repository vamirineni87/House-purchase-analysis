"""Shared pytest fixtures for the Home Purchase Analysis test suite."""

from datetime import date

import pytest

from hpa.config import AppConfig, CurrentHomeConfig, Defaults
from hpa.models.property import Address, PropertyDetails


@pytest.fixture()
def sample_config() -> AppConfig:
    """Return an AppConfig with reasonable defaults (no API keys needed)."""
    return AppConfig(
        defaults=Defaults(),
        current_home=CurrentHomeConfig(
            purchase_price=300_000,
            purchase_date=date(2020, 6, 15),
            estimated_current_value=380_000,
            remaining_mortgage_balance=240_000,
            monthly_payment=1800,
            mortgage_rate=0.035,
            annual_property_tax=4000,
            annual_insurance=1500,
            capital_improvements=25_000,
            years_as_primary_residence=5.5,
            estimated_monthly_rent=2200,
        ),
    )


@pytest.fixture()
def sample_property() -> PropertyDetails:
    """Return a PropertyDetails for a $450,000 house in Austin, TX."""
    return PropertyDetails(
        address=Address(
            street="123 Main St",
            city="Austin",
            state="TX",
            zip_code="78701",
        ),
        list_price=450_000,
        square_feet=2000,
        bedrooms=3,
        bathrooms=2.5,
        year_built=2005,
        hoa_monthly=150,
        lot_size_sqft=6500,
        garage_spaces=2,
        stories=2,
    )
