"""FastAPI application factory.

Wiring only: build the container, attach middleware, mount routes. Every piece
of behaviour lives in a layer below, which keeps this file readable and lets a
test build an app with different settings and no environment fiddling.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.middleware import REQUEST_ID_HEADER, RequestLoggingMiddleware
from app.api.rate_limit import RateLimitMiddleware
from app.api.static import mount_frontend
from app.api.v1.router import router as v1_router
from app.core.config import Settings, load_settings
from app.core.container import Container, build_container


def create_app(
    settings: Settings | None = None, container: Container | None = None
) -> FastAPI:
    """Build the app. `container` is an injection point for tests."""
    settings = settings or load_settings()
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container.startup()
        yield
        container.shutdown()

    app = FastAPI(
        title="Animation Studio API",
        version="1.0.0",
        summary="Prompt-driven Manim rendering",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        # Explicit origins, never "*": the API is credential-free today but a
        # wildcard would have to be unpicked the moment auth is added.
        allow_origins=list(settings.cors_allow_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )
    app.add_middleware(
        RequestLoggingMiddleware, logger=container.logger_factory.get_logger("http")
    )
    if container.rate_limiter is not None:
        # Added after the logger, so it runs first and a flood is rejected
        # before anything else does work for it.
        app.add_middleware(
            RateLimitMiddleware,
            limiter=container.rate_limiter,
            logger=container.logger_factory.get_logger("ratelimit"),
            trust_proxy=settings.rate_limit.trust_proxy,
        )
    register_error_handlers(app, container.logger_factory.get_logger("http"))
    app.include_router(v1_router)
    # Registered last: its catch-all must not shadow an API route.
    if settings.static_dir is not None:
        mount_frontend(
            app, settings.static_dir, container.logger_factory.get_logger("static")
        )
    return app


# No module-level `app = create_app()`: that would build the container, open
# the database, and validate credentials on mere import. Served with
# `uvicorn app.main:create_app --factory`.
