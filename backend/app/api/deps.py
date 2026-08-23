"""Route dependencies.

The container is built once at startup and stashed on `app.state`; routes ask
for the service they need and never reach for a concrete adapter.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.application.animation_service import AnimationService
from app.core.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_animation_service(
    container: Annotated[Container, Depends(get_container)],
) -> AnimationService:
    return container.animations


AnimationServiceDep = Annotated[AnimationService, Depends(get_animation_service)]
ContainerDep = Annotated[Container, Depends(get_container)]
