"""SQLite implementation of the render job repository.

Every statement is parameterised; no identifier or value is ever formatted into
SQL. The row/entity mapping lives here so the domain model can change shape
without a schema change leaking upward.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Sequence

from app.domain.errors import NotFoundError, RepositoryError
from app.domain.models import JobFailure, JobStatus, Quality, RenderJob
from app.infrastructure.persistence.sqlite.database import SqliteDatabase

_COLUMNS = (
    "id",
    "prompt",
    "status",
    "quality",
    "scene_name",
    "generated_code",
    "provider",
    "model",
    "artifact_key",
    "duration_ms",
    "size_bytes",
    "error_code",
    "error_message",
    "created_at",
    "updated_at",
)

_INSERT = (
    f"INSERT INTO render_jobs ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
)

_UPDATE = (
    "UPDATE render_jobs SET "
    + ", ".join(f"{column} = ?" for column in _COLUMNS if column != "id")
    + " WHERE id = ?"
)

_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM render_jobs"


class SqliteRenderJobRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    def add(self, job: RenderJob) -> None:
        with self._database.connect() as connection:
            try:
                connection.execute(_INSERT, _to_row(job))
            except sqlite3.IntegrityError as exc:
                raise RepositoryError(f"Job {job.id} already exists") from exc

    def update(self, job: RenderJob) -> None:
        values = _to_row(job)
        with self._database.connect() as connection:
            cursor = connection.execute(_UPDATE, (*values[1:], job.id))
            if cursor.rowcount == 0:
                raise NotFoundError(f"Render job {job.id} does not exist")

    def get(self, job_id: str) -> RenderJob:
        job = self.find(job_id)
        if job is None:
            raise NotFoundError(f"Render job {job_id} does not exist")
        return job

    def find(self, job_id: str) -> RenderJob | None:
        with self._database.connect() as connection:
            row = connection.execute(f"{_SELECT} WHERE id = ?", (job_id,)).fetchone()
        return _from_row(row) if row is not None else None

    def list(self, *, limit: int, offset: int = 0) -> Sequence[RenderJob]:
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{_SELECT} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def count(self) -> int:
        with self._database.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM render_jobs").fetchone()[0]


def _to_row(job: RenderJob) -> tuple[Any, ...]:
    return (
        job.id,
        job.prompt,
        job.status.value,
        job.quality.value,
        job.scene_name,
        job.generated_code,
        job.provider,
        job.model,
        job.artifact_key,
        job.duration_ms,
        job.size_bytes,
        job.failure.code if job.failure else None,
        job.failure.message if job.failure else None,
        job.created_at.isoformat(),
        job.updated_at.isoformat(),
    )


def _from_row(row: sqlite3.Row) -> RenderJob:
    failure = (
        JobFailure(code=row["error_code"], message=row["error_message"] or "")
        if row["error_code"]
        else None
    )
    return RenderJob(
        id=row["id"],
        prompt=row["prompt"],
        status=JobStatus(row["status"]),
        quality=Quality(row["quality"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        scene_name=row["scene_name"],
        generated_code=row["generated_code"],
        provider=row["provider"],
        model=row["model"],
        artifact_key=row["artifact_key"],
        duration_ms=row["duration_ms"],
        size_bytes=row["size_bytes"],
        failure=failure,
    )
