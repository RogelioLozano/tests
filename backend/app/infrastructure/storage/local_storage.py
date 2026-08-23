"""Local-directory artifact storage.

Object-storage semantics over a directory: opaque keys, no nesting, no
traversal. Keys are validated against a strict pattern rather than merely
sanitised, so a key that came from anywhere but our own id generator is
rejected instead of quietly rewritten into some other file's path.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.config import StorageSettings
from app.domain.errors import NotFoundError, StorageError
from app.domain.models import StoredArtifact
from app.domain.ports.logging import Logger

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class LocalDirectoryStorage:
    def __init__(self, settings: StorageSettings, logger: Logger) -> None:
        self._root = Path(settings.root).resolve()
        self._logger = logger
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, source_path: str, *, content_type: str) -> StoredArtifact:
        target = self._resolve(key)
        source = Path(source_path)
        if not source.is_file():
            raise StorageError(f"Nothing to store at {source_path!r}")
        try:
            # Same-filesystem move where possible; copy+unlink across devices.
            shutil.move(str(source), target)
        except OSError as exc:
            raise StorageError(f"Could not store artifact {key!r}: {exc}") from exc

        size_bytes = target.stat().st_size
        self._logger.info(
            "storage.saved", key=key, size_bytes=size_bytes, backend="local"
        )
        return StoredArtifact(key=key, size_bytes=size_bytes, content_type=content_type)

    def open(self, key: str) -> BinaryIO:
        target = self._resolve(key)
        try:
            return target.open("rb")
        except FileNotFoundError as exc:
            raise NotFoundError(f"No stored artifact for {key!r}") from exc
        except OSError as exc:
            raise StorageError(f"Could not read artifact {key!r}: {exc}") from exc

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        target = self._resolve(key)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"Could not delete artifact {key!r}: {exc}") from exc
        self._logger.info("storage.deleted", key=key, backend="local")

    def public_url(self, key: str) -> str | None:
        # Local files are not reachable by the browser; the API streams them.
        # A cloud adapter returns a presigned URL here instead.
        return None

    def _resolve(self, key: str) -> Path:
        if not _KEY_PATTERN.fullmatch(key):
            raise StorageError(f"Invalid storage key {key!r}")
        candidate = (self._root / key).resolve()
        # Belt and braces: the pattern already excludes separators and "..".
        if candidate.parent != self._root:
            raise StorageError(f"Storage key escapes the storage root: {key!r}")
        return candidate

    def size_of(self, key: str) -> int:
        try:
            return os.path.getsize(self._resolve(key))
        except FileNotFoundError as exc:
            raise NotFoundError(f"No stored artifact for {key!r}") from exc
