"""Repository and storage adapter tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.errors import NotFoundError, StorageError
from app.domain.models import JobFailure, JobStatus, Quality, RenderJob, StoredArtifact


def make_job(job_id: str, *, created: str = "2026-01-01T00:00:00+00:00") -> RenderJob:
    now = datetime.fromisoformat(created)
    return RenderJob(
        id=job_id,
        prompt="draw a circle",
        status=JobStatus.PENDING,
        quality=Quality.LOW,
        created_at=now,
        updated_at=now,
    )


def test_round_trips_a_job(repository) -> None:
    repository.add(make_job("a"))
    assert repository.get("a").prompt == "draw a circle"


def test_update_persists_the_terminal_state(repository) -> None:
    repository.add(make_job("a"))
    job = repository.get("a")
    repository.update(
        job.succeeded(
            StoredArtifact(key="a.mp4", size_bytes=42),
            duration_ms=100,
            now=datetime.now(timezone.utc),
        )
    )

    stored = repository.get("a")
    assert stored.status is JobStatus.SUCCEEDED
    assert stored.artifact_key == "a.mp4"
    assert stored.size_bytes == 42


def test_update_persists_failure_details(repository) -> None:
    repository.add(make_job("a"))
    failed = repository.get("a").failed(
        JobFailure("render_failed", "timed out"), datetime.now(timezone.utc)
    )
    repository.update(failed)

    stored = repository.get("a")
    assert stored.failure == JobFailure("render_failed", "timed out")


def test_update_of_an_unknown_job_raises(repository) -> None:
    with pytest.raises(NotFoundError):
        repository.update(make_job("ghost"))


def test_list_is_newest_first_and_paged(repository) -> None:
    repository.add(make_job("a", created="2026-01-01T00:00:00+00:00"))
    repository.add(make_job("b", created="2026-01-02T00:00:00+00:00"))
    repository.add(make_job("c", created="2026-01-03T00:00:00+00:00"))

    assert [job.id for job in repository.list(limit=2)] == ["c", "b"]
    assert [job.id for job in repository.list(limit=2, offset=2)] == ["a"]
    assert repository.count() == 3


def test_storage_round_trips_a_file(storage, tmp_path) -> None:
    source = tmp_path / "render.mp4"
    source.write_bytes(b"bytes")

    artifact = storage.save("job.mp4", str(source), content_type="video/mp4")

    assert artifact.size_bytes == 5
    assert storage.exists("job.mp4")
    with storage.open("job.mp4") as handle:
        assert handle.read() == b"bytes"
    assert not source.exists(), "the source should have been moved, not copied"


@pytest.mark.parametrize(
    "key", ["../escape.mp4", "nested/key.mp4", "", ".hidden", "a" * 200]
)
def test_storage_rejects_keys_that_could_escape_the_root(storage, key: str) -> None:
    with pytest.raises(StorageError):
        storage.exists(key)


def test_storage_open_of_a_missing_key_raises_not_found(storage) -> None:
    with pytest.raises(NotFoundError):
        storage.open("absent.mp4")
