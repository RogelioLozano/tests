"""Orphaned job recovery tests.

The scenario: the process died between writing a status and finishing the work.
Nothing else in the system will ever move those rows, so a client polling one
waits forever unless startup cleans up.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.application.job_recovery import JobRecovery
from app.domain.errors import RepositoryError
from app.domain.models import JobStatus, Quality, RenderJob, StoredArtifact
from tests.conftest import FrozenClock, RecordingLogger


def make_job(job_id: str, status: JobStatus) -> RenderJob:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return RenderJob(
        id=job_id,
        prompt="draw a circle",
        status=status,
        quality=Quality.LOW,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def recovery(repository, logger: RecordingLogger) -> JobRecovery:
    return JobRecovery(jobs=repository, clock=FrozenClock(), logger=logger)


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.PENDING,
        JobStatus.GENERATING,
        JobStatus.VALIDATING,
        JobStatus.RENDERING,
        JobStatus.STORING,
    ],
)
def test_every_non_terminal_state_is_reaped(
    repository, recovery: JobRecovery, status: JobStatus
) -> None:
    repository.add(make_job("a", status))

    assert recovery.reconcile() == 1
    reaped = repository.get("a")
    assert reaped.status is JobStatus.FAILED
    assert reaped.failure.code == "interrupted"
    assert "retry" in reaped.failure.message.lower()


def test_terminal_jobs_are_left_alone(repository, recovery: JobRecovery) -> None:
    succeeded = make_job("done", JobStatus.RENDERING).succeeded(
        StoredArtifact(key="done.mp4", size_bytes=10),
        duration_ms=50,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    repository.add(succeeded)

    assert recovery.reconcile() == 0
    assert repository.get("done").status is JobStatus.SUCCEEDED
    assert repository.get("done").artifact_key == "done.mp4"


def test_reaps_only_the_stranded_ones(repository, recovery: JobRecovery) -> None:
    repository.add(make_job("stuck1", JobStatus.RENDERING))
    repository.add(make_job("stuck2", JobStatus.PENDING))
    repository.add(
        make_job("done", JobStatus.RENDERING).succeeded(
            StoredArtifact(key="done.mp4", size_bytes=10),
            duration_ms=50,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )

    assert recovery.reconcile() == 2
    assert repository.get("done").status is JobStatus.SUCCEEDED


def test_reconcile_is_idempotent(repository, recovery: JobRecovery) -> None:
    """Restart loops must not keep rewriting the same rows."""
    repository.add(make_job("a", JobStatus.RENDERING))

    assert recovery.reconcile() == 1
    assert recovery.reconcile() == 0


def test_it_logs_what_it_reaped(
    repository, recovery: JobRecovery, logger: RecordingLogger
) -> None:
    repository.add(make_job("a", JobStatus.RENDERING))
    recovery.reconcile()

    events = {event: fields for _, event, fields in logger.events}
    assert events["recovery.job_interrupted"]["previous_status"] == "rendering"
    assert events["recovery.completed"]["reaped"] == 1


def test_a_broken_repository_does_not_block_startup(
    logger: RecordingLogger,
) -> None:
    """The API is still useful without recovery; refusing to boot is worse."""

    class BrokenRepository:
        def find_unfinished(self, *, limit: int):
            raise RepositoryError("database is locked")

    recovery = JobRecovery(
        jobs=BrokenRepository(), clock=FrozenClock(), logger=logger
    )
    assert recovery.reconcile() == 0
    assert "recovery.query_failed" in logger.names()


def test_startup_runs_recovery(settings, repository, logger: RecordingLogger) -> None:
    """Wiring check: the container must actually call it."""
    from app.core.container import Container

    repository.add(make_job("a", JobStatus.RENDERING))
    recovery = JobRecovery(jobs=repository, clock=FrozenClock(), logger=logger)
    container = Container(
        settings=settings,
        logger_factory=None,
        logger=logger,
        animations=None,
        migrate=lambda: None,
        recover=recovery.reconcile,
    )

    container.startup()
    assert repository.get("a").status is JobStatus.FAILED
