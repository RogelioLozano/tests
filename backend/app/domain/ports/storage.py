"""Storage port for rendered videos.

Modelled on object storage rather than a filesystem: callers address artifacts
by opaque key, so the local-directory adapter can be replaced by S3/GCS without
a call-site change.
"""

from __future__ import annotations

from typing import BinaryIO, Protocol

from app.domain.models import StoredArtifact


class ArtifactStorage(Protocol):
    def save(self, key: str, source_path: str, *, content_type: str) -> StoredArtifact:
        """Persist the file at `source_path` under `key`, replacing any existing object."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open the stored object for reading.

        Raises:
            NotFoundError: no object exists under `key`.
        """
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def public_url(self, key: str) -> str | None:
        """A directly fetchable URL, or None when the API must stream the bytes.

        A future S3 adapter returns a presigned URL here and the download route
        redirects instead of proxying; nothing else has to change.
        """
        ...
