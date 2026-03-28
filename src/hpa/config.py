"""Configuration loader using Pydantic v2 and PyYAML.

Loads settings from a YAML file with environment variable overrides
using the HPA_ prefix for API keys.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ApiKeys(BaseModel):
    """External API keys for data providers."""

    fred: Optional[str] = None
    rentcast: Optional[str] = None
    greatschools: Optional[str] = None
    walkscore: Optional[str] = None
    api_ninjas: Optional[str] = None
    census: Optional[str] = None


class Defaults(BaseModel):
    """Default assumptions for financial calculations."""

    homeowners_insurance_annual_pct: float = 0.0035
    pmi_annual_pct: float = 0.005
    pmi_ltv_threshold: float = 0.80
    property_tax_rate: float = 0.012
    closing_cost_pct: float = 0.03
    appreciation_rate: float = 0.03
    inflation_rate: float = 0.025
    moving_cost_estimate: float = 5000.0
    maintenance_annual_pct: float = 0.01
    vacancy_rate: float = 0.05
    marginal_tax_rate: float = 0.24
    filing_status: str = "married"


class CurrentHomeConfig(BaseModel):
    """Configuration for the buyer's current home (if applicable)."""

    purchase_price: float
    purchase_date: date
    estimated_current_value: float
    remaining_mortgage_balance: float
    monthly_payment: float
    mortgage_rate: float
    annual_property_tax: float
    annual_insurance: float
    capital_improvements: float = 0.0
    years_as_primary_residence: float
    estimated_monthly_rent: float = 0.0


class AppConfig(BaseModel):
    """Top-level application configuration."""

    api_keys: ApiKeys = Field(default_factory=ApiKeys)
    defaults: Defaults = Field(default_factory=Defaults)
    current_home: Optional[CurrentHomeConfig] = None


# Mapping of environment variable suffixes to ApiKeys field names.
_API_KEY_ENV_MAP: dict[str, str] = {
    "FRED": "fred",
    "RENTCAST": "rentcast",
    "GREATSCHOOLS": "greatschools",
    "WALKSCORE": "walkscore",
    "API_NINJAS": "api_ninjas",
    "CENSUS": "census",
}


def load_config(path: str = "config.yaml") -> AppConfig:
    """Load application configuration from a YAML file.

    Environment variables with the ``HPA_`` prefix override API key values
    found in the YAML file.  For example, ``HPA_FRED`` overrides
    ``api_keys.fred``.

    Parameters
    ----------
    path:
        Path to the YAML configuration file.  If the file does not exist,
        default values are used for all settings.

    Returns
    -------
    AppConfig
        Fully resolved application configuration.
    """
    config_path = Path(path)
    raw: dict = {}

    if config_path.is_file():
        with open(config_path, "r") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                raw = loaded

    config = AppConfig.model_validate(raw)

    # Apply environment variable overrides for API keys.
    for env_suffix, field_name in _API_KEY_ENV_MAP.items():
        env_value = os.environ.get(f"HPA_{env_suffix}")
        if env_value is not None:
            setattr(config.api_keys, field_name, env_value)

    return config
