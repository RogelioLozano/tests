"""Logging backend registry.

`ANIM_LOG_BACKEND` picks the implementation. Adding a hosted target later means
adding one entry here; no other module changes.
"""

from __future__ import annotations

from typing import Callable

from app.core.config import LoggingSettings
from app.domain.errors import ConfigurationError
from app.domain.ports.logging import LoggerFactory
from app.infrastructure.logging.stdlib_logger import StdlibLoggerFactory

_BACKENDS: dict[str, Callable[[LoggingSettings, str], LoggerFactory]] = {
    "stdlib": StdlibLoggerFactory,
}


def build_logger_factory(settings: LoggingSettings, environment: str) -> LoggerFactory:
    try:
        build = _BACKENDS[settings.backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown logging backend {settings.backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    return build(settings, environment)
