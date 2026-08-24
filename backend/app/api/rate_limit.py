"""Identifying the caller, and enforcing the cheap global quota.

Client identity is deliberately awkward: behind a proxy the socket address is
the proxy's, so the real address has to come from `X-Forwarded-For` — a header
anyone can forge. Trusting it is therefore opt-in (`ANIM_TRUST_PROXY`), because
trusting it when there is no proxy in front lets a caller mint a fresh identity
per request and bypass the limit entirely.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.schemas import ErrorResponse
from app.core.context import request_id
from app.domain.ports.logging import Logger
from app.domain.ports.rate_limit import RateLimiter, REQUESTS

# The platform probes this every 30s; counting it would be self-inflicted.
EXEMPT_PATHS = frozenset({"/api/v1/health"})

UNKNOWN_CLIENT = "unknown"


def client_identity(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Left-most entry is the original client; the rest are proxy hops.
            return forwarded.split(",")[0].strip()[:64] or UNKNOWN_CLIENT
    return request.client.host if request.client else UNKNOWN_CLIENT


def too_many_requests(retry_after: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=ErrorResponse(
            code="rate_limited", message=message, request_id=request_id()
        ).model_dump(),
        headers={"Retry-After": str(retry_after)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Generous flood protection across every endpoint.

    Sized to sit well above the frontend's polling rate; the strict quota that
    protects LLM spend is applied to the render route separately.
    """

    def __init__(
        self, app, limiter: RateLimiter, logger: Logger, trust_proxy: bool
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._logger = logger
        self._trust_proxy = trust_proxy

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        identity = client_identity(request, self._trust_proxy)
        verdict = self._limiter.check(REQUESTS, identity)
        if not verdict.allowed:
            self._logger.warning(
                "ratelimit.blocked",
                bucket=REQUESTS,
                client=identity,
                path=request.url.path,
                retry_after=verdict.retry_after_seconds,
            )
            return too_many_requests(
                verdict.retry_after_seconds,
                "Too many requests. Slow down and try again shortly.",
            )
        return await call_next(request)
