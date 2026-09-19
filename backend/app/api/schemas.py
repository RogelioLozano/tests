"""HTTP data-transfer objects.

Deliberately separate from the domain models: this is the published contract.
Adding a field to `RenderJob` should not silently change what the API returns,
and the mapping below is where any divergence gets resolved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.application.animation_service import JobPage
from app.domain.models import GitHubSession, Quality, RenderJob, Repository


class CreateAnimationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=1_000)
    quality: Quality = Quality.LOW


class JobFailureResponse(BaseModel):
    code: str
    message: str


class AnimationJobResponse(BaseModel):
    id: str
    prompt: str
    status: str
    quality: str
    created_at: datetime
    updated_at: datetime
    scene_name: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    size_bytes: int | None = None
    video_url: str | None = None
    error: JobFailureResponse | None = None

    @classmethod
    def from_domain(cls, job: RenderJob) -> "AnimationJobResponse":
        return cls(
            id=job.id,
            prompt=job.prompt,
            status=job.status.value,
            quality=job.quality.value,
            created_at=job.created_at,
            updated_at=job.updated_at,
            scene_name=job.scene_name,
            provider=job.provider,
            model=job.model,
            duration_ms=job.duration_ms,
            size_bytes=job.size_bytes,
            # Always the API's own route: the client is insulated from where the
            # bytes actually live, now or after a move to object storage.
            video_url=f"/api/v1/animations/{job.id}/video" if job.artifact_key else None,
            error=(
                JobFailureResponse(code=job.failure.code, message=job.failure.message)
                if job.failure
                else None
            ),
        )


class AnimationJobListResponse(BaseModel):
    items: list[AnimationJobResponse]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_domain(cls, page: JobPage) -> "AnimationJobListResponse":
        return cls(
            items=[AnimationJobResponse.from_domain(job) for job in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )


class SceneSourceResponse(BaseModel):
    job_id: str
    scene_name: str | None
    code: str | None


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str


class CapabilitiesResponse(BaseModel):
    """What this particular deployment can afford.

    Lets the UI offer only the qualities the instance has the memory for,
    instead of hard-coding a list that is wrong on a small box.
    """

    qualities: list[str]
    default_quality: str
    max_prompt_chars: int
    # Whether submitting a prompt needs an access code. Not the code itself,
    # obviously — only whether the UI should ask for one.
    requires_key: bool = False


class GitHubConnectionResponse(BaseModel):
    """Enough for the UI to choose between "connect", "connected" and "hidden".

    Carries no token: the session lives in an HttpOnly cookie the page cannot
    read, which is the point.
    """

    available: bool
    connected: bool
    login: str | None = None
    avatar_url: str | None = None
    expires_at: datetime | None = None

    @classmethod
    def from_domain(cls, session: GitHubSession | None) -> "GitHubConnectionResponse":
        if session is None:
            return cls(available=True, connected=False)
        return cls(
            available=True,
            connected=True,
            login=session.login,
            avatar_url=session.avatar_url,
            expires_at=session.expires_at,
        )


class RepositoryResponse(BaseModel):
    name: str
    full_name: str
    url: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    pushed_at: datetime | None = None
    is_fork: bool = False

    @classmethod
    def from_domain(cls, repository: Repository) -> "RepositoryResponse":
        return cls(
            name=repository.name,
            full_name=repository.full_name,
            url=repository.url,
            description=repository.description,
            language=repository.language,
            stars=repository.stars,
            forks=repository.forks,
            pushed_at=repository.pushed_at,
            is_fork=repository.is_fork,
        )


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse]
    total: int

    @classmethod
    def from_domain(
        cls, repositories: Sequence[Repository]
    ) -> "RepositoryListResponse":
        return cls(
            items=[RepositoryResponse.from_domain(r) for r in repositories],
            total=len(repositories),
        )
