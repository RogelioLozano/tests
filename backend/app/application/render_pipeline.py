"""The render pipeline: prompt in, stored video out.

The only place that knows the order of the steps. It talks exclusively to
ports, so the same code path runs unchanged whether it is invoked inline by the
API thread today or by a Celery/arq worker tomorrow.

Failure policy: every step's error is caught, recorded on the job, and
persisted. A job never leaves the pipeline in a non-terminal state, and the
caller is never handed an exception — a failed render is data, not a crash.
"""

from __future__ import annotations

import time

from app.domain.errors import DomainError, NotFoundError, UnsafeCodeError
from app.domain.models import (
    GeneratedScene,
    JobFailure,
    JobStatus,
    RenderJob,
)
from app.domain.ports.ai import SceneCodeGenerator
from app.domain.ports.clock import Clock
from app.domain.ports.logging import Logger
from app.domain.ports.rendering import SceneRenderer
from app.domain.ports.repository import RenderJobRepository
from app.domain.ports.storage import ArtifactStorage
from app.domain.ports.validation import SceneCodeValidator

ARTIFACT_CONTENT_TYPE = "video/mp4"


def scene_name_for(job_id: str) -> str:
    """A Python identifier derived from the job id, stable across retries."""
    return f"Scene_{job_id.replace('-', '')[:16]}"


class RenderPipeline:
    def __init__(
        self,
        *,
        jobs: RenderJobRepository,
        generator: SceneCodeGenerator,
        validator: SceneCodeValidator,
        renderer: SceneRenderer,
        storage: ArtifactStorage,
        clock: Clock,
        logger: Logger,
        max_attempts: int = 1,
    ) -> None:
        self._jobs = jobs
        self._generator = generator
        self._validator = validator
        self._renderer = renderer
        self._storage = storage
        self._clock = clock
        self._logger = logger
        self._max_attempts = max(1, max_attempts)

    def run(self, job_id: str) -> RenderJob:
        try:
            job = self._jobs.get(job_id)
        except NotFoundError:
            self._logger.error("pipeline.job_missing", job_id=job_id)
            raise

        if job.status.is_terminal:
            # Makes redelivery from a future broker harmless.
            self._logger.info(
                "pipeline.skipped", job_id=job_id, status=job.status.value
            )
            return job

        log = self._logger.bind(job_id=job_id)
        log.info("pipeline.started", quality=job.quality.value)
        started = time.monotonic()
        rendered_path: str | None = None

        try:
            scene = self._generate_valid_scene(job, log)
            job = job.with_generation(scene, self._clock.now())
            self._jobs.update(job)

            job = self._advance(job, JobStatus.RENDERING)
            rendered = self._renderer.render(
                scene.code,
                scene_name=scene.scene_name,
                quality=job.quality,
                job_id=job_id,
            )
            rendered_path = rendered.path

            job = self._advance(job, JobStatus.STORING)
            artifact = self._storage.save(
                f"{job_id}.mp4", rendered.path, content_type=ARTIFACT_CONTENT_TYPE
            )
            rendered_path = None  # save() consumed the file from scratch space.

            total_ms = int((time.monotonic() - started) * 1000)
            job = job.succeeded(artifact, total_ms, self._clock.now())
            self._jobs.update(job)
            log.info(
                "pipeline.completed",
                total_ms=total_ms,
                render_ms=rendered.render_ms,
                size_bytes=artifact.size_bytes,
                artifact_key=artifact.key,
            )
            return job

        except DomainError as exc:
            return self._fail(job, exc.code, exc.message, log, started)
        except Exception as exc:  # noqa: BLE001 - a job must always reach a terminal state
            log.error("pipeline.crashed", exc_info=True, error=str(exc))
            return self._fail(
                job,
                "internal_error",
                "The render job failed unexpectedly",
                log,
                started,
            )
        finally:
            if rendered_path:
                self._renderer.discard(rendered_path)

    def _generate_valid_scene(self, job: RenderJob, log: Logger) -> GeneratedScene:
        """Generate, validate, and on rejection hand the reasons back to the model.

        A model that has been told the rules still breaks them; the validator's
        complaint is the most useful correction signal available, so it becomes
        the next prompt. The budget is bounded, and the last rejection is what
        fails the job.
        """
        scene_name = scene_name_for(job.id)
        feedback: list[str] = []

        for attempt in range(1, self._max_attempts + 1):
            self._advance_generation(job, attempt)
            scene = self._generator.generate(
                job.prompt, scene_name=scene_name, feedback=feedback
            )

            self._logger.info(
                "pipeline.stage", job_id=job.id, status=JobStatus.VALIDATING.value
            )
            report = self._validator.validate(scene.code, scene_name=scene_name)
            if report.is_valid:
                if attempt > 1:
                    log.info("pipeline.repair_succeeded", attempt=attempt)
                return scene

            summary = report.summary()
            log.warning(
                "pipeline.generation_rejected",
                attempt=attempt,
                max_attempts=self._max_attempts,
                detail=summary,
            )
            feedback.append(summary)

        raise UnsafeCodeError(
            f"Generated code was rejected by validation after "
            f"{self._max_attempts} attempt(s): {feedback[-1]}"
        )

    def _advance_generation(self, job: RenderJob, attempt: int) -> None:
        # Status is written straight through rather than via _advance: the job
        # record the loop holds is stale once it has been re-saved.
        self._jobs.update(job.with_status(JobStatus.GENERATING, self._clock.now()))
        self._logger.info(
            "pipeline.stage",
            job_id=job.id,
            status=JobStatus.GENERATING.value,
            attempt=attempt,
        )

    def _advance(self, job: RenderJob, status: JobStatus) -> RenderJob:
        job = job.with_status(status, self._clock.now())
        self._jobs.update(job)
        self._logger.info("pipeline.stage", job_id=job.id, status=status.value)
        return job
    def _fail(
        self, job: RenderJob, code: str, message: str, log: Logger, started: float
    ) -> RenderJob:
        failed = job.failed(JobFailure(code=code, message=message), self._clock.now())
        log.error(
            "pipeline.failed",
            error_code=code,
            error_message=message,
            total_ms=int((time.monotonic() - started) * 1000),
        )
        try:
            self._jobs.update(failed)
        except DomainError:
            log.error("pipeline.failure_not_persisted", exc_info=True)
        return failed
