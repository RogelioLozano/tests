"""Persistence port for render job metadata."""

from __future__ import annotations

from typing import Protocol, Sequence

from app.domain.models import RenderJob


class RenderJobRepository(Protocol):
    def add(self, job: RenderJob) -> None: ...

    def update(self, job: RenderJob) -> None:
        """Persist the new state of an existing job.

        Raises:
            NotFoundError: the job was never added.
        """
        ...

    def get(self, job_id: str) -> RenderJob:
        """Raises NotFoundError when `job_id` is unknown."""
        ...

    def find(self, job_id: str) -> RenderJob | None: ...

    def list(self, *, limit: int, offset: int = 0) -> Sequence[RenderJob]:
        """Most recently created jobs first."""
        ...

    def find_unfinished(self, *, limit: int) -> Sequence[RenderJob]:
        """Jobs in a non-terminal state, oldest first.

        After a restart these are jobs nobody is working on any more.
        """
        ...

    def count(self) -> int: ...
