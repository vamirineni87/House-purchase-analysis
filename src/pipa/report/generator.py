"""Report orchestrator that coordinates JSON and HTML renderers."""

from __future__ import annotations

from typing import Any


class ReportGenerator:
    """Orchestrates report generation across multiple output formats."""

    def generate_json_report(
        self,
        property_data: dict[str, Any],
        analyses: dict[str, Any],
    ) -> dict:
        """Generate a structured JSON report with all analysis results.

        Parameters
        ----------
        property_data:
            Property information (address, price, features, etc.).
        analyses:
            Mapping of analysis name to result dict/model.

        Returns
        -------
        dict
            Complete report as a Python dict ready for serialisation.
        """
        from pipa.report.json_renderer import JsonRenderer
        return JsonRenderer().render(property_data, analyses)

    def generate_html_report(
        self,
        property_data: dict[str, Any],
        analyses: dict[str, Any],
    ) -> str:
        """Generate a self-contained HTML report.

        Parameters
        ----------
        property_data:
            Property information (address, price, features, etc.).
        analyses:
            Mapping of analysis name to result dict/model.

        Returns
        -------
        str
            Complete HTML document as a string.
        """
        from pipa.report.html_renderer import HtmlRenderer
        return HtmlRenderer().render(property_data, analyses)

    def generate_report(
        self,
        property_data: dict[str, Any],
        analyses: dict[str, Any],
        format: str = "json",
    ) -> str | dict:
        """Generate a report in the requested format.

        Parameters
        ----------
        property_data:
            Property information dict.
        analyses:
            Mapping of analysis name to result dict/model.
        format:
            Output format — ``"json"`` (default) or ``"html"``.

        Returns
        -------
        str | dict
            HTML string for ``"html"`` format, dict for ``"json"`` format.

        Raises
        ------
        ValueError
            If *format* is not ``"json"`` or ``"html"``.
        """
        if format == "json":
            return self.generate_json_report(property_data, analyses)
        elif format == "html":
            return self.generate_html_report(property_data, analyses)
        else:
            raise ValueError(f"Unsupported report format: {format!r}. Use 'json' or 'html'.")
