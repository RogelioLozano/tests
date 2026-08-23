"""Liveness endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(container: ContainerDep) -> HealthResponse:
    return HealthResponse(status="ok", environment=container.settings.environment)
