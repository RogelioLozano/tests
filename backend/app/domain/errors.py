"""Domain error hierarchy.

Adapters translate their own failures (sqlite3, subprocess, HTTP clients) into
these types so the service layer never sees a vendor exception, and the API
layer has a single, stable set of errors to map onto status codes.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every expected failure in the system."""

    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ValidationError(DomainError):
    """Input, or AI output, failed a rule before anything was executed."""

    code = "validation_error"


class UnsafeCodeError(ValidationError):
    """Generated code did not pass the static safety check."""

    code = "unsafe_code"


class NotFoundError(DomainError):
    code = "not_found"


class RateLimitedError(DomainError):
    """The caller has spent its quota for now."""

    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: int = 60) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class UnauthorizedError(DomainError):
    """Missing or wrong credentials for an endpoint that requires them."""

    code = "unauthorized"


class GenerationError(DomainError):
    """The AI provider could not produce usable Manim source."""

    code = "generation_failed"


class RenderError(DomainError):
    """Manim exited non-zero, timed out, or produced no output file."""

    code = "render_failed"


class StorageError(DomainError):
    code = "storage_failed"


class IntegrationError(DomainError):
    """A third party this app delegates to was unreachable or misbehaved.

    Distinct from UnauthorizedError: that one means the credential was refused
    and the user can fix it by reconnecting, this one means the fault is not
    theirs and retrying later is the remedy.
    """

    code = "integration_failed"


class RepositoryError(DomainError):
    code = "repository_failed"


class ConfigurationError(DomainError):
    """A requested implementation is not registered or is misconfigured."""

    code = "configuration_error"
