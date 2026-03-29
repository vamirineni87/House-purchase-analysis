"""Domain exception hierarchy."""


class PipaError(Exception):
    """Base exception for all PIPA errors."""


# Data access errors
class DataAccessError(PipaError):
    """Error accessing external data source."""


class ScraperError(DataAccessError):
    """Error during web scraping."""


class ApiClientError(DataAccessError):
    """Error calling external API."""


class RateLimitError(ApiClientError):
    """Rate limit exceeded on external API."""


class AuthenticationError(ApiClientError):
    """Authentication failed for external API."""


# Property errors
class PropertyNotFoundError(PipaError):
    """Property not found in database."""


class PropertyResolutionError(PipaError):
    """Could not resolve property identity from address or parcel ID."""


class DuplicatePropertyError(PipaError):
    """Property already exists in database."""


# Source/evidence errors
class SourceConflictError(PipaError):
    """Conflicting data from multiple sources."""

    def __init__(self, field: str, sources: list[dict], message: str = ""):
        self.field = field
        self.sources = sources
        super().__init__(message or f"Conflicting values for '{field}' from {len(sources)} sources")


class StaleDataError(PipaError):
    """Data has exceeded its freshness TTL."""


# Analysis errors
class AnalysisError(PipaError):
    """Error during analysis computation."""


class InsufficientDataError(AnalysisError):
    """Not enough data to perform analysis."""


# Worker/job errors
class JobError(PipaError):
    """Error in background job execution."""


class JobLeaseExpiredError(JobError):
    """Job lease expired before completion."""


class IdempotencyViolationError(JobError):
    """Duplicate job attempted."""
