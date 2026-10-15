"""Application errors. Each class maps to one HTTP status and error code (api-design.md §10)."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status = 400
    code = "VALIDATION_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class ValidationError(AppError):
    status = 400
    code = "VALIDATION_ERROR"


class Unauthenticated(AppError):
    status = 401
    code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status = 403
    code = "FORBIDDEN"


class QuotaExceeded(AppError):
    status = 403
    code = "QUOTA_EXCEEDED"


class NotPublished(AppError):
    status = 403
    code = "NOT_PUBLISHED"


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"


class InvalidState(AppError):
    status = 409
    code = "INVALID_STATE"


class NoChanges(AppError):
    status = 409
    code = "NO_CHANGES"


class Conflict(AppError):
    status = 409
    code = "CONFLICT"


class PreconditionFailed(AppError):
    status = 412
    code = "PRECONDITION_FAILED"


class Unprocessable(AppError):
    status = 422
    code = "UNPROCESSABLE"


class PreconditionRequired(AppError):
    status = 428
    code = "PRECONDITION_REQUIRED"


class RateLimited(AppError):
    status = 429
    code = "RATE_LIMITED"


class UpstreamUnavailable(AppError):
    status = 503
    code = "UPSTREAM_UNAVAILABLE"
