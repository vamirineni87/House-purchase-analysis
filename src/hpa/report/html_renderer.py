"""Render analysis results as a self-contained HTML report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import jinja2

from hpa.models.property import PropertyDetails
from hpa.report.generator import AnalysisResults
from hpa.utils.formatters import format_currency, format_number, format_percentage

TEMPLATE_DIR = Path(__file__).parent / "templates"


class HtmlRenderer:
    """Produce a single-file HTML report with inlined CSS."""

    def __init__(self) -> None:
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )
        self.env.filters["currency"] = format_currency
        self.env.filters["pct"] = format_percentage
        self.env.filters["number"] = format_number

    def render(
        self,
        property_details: PropertyDetails,
        results: AnalysisResults,
        output_dir: Path,
    ) -> Path:
        """Render *results* for *property_details* and write to *output_dir*.

        Returns the path to the generated HTML file.
        """
        slug = property_details.address.street.lower().replace(" ", "-")[:30]
        path = output_dir / f"analysis-{slug}.html"

        # Read CSS to inline in the document
        css_path = TEMPLATE_DIR / "static" / "style.css"
        css = css_path.read_text() if css_path.exists() else ""

        template = self.env.get_template("base.html.j2")
        html = template.render(
            property=property_details,
            results=results,
            css=css,
            generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        )
        path.write_text(html)
        return path
