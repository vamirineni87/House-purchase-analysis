"""PDF report renderer (requires weasyprint)."""

from __future__ import annotations

from pathlib import Path


class PdfRenderer:
    """Converts an HTML report to PDF using weasyprint."""

    def render(self, html_path: Path, output_dir: Path) -> Path:
        """Generate a PDF from an existing HTML report.

        Parameters
        ----------
        html_path:
            Path to the HTML file to convert.
        output_dir:
            Directory for the output PDF (filename mirrors the HTML source).

        Returns
        -------
        Path
            The path to the generated PDF file.

        Raises
        ------
        RuntimeError
            If weasyprint is not installed.
        """
        pdf_path = html_path.with_suffix(".pdf")
        try:
            from weasyprint import HTML
        except ImportError:
            raise RuntimeError(
                "weasyprint is required for PDF generation. "
                "Install with: pip install weasyprint"
            )
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return pdf_path
