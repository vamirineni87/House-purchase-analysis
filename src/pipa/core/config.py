"""Application configuration via Pydantic Settings.

Loads from environment variables (PIPA_ prefix), .env file, and optional config.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiKeys(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIPA_")

    fred_api_key: str = ""
    rentcast_api_key: str = ""
    greatschools_api_key: str = ""
    walkscore_api_key: str = ""
    api_ninjas_key: str = ""
    census_api_key: str = ""
    noaa_token: str = ""
    propdata_api_key: str = ""


class FinancialDefaults(BaseSettings):
    mortgage_rate_30yr: float = 6.5
    mortgage_rate_15yr: float = 5.9
    homeowners_insurance_rate: float = 0.0035
    pmi_rate: float = 0.005
    pmi_threshold: float = 0.80
    property_tax_rate: float = 0.012
    appreciation_rate: float = 0.03
    inflation_rate: float = 0.025
    maintenance_rate: float = 0.01
    closing_cost_rate: float = 0.03
    vacancy_rate: float = 0.05
    marginal_tax_rate: float = 0.24
    filing_status: str = "married"


class ReplacementDefaults(BaseSettings):
    roof_lifespan: int = 25
    hvac_lifespan: int = 15
    water_heater_lifespan: int = 12
    electrical_panel_lifespan: int = 40
    windows_lifespan: int = 25
    siding_lifespan: int = 30


class CurrentHome(BaseSettings):
    address: str = "43629 White Cap Ter, Chantilly, VA 20152"
    county: str = "loudoun"
    purchase_price: float = 0
    purchase_date: str = ""
    current_mortgage_payment: float = 0
    estimated_value: float = 0
    remaining_mortgage: float = 0
    filing_status: str = "married"
    years_as_primary: int = 0
    estimated_monthly_rent: float = 0
    year_built: int = 2011
    annual_property_tax: float = 0
    annual_insurance: float = 0


class CountyConfig(BaseSettings):
    property_tax_rate: float = 0.012
    gis_base_url: str = ""
    # Fairfax-specific
    icare_base_url: str = ""
    plus_base_url: str = ""
    # Loudoun-specific
    parcel_db_url: str = ""
    landmarc_url: str = ""


class ScraperConfig(BaseSettings):
    rate_limit_per_second: float = 1.0
    cache_ttl_hours: int = 24
    playwright_headless: bool = False  # Non-headless avoids most CAPTCHA detection
    save_html_snapshots: bool = True
    save_screenshots_on_error: bool = True


class AppConfig(BaseSettings):
    """Root application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PIPA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./pipa.db"

    # Storage paths
    storage_dir: Path = Path("./storage")
    raw_payload_dir: Path = Path("./raw_payloads")

    # Sub-configs (populated from YAML)
    api_keys: ApiKeys = Field(default_factory=ApiKeys)
    defaults: FinancialDefaults = Field(default_factory=FinancialDefaults)
    replacement_defaults: ReplacementDefaults = Field(default_factory=ReplacementDefaults)
    current_home: CurrentHome = Field(default_factory=CurrentHome)
    counties: dict[str, CountyConfig] = Field(default_factory=dict)
    scrapers: ScraperConfig = Field(default_factory=ScraperConfig)


def _load_api_keys_from_db(db_url: str) -> dict[str, str]:
    """Read API keys from app_setting table (sync, at startup)."""
    import json
    import sqlite3

    # Extract file path from SQLAlchemy URL
    path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    if not Path(path).exists():
        return {}

    try:
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("SELECT key, value_json FROM app_setting WHERE category = 'api_keys'")
        keys = {}
        for key, value_json in c.fetchall():
            try:
                keys[key] = json.loads(value_json)
            except (json.JSONDecodeError, TypeError):
                keys[key] = value_json
        conn.close()
        return keys
    except Exception:
        return {}


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from .env + optional YAML file + DB app_setting."""
    yaml_data: dict[str, Any] = {}

    if config_path and config_path.exists():
        with open(config_path) as f:
            yaml_data = yaml.safe_load(f) or {}
    else:
        # Try default location
        default_path = Path("config.yaml")
        if default_path.exists():
            with open(default_path) as f:
                yaml_data = yaml.safe_load(f) or {}

    # Build config, merging YAML data into sub-models
    config = AppConfig()

    if "defaults" in yaml_data:
        config.defaults = FinancialDefaults(**yaml_data["defaults"])
    if "current_home" in yaml_data:
        config.current_home = CurrentHome(**yaml_data["current_home"])
    if "counties" in yaml_data:
        config.counties = {k: CountyConfig(**v) for k, v in yaml_data["counties"].items()}
    if "scrapers" in yaml_data:
        config.scrapers = ScraperConfig(**yaml_data["scrapers"])

    # Load API keys from DB (app_setting table, set via Settings UI)
    db_keys = _load_api_keys_from_db(config.database_url)
    if db_keys:
        for attr in ("fred_api_key", "rentcast_api_key", "greatschools_api_key",
                      "walkscore_api_key", "api_ninjas_key", "census_api_key", "noaa_token",
                      "propdata_api_key"):
            # Check both lowercase and UPPERCASE DB keys
            db_val = db_keys.get(attr, "") or db_keys.get(attr.upper(), "")
            if db_val and not getattr(config.api_keys, attr, ""):
                setattr(config.api_keys, attr, db_val)

    # Ensure storage dirs exist
    config.storage_dir.mkdir(parents=True, exist_ok=True)
    config.raw_payload_dir.mkdir(parents=True, exist_ok=True)

    return config
