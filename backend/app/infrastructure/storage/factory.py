"""Storage registry."""

from __future__ import annotations

from typing import Callable

from app.core.config import StorageSettings
from app.domain.errors import ConfigurationError
from app.domain.ports.logging import Logger
from app.domain.ports.storage import ArtifactStorage
from app.infrastructure.storage.local_storage import LocalDirectoryStorage

_BACKENDS: dict[str, Callable[[StorageSettings, Logger], ArtifactStorage]] = {
    "local": LocalDirectoryStorage,
}


def build_storage(settings: StorageSettings, logger: Logger) -> ArtifactStorage:
    try:
        build = _BACKENDS[settings.backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown storage backend {settings.backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    return build(settings, logger)
