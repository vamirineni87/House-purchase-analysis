"""Abstract base class for all analyzers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class BaseAnalyzer(ABC):
    """Base class that every analyzer must inherit from."""

    @abstractmethod
    def analyze(self, property_details, config) -> BaseModel:
        """Run analysis and return a Pydantic result model."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this analyzer."""
        ...

    @property
    def requires_api(self) -> bool:
        """Whether this analyzer needs external API calls."""
        return False
