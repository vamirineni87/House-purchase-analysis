"""Report orchestrator that coordinates all renderers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from hpa.models.property import PropertyDetails


class AnalysisResults(BaseModel):
    """Container for all analysis results."""

    financial: Any = None
    appraisal: Any = None
    neighborhood: Any = None
    investment: Any = None
    tax: Any = None
    insurance: Any = None


class ReportGenerator:
    """Orchestrates report generation across multiple output formats."""

    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(
        self,
        property_details: PropertyDetails,
        results: AnalysisResults,
        formats: list[str] | None = None,
    ) -> dict[str, Path | None]:
        """Generate reports in all requested formats.

        Parameters
        ----------
        property_details:
            The subject property information.
        results:
            Container holding results from each analysis module.
        formats:
            List of output formats. Supported: ``"html"``, ``"json"``,
            ``"terminal"``, ``"pdf"``.  Defaults to all except PDF.

        Returns
        -------
        dict[str, Path | None]
            Mapping of format name to the output file path (``None`` for
            terminal, which prints directly).
        """
        if formats is None:
            formats = ["html", "json", "terminal"]

        outputs: dict[str, Path | None] = {}

        if "terminal" in formats:
            from hpa.report.terminal_renderer import TerminalRenderer

            TerminalRenderer().render(property_details, results)
            outputs["terminal"] = None

        if "json" in formats:
            from hpa.report.json_renderer import JsonRenderer

            path = JsonRenderer().render(property_details, results, self.output_dir)
            outputs["json"] = path

        if "html" in formats:
            from hpa.report.html_renderer import HtmlRenderer

            path = HtmlRenderer().render(property_details, results, self.output_dir)
            outputs["html"] = path

        if "pdf" in formats:
            from hpa.report.pdf_renderer import PdfRenderer

            html_path = outputs.get("html")
            if html_path is None:
                from hpa.report.html_renderer import HtmlRenderer

                html_path = HtmlRenderer().render(
                    property_details, results, self.output_dir
                )
            path = PdfRenderer().render(html_path, self.output_dir)
            outputs["pdf"] = path

        return outputs
