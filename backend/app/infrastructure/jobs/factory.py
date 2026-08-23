"""Job dispatch registry.

`ANIM_JOBS_BACKEND` selects how work is executed. Only `inline` exists today;
a worker-backed entry slots in here without touching the service or the API.
"""

from __future__ import annotations

from typing import Callable

from app.application.render_pipeline import RenderPipeline
from app.domain.errors import ConfigurationError
from app.domain.ports.jobs import JobQueue
from app.domain.ports.logging import Logger
from app.infrastructure.jobs.inline_queue import InlineJobQueue

_BACKENDS: dict[str, Callable[[RenderPipeline, Logger], JobQueue]] = {
    "inline": InlineJobQueue,
}


def build_job_queue(
    backend: str, pipeline: RenderPipeline, logger: Logger
) -> JobQueue:
    try:
        build = _BACKENDS[backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown jobs backend {backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    return build(pipeline, logger)
