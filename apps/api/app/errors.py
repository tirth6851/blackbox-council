"""Application error types mapped to the {"error": {"code","message"}} envelope."""
from __future__ import annotations


class AppError(Exception):
    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnsupportedMockTaskAppError(AppError):
    status_code = 422
    code = "unsupported_mock_task"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
