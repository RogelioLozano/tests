"""SQLite connection handling and schema migration.

A connection is opened per unit of work rather than shared: FastAPI runs
blocking handlers in a thread pool, and SQLite connections are not safe to pass
between threads. WAL mode lets a reader run while the render pipeline writes.

Schema version lives in `PRAGMA user_version`, so migrations are ordered,
idempotent, and need no extra bookkeeping table.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import DatabaseSettings
from app.domain.errors import RepositoryError
from app.domain.ports.logging import Logger

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        """
        CREATE TABLE IF NOT EXISTS render_jobs (
            id             TEXT PRIMARY KEY,
            prompt         TEXT NOT NULL,
            status         TEXT NOT NULL,
            quality        TEXT NOT NULL,
            scene_name     TEXT,
            generated_code TEXT,
            provider       TEXT,
            model          TEXT,
            artifact_key   TEXT,
            duration_ms    INTEGER,
            size_bytes     INTEGER,
            error_code     TEXT,
            error_message  TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_render_jobs_created_at "
        "ON render_jobs (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_render_jobs_status ON render_jobs (status)",
    ),
)


class SqliteDatabase:
    def __init__(self, settings: DatabaseSettings, logger: Logger) -> None:
        self._path = Path(settings.path)
        self._timeout = settings.timeout_seconds
        self._logger = logger
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside a transaction, committing on clean exit."""
        try:
            connection = sqlite3.connect(
                self._path, timeout=self._timeout, isolation_level=None
            )
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not open the database: {exc}") from exc

        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = %d" % int(self._timeout * 1000))
            connection.execute("BEGIN")
            yield connection
        except sqlite3.Error as exc:
            connection.rollback()
            raise RepositoryError(f"Database operation failed: {exc}") from exc
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as connection:
            current = connection.execute("PRAGMA user_version").fetchone()[0]
            for version, statements in enumerate(MIGRATIONS, start=1):
                if version <= current:
                    continue
                for statement in statements:
                    connection.execute(statement)
                # PRAGMA does not accept bound parameters; the value is an int
                # derived from the migration list, never from input.
                connection.execute(f"PRAGMA user_version = {version:d}")
                self._logger.info("database.migrated", version=version)
            self._logger.info(
                "database.ready", path=str(self._path), version=len(MIGRATIONS)
            )
