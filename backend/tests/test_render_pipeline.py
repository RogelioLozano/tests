"""Pipeline behaviour: a job always reaches a terminal state, and never crashes
the caller."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.render_pipeline import RenderPipeline
from app.core.config import ValidationSettings
from app.domain.errors import GenerationError, RenderError
from app.domain.models import JobStatus, Quality, RenderJob
from app.infrastructure.validation.ast_validator import AstSceneCodeValidator
from tests.conftest import (
    VALID_SCENE,
    FakeGenerator,
    FakeRenderer,
    FrozenClock,
    RecordingLogger,
)


def make_pipeline(
    repository, storage, renderer, logger, generator=None, max_attempts=1
) -> RenderPipeline:
    return RenderPipeline(
        jobs=repository,
        generator=generator or FakeGenerator(),
        validator=AstSceneCodeValidator(ValidationSettings(), logger),
        renderer=renderer,
        storage=storage,
        clock=FrozenClock(),
        logger=logger,
        max_attempts=max_attempts,
    )


UNSAFE_SCENE = (
    "import os\n\n\nclass {name}(Scene):\n    def construct(self):\n        pass\n"
)


def seed(repository, clock=None) -> RenderJob:
    clock = clock or FrozenClock()
    now = clock.now()
    job = RenderJob(
        id="job0001",
        prompt="draw a circle",
        status=JobStatus.PENDING,
        quality=Quality.LOW,
        created_at=now,
        updated_at=now,
    )
    repository.add(job)
    return job


def test_success_stores_the_artifact_and_records_metadata(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    seed(repository)
    result = make_pipeline(repository, storage, renderer, logger).run("job0001")

    assert result.status is JobStatus.SUCCEEDED
    assert result.artifact_key == "job0001.mp4"
    assert result.failure is None
    assert storage.exists("job0001.mp4")
    assert repository.get("job0001").status is JobStatus.SUCCEEDED


def test_success_logs_every_stage(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    seed(repository)
    make_pipeline(repository, storage, renderer, logger).run("job0001")

    events = logger.names()
    for expected in (
        "pipeline.started",
        "pipeline.stage",
        "validation.started",
        "validation.passed",
        "storage.saved",
        "pipeline.completed",
    ):
        assert expected in events, f"missing {expected}: {events}"


def test_generation_failure_fails_the_job_without_raising(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    seed(repository)
    pipeline = make_pipeline(
        repository,
        storage,
        renderer,
        logger,
        generator=FakeGenerator(error=GenerationError("provider is down")),
    )
    result = pipeline.run("job0001")

    assert result.status is JobStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "generation_failed"
    assert repository.get("job0001").failure.message == "provider is down"


def test_unsafe_code_is_never_rendered(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    seed(repository)
    pipeline = make_pipeline(
        repository, storage, renderer, logger, generator=FakeGenerator(code=UNSAFE_SCENE)
    )
    result = pipeline.run("job0001")

    assert result.status is JobStatus.FAILED
    assert result.failure.code == "unsafe_code"
    assert not storage.exists("job0001.mp4")
    assert "render.started" not in logger.names()


def test_a_rejected_generation_is_retried_with_the_validator_errors(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    """The validator's complaint is the correction signal sent back to the model."""
    generator = FakeGenerator(codes=[UNSAFE_SCENE, VALID_SCENE])
    seed(repository)
    result = make_pipeline(
        repository, storage, renderer, logger, generator=generator, max_attempts=3
    ).run("job0001")

    assert result.status is JobStatus.SUCCEEDED
    assert len(generator.calls) == 2

    first_feedback, second_feedback = generator.calls[0][1], generator.calls[1][1]
    assert first_feedback == ()
    assert "forbidden_import" in second_feedback[0]
    assert "pipeline.repair_succeeded" in logger.names()


def test_repair_gives_up_within_the_budget(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    generator = FakeGenerator(code=UNSAFE_SCENE)
    seed(repository)
    result = make_pipeline(
        repository, storage, renderer, logger, generator=generator, max_attempts=3
    ).run("job0001")

    assert result.status is JobStatus.FAILED
    assert result.failure.code == "unsafe_code"
    assert len(generator.calls) == 3
    assert not storage.exists("job0001.mp4")


def test_render_failure_is_recorded(
    repository, storage, failing_renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    seed(repository)
    result = make_pipeline(repository, storage, failing_renderer, logger).run("job0001")

    assert result.status is JobStatus.FAILED
    assert result.failure.code == "render_failed"
    assert not storage.exists("job0001.mp4")


def test_storage_failure_discards_the_rendered_file(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger, tmp_path: Path
) -> None:
    class BrokenStorage:
        def save(self, key, source_path, *, content_type):
            from app.domain.errors import StorageError

            raise StorageError("disk full")

    seed(repository)
    pipeline = make_pipeline(repository, BrokenStorage(), renderer, logger)
    result = pipeline.run("job0001")

    assert result.status is JobStatus.FAILED
    assert result.failure.code == "storage_failed"
    assert renderer.discarded, "scratch file should have been cleaned up"


def test_a_terminal_job_is_not_reprocessed(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    """Redelivery from a future broker must be a no-op, not a second render."""
    seed(repository)
    pipeline = make_pipeline(repository, storage, renderer, logger)
    pipeline.run("job0001")
    logger.events.clear()

    pipeline.run("job0001")
    assert "pipeline.skipped" in logger.names()
    assert "render.started" not in logger.names()


def test_unknown_job_raises(
    repository, storage, renderer: FakeRenderer, logger: RecordingLogger
) -> None:
    from app.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        make_pipeline(repository, storage, renderer, logger).run("missing")
