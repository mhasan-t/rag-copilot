from typing import Any


class AppError(Exception):
    """Base for errors that map to an API response; raised anywhere, rendered by the global handler."""

    status_code = 500
    code = "internal_error"
    headers: dict[str, str] | None = None

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    # RFC 6750: tells clients which authentication scheme to use.
    headers = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidInputError(AppError):
    """Input rejected by business rules (as opposed to request-schema validation)."""

    status_code = 422
    code = "invalid_input"


class UpstreamError(AppError):
    """A backing service we depend on (monitoring stack, deployment backend) failed or rejected our request."""

    status_code = 502
    code = "upstream_error"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
