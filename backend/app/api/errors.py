"""Domain error to HTTP status mapping.

Handlers are registered once on the app so route functions can raise domain
errors and stay free of HTTP concerns. Client-visible messages come from the
domain error; unexpected exceptions are logged in full and reported as a
generic 500, so internals never leak into a response body.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.core.context import request_id
from app.domain.errors import (
    ConfigurationError,
    DomainError,
    GenerationError,
    NotFoundError,
    RenderError,
    RepositoryError,
    StorageError,
    UnsafeCodeError,
    ValidationError,
)
from app.domain.ports.logging import Logger

# Spelled numerically: Starlette renamed its 422 constant, and the number is
# the part of the contract clients actually see.
HTTP_422_UNPROCESSABLE = 422

_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (UnsafeCodeError, HTTP_422_UNPROCESSABLE),
    (ValidationError, status.HTTP_400_BAD_REQUEST),
    (GenerationError, status.HTTP_502_BAD_GATEWAY),
    (RenderError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (StorageError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (RepositoryError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (ConfigurationError, status.HTTP_500_INTERNAL_SERVER_ERROR),
)


def _status_for(error: DomainError) -> int:
    for error_type, code in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _body(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            code=code, message=message, request_id=request_id()
        ).model_dump(),
    )


def register_error_handlers(app: FastAPI, logger: Logger) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status_code = _status_for(exc)
        log = logger.error if status_code >= 500 else logger.warning
        log("request.domain_error", error_code=exc.code, error_message=exc.message)
        return _body(exc.code, exc.message, status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("request.invalid", errors=exc.errors())
        return _body(
            "invalid_request",
            "The request body or query parameters are invalid",
            HTTP_422_UNPROCESSABLE,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("request.unhandled_error", exc_info=True, error=str(exc))
        return _body(
            "internal_error",
            "The server could not complete the request",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
