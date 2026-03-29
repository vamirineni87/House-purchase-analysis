"""Render analysis results as a self-contained HTML report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2

from pipa.utils.formatters import format_currency, format_number, format_percentage

TEMPLATE_DIR = Path(__file__).parent / "templates"


class HtmlRenderer:
    """Produce a single-file HTML report with inlined CSS."""

    def __init__(self) -> None:
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )
        # Register custom Jinja2 filters
        self.env.filters["currency"] = format_currency
        self.env.filters["pct"] = format_percentage
        self.env.filters["number"] = format_number

    def render(
        self,
        property_data: dict[str, Any],
        analyses: dict[str, Any],
    ) -> str:
        """Render a self-contained HTML report from property data and analyses.

        Parameters
        ----------
        property_data:
            Property information dict. Expected keys include ``address``
            (with ``street``, ``city``, ``state``, ``zip_code``), ``list_price``,
            ``square_feet``, etc.
        analyses:
            Mapping of analysis name to result dict/model.

        Returns
        -------
        str
            Complete HTML document as a string.
        """
        # Serialise any Pydantic models in analyses
        serialised: dict[str, Any] = {}
        for name, result in analyses.items():
            if result is None:
                continue
            if hasattr(result, "model_dump"):
                serialised[name] = result.model_dump(mode="json")
            else:
                serialised[name] = result

        # Read CSS to inline in the document
        css_path = TEMPLATE_DIR / "static" / "style.css"
        css = css_path.read_text() if css_path.exists() else ""

        template = self.env.get_template("base.html.j2")
        html = template.render(
            property=property_data,
            analyses=serialised,
            css=css,
            generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        )
        return html
