"""Job dispatch registry.

`ANIM_JOBS_BACKEND` selects how work is executed:

    inline  run on the calling thread; the request blocks until the render ends
    thread  hand to a bounded pool and return immediately (use when deployed)

Both satisfy the same port and the API answers 202 either way, so the choice is
an operational one rather than a design one. A broker-backed adapter joins as a
third entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.application.render_pipeline import RenderPipeline
from app.domain.errors import ConfigurationError
from app.domain.ports.jobs import JobQueue
from app.domain.ports.logging import Logger
from app.infrastructure.jobs.inline_queue import InlineJobQueue
from app.infrastructure.jobs.thread_queue import ThreadPoolJobQueue


@dataclass(frozen=True, slots=True)
class JobDispatch:
    queue: JobQueue
    shutdown: Callable[[], None]


def _build_inline(
    pipeline: RenderPipeline, logger: Logger, max_workers: int
) -> JobDispatch:
    return JobDispatch(queue=InlineJobQueue(pipeline, logger), shutdown=lambda: None)


def _build_thread(
    pipeline: RenderPipeline, logger: Logger, max_workers: int
) -> JobDispatch:
    queue = ThreadPoolJobQueue(pipeline, logger, max_workers=max_workers)
    return JobDispatch(queue=queue, shutdown=queue.close)


_BACKENDS: dict[str, Callable[[RenderPipeline, Logger, int], JobDispatch]] = {
    "inline": _build_inline,
    "thread": _build_thread,
}


def build_job_dispatch(
    backend: str, pipeline: RenderPipeline, logger: Logger, max_workers: int
) -> JobDispatch:
    try:
        build = _BACKENDS[backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown jobs backend {backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    return build(pipeline, logger, max_workers)
