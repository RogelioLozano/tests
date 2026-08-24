"""Route dependencies.

The container is built once at startup and stashed on `app.state`; routes ask
for the service they need and never reach for a concrete adapter.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.auth import require_api_key
from app.api.rate_limit import client_identity
from app.application.animation_service import AnimationService
from app.core.container import Container
from app.domain.errors import RateLimitedError
from app.domain.ports.rate_limit import RENDERS


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_animation_service(
    container: Annotated[Container, Depends(get_container)],
) -> AnimationService:
    return container.animations


def enforce_render_quota(request: Request) -> None:
    """The strict quota, applied only where a request costs real money."""
    container: Container = request.app.state.container
    limiter = container.rate_limiter
    if limiter is None:
        return

    identity = client_identity(request, container.settings.rate_limit.trust_proxy)
    verdict = limiter.check(RENDERS, identity)
    if not verdict.allowed:
        container.logger.warning(
            "ratelimit.blocked",
            bucket=RENDERS,
            client=identity,
            retry_after=verdict.retry_after_seconds,
        )
        raise RateLimitedError(
            "Render limit reached. Try again in "
            f"{verdict.retry_after_seconds} seconds.",
            retry_after_seconds=verdict.retry_after_seconds,
        )


AnimationServiceDep = Annotated[AnimationService, Depends(get_animation_service)]
ContainerDep = Annotated[Container, Depends(get_container)]
RenderQuota = Depends(enforce_render_quota)
# The two guards on the expensive route defend the same thing for different
# reasons: the key stops strangers, the quota stops anyone (friends included)
# from running up a bill.
RequireApiKey = Depends(require_api_key)
