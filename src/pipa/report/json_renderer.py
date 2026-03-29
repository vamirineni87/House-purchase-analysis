"""JSON report renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pipa


class JsonRenderer:
    """Renders analysis results to a structured JSON dict with metadata."""

    def render(
        self,
        property_data: dict[str, Any],
        analyses: dict[str, Any],
    ) -> dict:
        """Combine property info and all analysis results into one JSON structure.

        The output includes metadata (``generated_at``, ``version``) and
        separate top-level keys for ``property`` and ``analyses``.

        Parameters
        ----------
        property_data:
            Property information (address, price, features, etc.).
        analyses:
            Mapping of analysis name to result.  Values may be dicts or
            Pydantic models (which will be serialised via ``model_dump``).

        Returns
        -------
        dict
            Complete report as a Python dict.
        """
        serialised_analyses: dict[str, Any] = {}

        for name, result in analyses.items():
            if result is None:
                continue
            if hasattr(result, "model_dump"):
                serialised_analyses[name] = result.model_dump(mode="json")
            else:
                serialised_analyses[name] = result

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": pipa.__version__,
            "property": property_data,
            "analyses": serialised_analyses,
        }
