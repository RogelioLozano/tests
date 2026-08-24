"""Rate limiter registry.

`ANIM_RATE_LIMIT_BACKEND` selects the implementation. A Redis-backed entry
joins here when the app runs more than one instance and the quota has to be
shared between them.
"""

from __future__ import annotations

from typing import Callable

from app.core.config import RateLimitSettings
from app.domain.errors import ConfigurationError
from app.domain.ports.logging import Logger
from app.domain.ports.rate_limit import Quota, RateLimiter, RENDERS, REQUESTS
from app.infrastructure.rate_limit.memory_limiter import InMemoryRateLimiter


def _build_memory(settings: RateLimitSettings, logger: Logger) -> RateLimiter:
    return InMemoryRateLimiter(
        {
            RENDERS: Quota(settings.render_limit, settings.render_window_seconds),
            REQUESTS: Quota(settings.request_limit, settings.request_window_seconds),
        },
        logger,
        max_identities=settings.max_identities,
    )


_BACKENDS: dict[str, Callable[[RateLimitSettings, Logger], RateLimiter]] = {
    "memory": _build_memory,
}


def build_rate_limiter(settings: RateLimitSettings, logger: Logger) -> RateLimiter:
    try:
        build = _BACKENDS[settings.backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown rate limit backend {settings.backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    logger.info(
        "ratelimit.configured",
        backend=settings.backend,
        renders=f"{settings.render_limit}/{settings.render_window_seconds}s",
        requests=f"{settings.request_limit}/{settings.request_window_seconds}s",
        trust_proxy=settings.trust_proxy,
    )
    return build(settings, logger)
