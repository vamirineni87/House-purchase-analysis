"""Add rent_vs_sell tables and seed starter current-home profile

Revision ID: a1b2c3d4e5f6
Revises: ed2ac2045645
Create Date: 2026-04-12 00:00:00.000000
"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "ed2ac2045645"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Starter defaults for the White Cap Ter current-home profile. All fields are
# nested under config_json so schema changes don't require migrations.
_WHITE_CAP_TER_CONFIG = {
    # Core
    "value_today": 790000,
    "basis": 478000,
    "loan_balance": 295413,
    "mortgage_rate": 0.025,
    # Monthly carrying costs (split — no PITI lump)
    "monthly_principal_interest": 1245,
    "monthly_taxes": 620,
    "monthly_insurance": 120,
    "monthly_hoa": 0,
    "monthly_misc_owner_paid": 80,
    # Rental conversion
    "insurance_conversion_bump_pct": 0.15,
    "initial_lease_up_vacancy_months": 1.0,
    # Sale + rent
    "sell_cost_pct_now": 0.07,
    "monthly_rent_base": 3500,
    "land_pct": 0.2974,
    "building_pct": 0.7026,
    "move_out_month": "2026-05",
    "rent_start_month": "2026-06",
    # Rental operations
    "reserve_months_per_year": 2,
    "self_manage": True,
    "property_management_pct": 0.00,
    "vacancy_months_per_year_base": 0.5,
    "bad_debt_pct_of_gross_rent": 0.005,
    "leasing_fee_pct_of_annual_rent": 0.05,
    "turnover_cost_per_event": 2500,
    "turnover_frequency_months": 24,
    "routine_maintenance_pct_of_rent": 0.05,
    "maintenance_inflation_annual_pct": 0.03,
    # Ownership cost growth
    "current_home_tax_growth_annual_pct": 0.03,
    "current_home_insurance_growth_annual_pct": 0.05,
    "current_home_hoa_growth_annual_pct": 0.03,
    "current_home_misc_growth_annual_pct": 0.03,
    # Exit friction
    "current_home_sell_cost_pct_future": 0.07,
    "sale_prep_cost_flat": 3000,
    "pre_sale_vacancy_months": 0.5,
    "concession_pct_at_sale": 0.00,
}


def upgrade() -> None:
    op.create_table(
        "current_home_profile",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rent_vs_sell_run",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("scenario_label", sa.String(length=32), nullable=False),
        sa.Column("target_property_id", sa.String(length=36), nullable=True),
        sa.Column("current_home_profile_id", sa.String(length=36), nullable=True),
        sa.Column("comparison_horizon_years", sa.Integer(), nullable=False),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column("target_property_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("current_home_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("created_from_property_detail", sa.Boolean(), nullable=False),
        sa.Column("source_prefill_version", sa.String(length=32), nullable=True),
        sa.Column("calc_version", sa.String(length=32), nullable=False),
        sa.Column("input_schema_version", sa.String(length=32), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("outputs_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["target_property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["current_home_profile_id"], ["current_home_profile.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rent_vs_sell_run_target_property_id"),
        "rent_vs_sell_run",
        ["target_property_id"],
        unique=False,
    )

    # Seed the starter White Cap Ter profile, but idempotently. If something
    # upstream (test fixture, prior partial migration) already inserted a
    # profile with this name, skip the seed — re-upgrading after a downgrade
    # must not spawn duplicate default rows.
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM current_home_profile WHERE name = :name"),
        {"name": "43629 White Cap Ter"},
    ).first()
    if existing is None:
        current_home_profile = sa.table(
            "current_home_profile",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("is_default", sa.Boolean),
            sa.column("config_json", sa.JSON),
        )
        op.bulk_insert(
            current_home_profile,
            [
                {
                    "id": str(uuid.uuid4()),
                    "name": "43629 White Cap Ter",
                    "is_default": True,
                    "config_json": _WHITE_CAP_TER_CONFIG,
                }
            ],
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_rent_vs_sell_run_target_property_id"),
        table_name="rent_vs_sell_run",
    )
    op.drop_table("rent_vs_sell_run")
    op.drop_table("current_home_profile")
