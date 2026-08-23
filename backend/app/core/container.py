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
from app.application.render_pipeline import RenderPipeline
from app.core.clock import SystemClock, UuidGenerator
from app.core.config import Settings
from app.domain.ports.logging import Logger, LoggerFactory
from app.infrastructure.ai.factory import build_scene_generator
from app.infrastructure.jobs.factory import build_job_queue
from app.infrastructure.logging.factory import build_logger_factory
from app.infrastructure.persistence.factory import build_persistence
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

    def startup(self) -> None:
        self.migrate()
        self.logger.info(
            "app.started",
            environment=self.settings.environment,
            ai_provider=self.settings.ai.provider,
            ai_model=self.settings.ai.llm.model,
            storage_backend=self.settings.storage.backend,
            database_backend=self.settings.database.backend,
            jobs_backend=self.settings.jobs_backend,
        )


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
    queue = build_job_queue(settings.jobs_backend, pipeline, log("jobs"))

    animations = AnimationService(
        jobs=persistence.jobs,
        queue=queue,
        storage=storage,
        clock=clock,
        ids=UuidGenerator(),
        logger=log("animations"),
        max_prompt_chars=settings.ai.max_prompt_chars,
        max_page_size=settings.max_page_size,
    )

    container = Container(
        settings=settings,
        logger_factory=logger_factory,
        logger=log("app"),
        animations=animations,
        migrate=persistence.initialise,
    )
    return container
