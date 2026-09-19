"""Persistence registry.

Returns the repository together with an `initialise` hook so the composition
root can migrate at startup without knowing that SQLite is what is underneath.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.config import DatabaseSettings
from app.domain.errors import ConfigurationError
from app.domain.ports.logging import Logger
from app.domain.ports.repository import GitHubSessionRepository, RenderJobRepository
from app.infrastructure.persistence.sqlite.database import SqliteDatabase
from app.infrastructure.persistence.sqlite.job_repository import (
    SqliteRenderJobRepository,
)
from app.infrastructure.persistence.sqlite.session_repository import (
    SqliteGitHubSessionRepository,
)


@dataclass(frozen=True, slots=True)
class Persistence:
    jobs: RenderJobRepository
    github_sessions: GitHubSessionRepository
    initialise: Callable[[], None]


def _build_sqlite(settings: DatabaseSettings, logger: Logger) -> Persistence:
    database = SqliteDatabase(settings, logger)
    return Persistence(
        jobs=SqliteRenderJobRepository(database),
        github_sessions=SqliteGitHubSessionRepository(database),
        initialise=database.migrate,
    )


_BACKENDS: dict[str, Callable[[DatabaseSettings, Logger], Persistence]] = {
    "sqlite": _build_sqlite,
}


def build_persistence(settings: DatabaseSettings, logger: Logger) -> Persistence:
    try:
        build = _BACKENDS[settings.backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown database backend {settings.backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    return build(settings, logger)
