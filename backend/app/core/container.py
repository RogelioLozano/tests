"""Composition root.

The single place where interfaces are bound to implementations. Everything
above this file depends on ports only, which is what makes the local adapters
(SQLite, local disk, template AI, stdlib logging) replaceable by hosted ones
without edits anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.application.animation_service import AnimationService
from app.application.job_recovery import JobRecovery
from app.application.render_pipeline import RenderPipeline
from app.core.clock import SystemClock, UuidGenerator
from app.core.config import Settings
from app.domain.models import Quality
from app.domain.ports.logging import Logger, LoggerFactory
from app.domain.ports.rate_limit import RateLimiter
from app.domain.ports.repository import GitHubSessionRepository
from app.infrastructure.ai.factory import build_scene_generator
from app.infrastructure.jobs.factory import build_job_dispatch
from app.infrastructure.logging.factory import build_logger_factory
from app.infrastructure.persistence.factory import build_persistence
from app.infrastructure.rate_limit.factory import build_rate_limiter
from app.infrastructure.rendering.factory import build_renderer
from app.infrastructure.storage.factory import build_storage
from app.infrastructure.validation.ast_validator import AstSceneCodeValidator


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    logger_factory: LoggerFactory
    logger: Logger
    animations: AnimationService
    migrate: Callable[[], None]
    rate_limiter: RateLimiter | None = None
    github_sessions: GitHubSessionRepository | None = None
    drain: Callable[[], None] = lambda: None
    recover: Callable[[], int] = lambda: 0
    purge_sessions: Callable[[], int] = lambda: 0

    def startup(self) -> None:
        self.migrate()
        # Before any new work is accepted, so a client polling a job stranded by
        # the previous run gets an answer immediately.
        self.recover()
        self.purge_sessions()
        self.logger.info(
            "app.started",
            environment=self.settings.environment,
            ai_provider=self.settings.ai.provider,
            ai_model=self.settings.ai.llm.model,
            storage_backend=self.settings.storage.backend,
            database_backend=self.settings.database.backend,
            jobs_backend=self.settings.jobs_backend,
        )

    def shutdown(self) -> None:
        self.drain()
        self.logger.info("app.stopped")


def build_container(settings: Settings) -> Container:
    logger_factory = build_logger_factory(settings.logging, settings.environment)
    log = logger_factory.get_logger

    persistence = build_persistence(settings.database, log("db"))
    storage = build_storage(settings.storage, log("storage"))
    generator = build_scene_generator(settings.ai, log("ai"))
    validator = AstSceneCodeValidator(settings.validation, log("validation"))
    renderer = build_renderer(settings.render, log("render"))
    clock = SystemClock()

    pipeline = RenderPipeline(
        jobs=persistence.jobs,
        generator=generator,
        validator=validator,
        renderer=renderer,
        storage=storage,
        clock=clock,
        logger=log("pipeline"),
        max_attempts=settings.ai.max_attempts,
    )
    dispatch = build_job_dispatch(
        settings.jobs_backend, pipeline, log("jobs"), settings.jobs_max_workers
    )

    animations = AnimationService(
        jobs=persistence.jobs,
        queue=dispatch.queue,
        storage=storage,
        clock=clock,
        ids=UuidGenerator(),
        logger=log("animations"),
        max_prompt_chars=settings.ai.max_prompt_chars,
        max_page_size=settings.max_page_size,
        max_quality=Quality(settings.render.max_quality),
    )

    container = Container(
        settings=settings,
        logger_factory=logger_factory,
        logger=log("app"),
        animations=animations,
        migrate=persistence.initialise,
        rate_limiter=build_rate_limiter(settings.rate_limit, log("ratelimit")),
        github_sessions=persistence.github_sessions,
        drain=dispatch.shutdown,
        recover=JobRecovery(
            jobs=persistence.jobs, clock=clock, logger=log("recovery")
        ).reconcile,
        purge_sessions=lambda: persistence.github_sessions.purge_expired(
            now=clock.now()
        ),
    )
    return container
