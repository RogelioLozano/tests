"""Liveness and capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AnimationServiceDep, ContainerDep
from app.api.schemas import CapabilitiesResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(container: ContainerDep) -> HealthResponse:
    return HealthResponse(status="ok", environment=container.settings.environment)


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="What this deployment supports",
)
def capabilities(
    container: ContainerDep, service: AnimationServiceDep
) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        qualities=[q.value for q in service.allowed_qualities],
        default_quality=container.settings.render.default_quality,
        max_prompt_chars=container.settings.ai.max_prompt_chars,
    )
