"""Job dispatch tests.

The thread backend is what makes the 202-and-poll contract honest in a
deployment, so the properties that matter are: enqueue returns before the work
finishes, the request id survives the thread hop, and a crashing job never
takes the worker down.
"""

from __future__ import annotations

import threading

import pytest

from app.core.context import bound_context, current_context
from app.domain.errors import ConfigurationError, RenderError
from app.infrastructure.jobs.factory import build_job_dispatch
from tests.conftest import RecordingLogger


class BlockingPipeline:
    """Holds the worker until the test releases it."""

    def __init__(self) -> None:
        self.released = threading.Event()
        self.started = threading.Event()
        self.seen_context: dict = {}

    def run(self, job_id: str):
        self.seen_context = current_context()
        self.started.set()
        self.released.wait(timeout=5)
        return None


class CrashingPipeline:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, job_id: str):
        self.calls += 1
        raise RuntimeError("boom")


def test_thread_backend_returns_before_the_work_finishes(
    logger: RecordingLogger,
) -> None:
    pipeline = BlockingPipeline()
    dispatch = build_job_dispatch("thread", pipeline, logger, max_workers=1)

    dispatch.queue.enqueue("job1")
    assert pipeline.started.wait(timeout=5), "worker never started"
    # Enqueue has already returned while run() is still blocked.
    assert not pipeline.released.is_set()

    pipeline.released.set()
    dispatch.shutdown()


def test_the_request_id_survives_the_thread_hop(logger: RecordingLogger) -> None:
    """Context variables are not inherited by pool threads; the queue carries
    them across so render logs stay correlated to the request."""
    pipeline = BlockingPipeline()
    pipeline.released.set()
    dispatch = build_job_dispatch("thread", pipeline, logger, max_workers=1)

    with bound_context(request_id="req-abc"):
        dispatch.queue.enqueue("job1")
    dispatch.shutdown()

    assert pipeline.seen_context.get("request_id") == "req-abc"
    assert pipeline.seen_context.get("job_id") == "job1"


def test_a_crashing_job_does_not_kill_the_worker(logger: RecordingLogger) -> None:
    pipeline = CrashingPipeline()
    dispatch = build_job_dispatch("thread", pipeline, logger, max_workers=1)

    dispatch.queue.enqueue("job1")
    dispatch.queue.enqueue("job2")
    dispatch.shutdown()

    assert pipeline.calls == 2
    assert "job.worker_crashed" in logger.names()


def test_a_domain_error_is_not_reported_as_a_crash(logger: RecordingLogger) -> None:
    class FailingPipeline:
        def run(self, job_id: str):
            raise RenderError("manim exploded")

    dispatch = build_job_dispatch("thread", FailingPipeline(), logger, max_workers=1)
    dispatch.queue.enqueue("job1")
    dispatch.shutdown()

    assert "job.finished_with_error" in logger.names()
    assert "job.worker_crashed" not in logger.names()


def test_shutdown_drains_in_flight_work(logger: RecordingLogger) -> None:
    """A deploy must not orphan a job midway through a render."""
    pipeline = BlockingPipeline()
    dispatch = build_job_dispatch("thread", pipeline, logger, max_workers=1)

    dispatch.queue.enqueue("job1")
    pipeline.started.wait(timeout=5)
    pipeline.released.set()
    dispatch.shutdown()

    assert "jobs.draining" in logger.names()


def test_inline_backend_finishes_before_returning(logger: RecordingLogger) -> None:
    calls: list[str] = []

    class Pipeline:
        def run(self, job_id: str):
            calls.append(job_id)

    dispatch = build_job_dispatch("inline", Pipeline(), logger, max_workers=1)
    dispatch.queue.enqueue("job1")
    assert calls == ["job1"]


def test_an_unknown_backend_is_a_configuration_error(logger: RecordingLogger) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        build_job_dispatch("celery", object(), logger, max_workers=1)
    assert "inline" in str(excinfo.value)
