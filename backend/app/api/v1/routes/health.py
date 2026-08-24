"""Liveness, capability, and access-code endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.auth import is_enabled
from app.api.deps import AnimationServiceDep, ContainerDep, RequireApiKey
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
        requires_key=is_enabled(container.settings.api_key),
    )


@router.post(
    "/auth/check",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Test an access code",
    dependencies=[RequireApiKey],
)
def check_api_key() -> Response:
    """Lets the UI tell the user their code is wrong immediately.

    Without this they would only find out after composing a prompt and waiting
    for the 401. Safe as a guessing oracle only because the code is expected to
    be `openssl rand -hex 32`, not something memorable.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)
