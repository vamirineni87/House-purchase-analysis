"""Application settings stored in the database."""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pipa.models.base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    """Key-value settings for the single-user desktop app.

    Categories:
        api_keys          - Third-party API credentials
        financial_defaults - Default rates, terms, down-payment percentages
        ui_defaults        - Theme, default tab, display preferences
    """

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON, nullable=True
    )
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, default="ui_defaults"
    )
