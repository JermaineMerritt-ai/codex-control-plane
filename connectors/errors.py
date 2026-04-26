"""Normalized connector failures for retries, policy, and operator messaging."""


class ConnectorError(Exception):
    """Base class for connector-layer failures."""

    def __init__(self, message: str, *, provider: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.provider = provider
        self.details = details or {}


class AuthError(ConnectorError):
    """Invalid, expired, or missing credentials."""


class RateLimitError(ConnectorError):
    """Provider throttling; caller may backoff and retry."""


class TemporaryProviderError(ConnectorError):
    """Transient outage or 5xx-class conditions."""


class PermanentProviderError(ConnectorError):
    """Non-retryable client or configuration error."""
