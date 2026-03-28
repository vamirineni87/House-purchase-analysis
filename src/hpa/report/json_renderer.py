"""JSON report renderer."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from hpa.models.property import PropertyDetails
from hpa.report.generator import AnalysisResults


class JsonRenderer:
    """Renders analysis results to a structured JSON file."""

    def render(
        self,
        property_details: PropertyDetails,
        results: AnalysisResults,
        output_dir: Path,
    ) -> Path:
        """Write a JSON report and return the output path.

        Parameters
        ----------
        property_details:
            The subject property.
        results:
            Container with all analysis results.
        output_dir:
            Directory to write the JSON file into.

        Returns
        -------
        Path
            The path to the written JSON file.
        """
        slug = re.sub(r"[^a-z0-9]+", "-", property_details.address.street.lower())[:30]
        slug = slug.strip("-")
        path = output_dir / f"analysis-{slug}.json"

        data: dict = {
            "generated_at": datetime.now().isoformat(),
            "property": property_details.model_dump(mode="json"),
            "analysis": {},
        }

        for field_name in (
            "financial",
            "appraisal",
            "neighborhood",
            "investment",
            "tax",
            "insurance",
        ):
            result = getattr(results, field_name, None)
            if result is not None:
                if hasattr(result, "model_dump"):
                    data["analysis"][field_name] = result.model_dump(mode="json")
                else:
                    data["analysis"][field_name] = result

        path.write_text(json.dumps(data, indent=2, default=str))
        return path
