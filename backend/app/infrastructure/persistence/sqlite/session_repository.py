"""SQLite implementation of the GitHub session repository.

Every statement is parameterised. Expiry is enforced in the `WHERE` clause
rather than by the caller, so a lookup that forgets to check the clock still
cannot resurrect a dead session.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.domain.errors import RepositoryError
from app.domain.models import GitHubSession
from app.infrastructure.persistence.sqlite.database import SqliteDatabase

_COLUMNS = (
    "token_hash",
    "access_token",
    "login",
    "avatar_url",
    "created_at",
    "expires_at",
)

_INSERT = (
    f"INSERT INTO github_sessions ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
)

_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM github_sessions"


class SqliteGitHubSessionRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def add(self, session: GitHubSession) -> None:
        with self._database.connect() as connection:
            try:
                connection.execute(_INSERT, _to_row(session))
            except sqlite3.IntegrityError as exc:
                # Only reachable on a token_hash collision, i.e. never in
                # practice — but a silent overwrite would hand one visitor
                # another's session, so it must not be an upsert.
                raise RepositoryError("That session already exists") from exc

    def find(self, token_hash: str, *, now: datetime) -> GitHubSession | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{_SELECT} WHERE token_hash = ? AND expires_at > ?",
                (token_hash, now.isoformat()),
            ).fetchone()
        return _from_row(row) if row is not None else None

    def delete(self, token_hash: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM github_sessions WHERE token_hash = ?", (token_hash,)
            )

    def purge_expired(self, *, now: datetime) -> int:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM github_sessions WHERE expires_at <= ?",
                (now.isoformat(),),
            )
            return cursor.rowcount


def _to_row(session: GitHubSession) -> tuple[Any, ...]:
    # Timestamps are compared as text, which is only sound because every one of
    # them comes from the clock as UTC and so shares an offset suffix.
    return (
        session.token_hash,
        session.access_token,
        session.login,
        session.avatar_url,
        session.created_at.isoformat(),
        session.expires_at.isoformat(),
    )


def _from_row(row: sqlite3.Row) -> GitHubSession:
    return GitHubSession(
        token_hash=row["token_hash"],
        access_token=row["access_token"],
        login=row["login"],
        avatar_url=row["avatar_url"],
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )
