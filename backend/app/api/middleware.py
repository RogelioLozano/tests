"""Request logging and correlation.

Assigns every request an id, binds it to the ambient context so downstream logs
(including the render pipeline's) carry it, and echoes it back in
`X-Request-ID` so a client can quote it in a bug report.

An inbound `X-Request-ID` is honoured for tracing across services but is
validated first: it ends up in log records, and an unbounded header value would
be a log-injection vector.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import bound_context
from app.domain.ports.logging import Logger

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger: Logger) -> None:
        super().__init__(app)
        self._logger = logger

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex

        with bound_context(request_id=request_id):
            self._logger.info(
                "request.received",
                method=request.method,
                path=request.url.path,
                client=request.client.host if request.client else None,
            )
            started = time.monotonic()
            try:
                response = await call_next(request)
            except Exception:
                self._logger.error(
                    "request.failed",
                    exc_info=True,
                    method=request.method,
                    path=request.url.path,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                raise

            duration_ms = int((time.monotonic() - started) * 1000)
            self._logger.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
