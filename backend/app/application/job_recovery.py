"""Recovering jobs stranded by a restart.

A job is written as `rendering` before Manim is invoked. If the process dies in
between — a deploy, an OOM kill, a free-tier spin-down — that row stays
non-terminal forever, and a client polling it waits forever. Nothing else in
the system ever moves it, because the only thing that would have was the worker
that died.

So on startup every non-terminal job is failed. It is honest about what
happened, it unblocks the client, and it is idempotent.

This is correct *because the deployment is single-process*: one uvicorn worker,
an in-process job queue, so at startup nothing is legitimately in flight. Under
a broker with multiple workers that assumption breaks — reaping would kill jobs
another worker is actively running — and this would need to become a lease or
heartbeat check instead.
"""

from __future__ import annotations

from app.domain.errors import DomainError
from app.domain.models import JobFailure
from app.domain.ports.clock import Clock
from app.domain.ports.logging import Logger
from app.domain.ports.repository import RenderJobRepository

INTERRUPTED = JobFailure(
    code="interrupted",
    message=(
        "The render was interrupted by a server restart and did not finish. "
        "Submit the prompt again to retry."
    ),
)


class JobRecovery:
    def __init__(
        self,
        *,
        jobs: RenderJobRepository,
        clock: Clock,
        logger: Logger,
        batch_size: int = 500,
    ) -> None:
        self._jobs = jobs
        self._clock = clock
        self._logger = logger
        self._batch_size = batch_size

    def reconcile(self) -> int:
        """Fail every job left mid-flight. Returns how many were reaped."""
        try:
            orphans = self._jobs.find_unfinished(limit=self._batch_size)
        except DomainError:
            # Never block startup on this; the API is still useful without it.
            self._logger.error("recovery.query_failed", exc_info=True)
            return 0

        reaped = 0
        for job in orphans:
            try:
                self._jobs.update(job.failed(INTERRUPTED, self._clock.now()))
            except DomainError:
                self._logger.error("recovery.update_failed", job_id=job.id)
                continue
            reaped += 1
            self._logger.warning(
                "recovery.job_interrupted",
                job_id=job.id,
                previous_status=job.status.value,
            )

        if reaped:
            self._logger.warning("recovery.completed", reaped=reaped)
        else:
            self._logger.info("recovery.completed", reaped=0)
        return reaped
