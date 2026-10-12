from typing import Any


class AppError(Exception):
    """Base for errors that map to an API response; raised anywhere, rendered by the global handler."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
