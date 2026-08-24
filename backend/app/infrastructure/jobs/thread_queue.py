"""Background job dispatch on a bounded thread pool.

The step the `JobQueue` port was built for. A render takes seconds to minutes,
which is longer than a platform load balancer will hold a connection open, so
in a deployed environment `enqueue` has to return before the work is done. The
API already answers 202 and the frontend already polls, so switching from
`inline` to this changes no contract — only `ANIM_JOBS_BACKEND`.

Concurrency is capped because rendering is CPU-bound: on a small instance, two
simultaneous Manim processes are already competing for the same cores.

Still a single process, so it does not survive a restart. That is the point at
which a real broker (Redis/SQS) earns its keep, and it slots in behind the same
port.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.application.render_pipeline import RenderPipeline
from app.core.context import bound_context, current_context
from app.domain.errors import DomainError
from app.domain.ports.logging import Logger


class ThreadPoolJobQueue:
    def __init__(
        self, pipeline: RenderPipeline, logger: Logger, max_workers: int = 2
    ) -> None:
        self._pipeline = pipeline
        self._logger = logger
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="render"
        )

    def enqueue(self, job_id: str) -> None:
        # Context variables are not inherited by pool threads, so the request id
        # is captured here and re-bound inside the worker; without this the
        # render logs would lose their correlation to the request.
        context = current_context()
        self._logger.info("job.enqueued", job_id=job_id, mode="thread")
        self._executor.submit(self._run, job_id, context)

    def _run(self, job_id: str, context: dict[str, Any]) -> None:
        with bound_context(**context, job_id=job_id):
            try:
                self._pipeline.run(job_id)
            except DomainError:
                # Already recorded on the job by the pipeline.
                self._logger.warning("job.finished_with_error", job_id=job_id)
            except Exception:  # noqa: BLE001 - a worker thread must never die silently
                self._logger.error("job.worker_crashed", exc_info=True, job_id=job_id)

    def close(self) -> None:
        """Let in-flight renders finish so a deploy does not orphan a job."""
        self._logger.info("jobs.draining")
        self._executor.shutdown(wait=True)
