"""Shared fixtures.

Adapters are wired by hand here rather than through `build_container`, which is
the point of the port design: the pipeline under test gets a real SQLite
repository and real local storage, and only the two slow/external pieces (the
AI provider and Manim) are replaced by fakes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import pytest

from app.core.config import (
    AISettings,
    DatabaseSettings,
    LoggingSettings,
    RenderSettings,
    Settings,
    StorageSettings,
    ValidationSettings,
)
from app.domain.errors import RenderError
from app.domain.models import GeneratedScene, Quality, RenderedScene
from app.infrastructure.persistence.sqlite.database import SqliteDatabase
from app.infrastructure.persistence.sqlite.job_repository import (
    SqliteRenderJobRepository,
)
from app.infrastructure.storage.local_storage import LocalDirectoryStorage

VALID_SCENE = """\
from manim import *


class {name}(Scene):
    def construct(self):
        circle = Circle()
        circle.set_fill(BLUE, opacity=0.5)
        self.play(Create(circle))
"""


class RecordingLogger:
    """Captures events so tests can assert on what was logged."""

    def __init__(self, events: list[tuple[str, str, dict[str, Any]]] | None = None):
        self.events = events if events is not None else []

    def bind(self, **fields: Any) -> "RecordingLogger":
        return RecordingLogger(self.events)

    def debug(self, event: str, /, **fields: Any) -> None:
        self.events.append(("DEBUG", event, fields))

    def info(self, event: str, /, **fields: Any) -> None:
        self.events.append(("INFO", event, fields))

    def warning(self, event: str, /, **fields: Any) -> None:
        self.events.append(("WARNING", event, fields))

    def error(self, event: str, /, exc_info: bool = False, **fields: Any) -> None:
        self.events.append(("ERROR", event, fields))

    def names(self) -> list[str]:
        return [event for _, event, _ in self.events]


class FrozenClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


class SequentialIds:
    def __init__(self) -> None:
        self._next = 0

    def new_id(self) -> str:
        self._next += 1
        return f"job{self._next:04d}"


class FakeGenerator:
    """Returns canned source, or raises, without touching a network.

    `codes` is consumed one entry per attempt, so a test can hand back invalid
    source first and valid source on the repair.
    """

    def __init__(
        self,
        code: str | None = None,
        error: Exception | None = None,
        codes: list[str] | None = None,
    ):
        self._code = code
        self._error = error
        self._codes = list(codes) if codes else None
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    provider = "fake"
    model = "fake-1"

    def generate(
        self, prompt: str, *, scene_name: str, feedback: Sequence[str] = ()
    ) -> GeneratedScene:
        self.calls.append((scene_name, tuple(feedback)))
        if self._error:
            raise self._error
        if self._codes:
            template = self._codes.pop(0) if len(self._codes) > 1 else self._codes[0]
        else:
            template = self._code or VALID_SCENE
        return GeneratedScene(
            code=template.format(name=scene_name),
            scene_name=scene_name,
            provider=self.provider,
            model=self.model,
        )


class FakeRenderer:
    """Writes a placeholder file instead of invoking Manim."""

    def __init__(self, scratch: Path, error: Exception | None = None):
        self.scratch = scratch
        self.scratch.mkdir(parents=True, exist_ok=True)
        self._error = error
        self.discarded: list[str] = []

    def render(
        self, code: str, *, scene_name: str, quality: Quality, job_id: str
    ) -> RenderedScene:
        if self._error:
            raise self._error
        target = self.scratch / f"{job_id}.mp4"
        target.write_bytes(b"fake-mp4-bytes")
        return RenderedScene(
            path=str(target), render_ms=5, size_bytes=target.stat().st_size
        )

    def discard(self, path: str) -> None:
        self.discarded.append(path)
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def logger() -> RecordingLogger:
    return RecordingLogger()


@pytest.fixture
def repository(tmp_path: Path, logger: RecordingLogger) -> SqliteRenderJobRepository:
    database = SqliteDatabase(
        DatabaseSettings(path=tmp_path / "metadata.db"), logger
    )
    database.migrate()
    return SqliteRenderJobRepository(database)


@pytest.fixture
def storage(tmp_path: Path, logger: RecordingLogger) -> LocalDirectoryStorage:
    return LocalDirectoryStorage(StorageSettings(root=tmp_path / "library"), logger)


@pytest.fixture
def renderer(tmp_path: Path) -> FakeRenderer:
    return FakeRenderer(tmp_path / "scratch")


@pytest.fixture
def failing_renderer(tmp_path: Path) -> FakeRenderer:
    return FakeRenderer(tmp_path / "scratch", error=RenderError("manim blew up"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        ai=AISettings(provider="template"),
        validation=ValidationSettings(),
        render=RenderSettings(scratch_dir=tmp_path / "scratch"),
        storage=StorageSettings(root=tmp_path / "library"),
        database=DatabaseSettings(path=tmp_path / "metadata.db"),
        logging=LoggingSettings(level="CRITICAL", format="text"),
    )


class FakeLoggerFactory:
    def __init__(self, logger: RecordingLogger) -> None:
        self._logger = logger

    def get_logger(self, name: str) -> RecordingLogger:
        return self._logger


def build_service(
    *, settings, repository, storage, renderer, logger, max_quality=Quality.HIGH
):
    """Wire the real service against fakes for the two slow/external parts."""
    from app.application.animation_service import AnimationService
    from app.application.render_pipeline import RenderPipeline
    from app.infrastructure.jobs.inline_queue import InlineJobQueue
    from app.infrastructure.validation.ast_validator import AstSceneCodeValidator

    pipeline = RenderPipeline(
        jobs=repository,
        generator=FakeGenerator(),
        validator=AstSceneCodeValidator(ValidationSettings(), logger),
        renderer=renderer,
        storage=storage,
        clock=FrozenClock(),
        logger=logger,
    )
    return AnimationService(
        jobs=repository,
        queue=InlineJobQueue(pipeline, logger),
        storage=storage,
        clock=FrozenClock(),
        ids=SequentialIds(),
        logger=logger,
        max_prompt_chars=settings.ai.max_prompt_chars,
        max_page_size=settings.max_page_size,
        max_quality=max_quality,
    )


def build_client(*, settings, service, logger, rate_limiter=None):
    from fastapi.testclient import TestClient

    from app.core.container import Container
    from app.main import create_app

    container = Container(
        settings=settings,
        logger_factory=FakeLoggerFactory(logger),
        logger=logger,
        animations=service,
        migrate=lambda: None,
        rate_limiter=rate_limiter,
    )
    return TestClient(create_app(settings, container=container))


@pytest.fixture
def client(settings, repository, storage, renderer, logger):
    service = build_service(
        settings=settings,
        repository=repository,
        storage=storage,
        renderer=renderer,
        logger=logger,
    )
    return build_client(settings=settings, service=service, logger=logger)


@pytest.fixture
def capped_service(settings, repository, storage, renderer, logger):
    """A deployment that can only afford low quality, like a 512 MB instance."""
    return build_service(
        settings=settings,
        repository=repository,
        storage=storage,
        renderer=renderer,
        logger=logger,
        max_quality=Quality.LOW,
    )


@pytest.fixture
def capped_client(settings, capped_service, logger):
    return build_client(settings=settings, service=capped_service, logger=logger)
