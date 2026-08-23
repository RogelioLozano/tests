"""Inline job dispatch.

Runs the pipeline on the calling thread, so a submission is complete by the
time the request returns. The queue port is still in front of it: replacing
this with a broker-backed adapter is a one-line change in the composition root,
and neither the API nor the frontend can tell — both already treat a job as
something to poll.
"""

from __future__ import annotations

from app.application.render_pipeline import RenderPipeline
from app.core.context import bound_context
from app.domain.errors import DomainError
from app.domain.ports.logging import Logger


class InlineJobQueue:
    def __init__(self, pipeline: RenderPipeline, logger: Logger) -> None:
        self._pipeline = pipeline
        self._logger = logger

    def enqueue(self, job_id: str) -> None:
        self._logger.info("job.enqueued", job_id=job_id, mode="inline")
        with bound_context(job_id=job_id):
            try:
                self._pipeline.run(job_id)
            except DomainError:
                # The pipeline already recorded the failure on the job; the
                # enqueue call itself still succeeded.
                self._logger.warning("job.finished_with_error", job_id=job_id)
