"""Domain entities and value objects.

Pure data: no framework imports, no I/O. Every other layer may depend on this
module; this module depends on nothing but the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    """Lifecycle of a render job.

    The terminal states are SUCCEEDED and FAILED. The intermediate states are
    reported to clients verbatim, so a background worker can publish progress
    without the API contract changing.
    """

    PENDING = "pending"
    GENERATING = "generating"
    VALIDATING = "validating"
    RENDERING = "rendering"
    STORING = "storing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED)


class Quality(str, Enum):
    """Render quality presets, mapped to renderer-specific flags by the adapter.

    Ordered, because peak memory scales sharply with it — roughly 217 MB, 388 MB
    and 981 MB — so a deployment has to be able to forbid the top of the range.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return _QUALITY_ORDER.index(self)

    def exceeds(self, ceiling: "Quality") -> bool:
        return self.rank > ceiling.rank

    @classmethod
    def up_to(cls, ceiling: "Quality") -> tuple["Quality", ...]:
        return tuple(q for q in _QUALITY_ORDER if not q.exceeds(ceiling))


_QUALITY_ORDER = (Quality.LOW, Quality.MEDIUM, Quality.HIGH)


@dataclass(frozen=True, slots=True)
class GeneratedScene:
    """Manim source produced from a prompt by an AI provider."""

    code: str
    scene_name: str
    provider: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    line: int | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        return "; ".join(
            f"{issue.code}: {issue.message}"
            + (f" (line {issue.line})" if issue.line is not None else "")
            for issue in self.issues
        )


@dataclass(frozen=True, slots=True)
class RenderedScene:
    """A rendered video sitting in renderer-owned scratch space."""

    path: str
    render_ms: int
    size_bytes: int


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """A video that has been handed to durable storage."""

    key: str
    size_bytes: int
    content_type: str = "video/mp4"


@dataclass(frozen=True, slots=True)
class JobFailure:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RenderJob:
    """The unit of work tracked from prompt to playable video.

    Instances are immutable; state transitions return a new job so a repository
    write is always an explicit step rather than a side effect of mutation.
    """

    id: str
    prompt: str
    status: JobStatus
    quality: Quality
    created_at: datetime
    updated_at: datetime
    scene_name: str | None = None
    generated_code: str | None = None
    provider: str | None = None
    model: str | None = None
    artifact_key: str | None = None
    duration_ms: int | None = None
    size_bytes: int | None = None
    failure: JobFailure | None = None

    def with_status(self, status: JobStatus, now: datetime) -> RenderJob:
        return replace(self, status=status, updated_at=now)

    def with_generation(self, scene: GeneratedScene, now: datetime) -> RenderJob:
        return replace(
            self,
            scene_name=scene.scene_name,
            generated_code=scene.code,
            provider=scene.provider,
            model=scene.model,
            updated_at=now,
        )

    def succeeded(
        self, artifact: StoredArtifact, duration_ms: int, now: datetime
    ) -> RenderJob:
        return replace(
            self,
            status=JobStatus.SUCCEEDED,
            artifact_key=artifact.key,
            size_bytes=artifact.size_bytes,
            duration_ms=duration_ms,
            failure=None,
            updated_at=now,
        )

    def failed(self, failure: JobFailure, now: datetime) -> RenderJob:
        return replace(self, status=JobStatus.FAILED, failure=failure, updated_at=now)


@dataclass(frozen=True, slots=True)
class GitHubSession:
    """One browser's delegated access to a visitor's public GitHub data.

    Identified by the *hash* of the cookie value rather than the value itself,
    so a leaked copy of this table cannot be replayed as a login: the only
    place the real token exists is the user's own cookie jar.

    `access_token` is GitHub's, and never leaves the server.
    """

    token_hash: str
    login: str
    access_token: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    avatar_url: str | None = None
