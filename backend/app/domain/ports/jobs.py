"""Job dispatch port.

The seam that keeps "synchronous today, background workers tomorrow" from
becoming an API change: the service always enqueues and returns immediately
with a job id. The inline adapter happens to finish the work before `enqueue`
returns; a broker-backed adapter would not, and no caller can tell the
difference from the contract alone.
"""

from __future__ import annotations

from typing import Protocol


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None:
        """Hand `job_id` off for processing.

        Implementations must not raise for failures of the job itself; a failed
        job is recorded on the job record, not signalled to the enqueuer.
        """
        ...
