"""Persistence ports."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from app.domain.models import GitHubSession, RenderJob


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


class GitHubSessionRepository(Protocol):
    """Delegated GitHub access, keyed by the hash of a browser's cookie value.

    There is deliberately no `list`: sessions are looked up one at a time by a
    caller that already holds the token, never enumerated.
    """

    def add(self, session: GitHubSession) -> None: ...

    def find(self, token_hash: str, *, now: datetime) -> GitHubSession | None:
        """An expired session is never returned, so a missed expiry check
        upstream cannot be turned into a valid login."""
        ...

    def delete(self, token_hash: str) -> None:
        """Idempotent: logging out twice, or after expiry, is not an error."""
        ...

    def purge_expired(self, *, now: datetime) -> int:
        """Drop rows past their expiry; returns how many went."""
        ...
