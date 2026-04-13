"""Rent vs Sell analysis models.

Two tables:
  - current_home_profile: reusable "my home" assumption set
  - rent_vs_sell_run: one saved analysis (assumptions + cached outputs)

`assumptions_json` is the source of truth. `outputs_json` and `summary_json`
are cached and recomputed when `calc_version` no longer matches the engine's
current CALC_VERSION.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin, UUIDMixin


class CurrentHomeProfile(Base, UUIDMixin, TimestampMixin):
    """A reusable assumption set for the user's existing home.

    Fields are nested under `config_json` so the schema can evolve without
    migrations. See schemas/rent_vs_sell.py for the canonical key set.
    """

    __tablename__ = "current_home_profile"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class RentVsSellRun(Base, UUIDMixin, TimestampMixin):
    """One saved rent-vs-sell analysis run.

    A run is one assumption set + all four strategy outputs. The caller can
    link it to a target property (the "new home") and a current-home profile.
    """

    __tablename__ = "rent_vs_sell_run"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_label: Mapped[str] = mapped_column(String(32), default="base", nullable=False)

    target_property_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("property.id"), nullable=True
    )
    current_home_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("current_home_profile.id"), nullable=True
    )

    comparison_horizon_years: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # Source of truth + provenance
    assumptions_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_property_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    current_home_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_from_property_detail: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_prefill_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Cached outputs — authoritative only while calc_version matches
    calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
