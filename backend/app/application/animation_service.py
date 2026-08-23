"""Application service for the animation feature.

Owns the use cases the API exposes: accept a prompt, hand the work to the job
queue, and read jobs back. It never renders anything itself — that is the
pipeline's job, reached through the `JobQueue` port — which is what keeps
"synchronous now, workers later" out of the HTTP contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Sequence

from app.domain.errors import NotFoundError, ValidationError
from app.domain.models import JobStatus, Quality, RenderJob
from app.domain.ports.clock import Clock, IdGenerator
from app.domain.ports.jobs import JobQueue
from app.domain.ports.logging import Logger
from app.domain.ports.repository import RenderJobRepository
from app.domain.ports.storage import ArtifactStorage


@dataclass(frozen=True, slots=True)
class JobPage:
    items: Sequence[RenderJob]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class ArtifactDownload:
    """Either a redirect target or a stream the API should proxy."""

    url: str | None
    stream: BinaryIO | None
    content_type: str
    size_bytes: int | None


class AnimationService:
    def __init__(
        self,
        *,
        jobs: RenderJobRepository,
        queue: JobQueue,
        storage: ArtifactStorage,
        clock: Clock,
        ids: IdGenerator,
        logger: Logger,
        max_prompt_chars: int,
        max_page_size: int,
    ) -> None:
        self._jobs = jobs
        self._queue = queue
        self._storage = storage
        self._clock = clock
        self._ids = ids
        self._logger = logger
        self._max_prompt_chars = max_prompt_chars
        self._max_page_size = max_page_size

    def submit_prompt(self, prompt: str, quality: Quality) -> RenderJob:
        cleaned = prompt.strip()
        if not cleaned:
            raise ValidationError("Prompt must not be empty")
        if len(cleaned) > self._max_prompt_chars:
            raise ValidationError(
                f"Prompt must be at most {self._max_prompt_chars} characters"
            )

        now = self._clock.now()
        job = RenderJob(
            id=self._ids.new_id(),
            prompt=cleaned,
            status=JobStatus.PENDING,
            quality=quality,
            created_at=now,
            updated_at=now,
        )
        self._jobs.add(job)
        self._logger.info(
            "prompt.received",
            job_id=job.id,
            prompt_chars=len(cleaned),
            quality=quality.value,
        )

        self._queue.enqueue(job.id)
        # Re-read: an inline queue has already finished, a broker-backed one has
        # not. Either way the caller gets the current truth.
        return self._jobs.find(job.id) or job

    def get_job(self, job_id: str) -> RenderJob:
        return self._jobs.get(job_id)

    def list_jobs(self, *, limit: int, offset: int) -> JobPage:
        bounded = max(1, min(limit, self._max_page_size))
        offset = max(0, offset)
        return JobPage(
            items=self._jobs.list(limit=bounded, offset=offset),
            total=self._jobs.count(),
            limit=bounded,
            offset=offset,
        )

    def open_artifact(self, job_id: str) -> ArtifactDownload:
        job = self._jobs.get(job_id)
        if job.status is not JobStatus.SUCCEEDED or not job.artifact_key:
            raise NotFoundError(f"Render job {job_id} has no video")

        url = self._storage.public_url(job.artifact_key)
        if url is not None:
            return ArtifactDownload(
                url=url, stream=None, content_type="video/mp4", size_bytes=job.size_bytes
            )
        return ArtifactDownload(
            url=None,
            stream=self._storage.open(job.artifact_key),
            content_type="video/mp4",
            size_bytes=job.size_bytes,
        )
