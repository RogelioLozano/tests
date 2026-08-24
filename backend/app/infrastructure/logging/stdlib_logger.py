"""Standard-library logging adapter.

Every call site emits `event` plus structured fields. Here they become a
`logging.LogRecord` with the fields attached, which the JSON formatter renders
as one object per line — the shape log shippers (Datadog, OTel collectors)
expect. Routing elsewhere later means registering another factory in
`app.infrastructure.logging.factory`, not editing call sites.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import LoggingSettings
from app.core.context import current_context

# Attributes every LogRecord carries; anything else was added by us and belongs
# in the structured payload.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str, environment: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "service": self._service_name,
            "env": self._environment,
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["error.stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_stringify)


class TextFormatter(logging.Formatter):
    """Human-readable output for local debugging."""

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED
        }
        suffix = " " + " ".join(f"{k}={v!r}" for k, v in sorted(extras.items())) if extras else ""
        base = (
            f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} "
            f"{record.name} {record.getMessage()}{suffix}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def _stringify(value: Any) -> str:
    return str(value)


class StdlibLogger:
    """Adapter from the `Logger` port to a `logging.Logger`."""

    __slots__ = ("_logger", "_bound")

    def __init__(self, logger: logging.Logger, bound: dict[str, Any] | None = None):
        self._logger = logger
        self._bound = bound or {}

    def bind(self, **fields: Any) -> "StdlibLogger":
        return StdlibLogger(self._logger, {**self._bound, **fields})

    def debug(self, event: str, /, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, fields)

    def info(self, event: str, /, **fields: Any) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, /, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, /, exc_info: bool = False, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields, exc_info=exc_info)

    def _emit(
        self,
        level: int,
        event: str,
        fields: dict[str, Any],
        *,
        exc_info: bool = False,
    ) -> None:
        if not self._logger.isEnabledFor(level):
            return
        # Ambient context first so an explicit field always wins.
        extra = {**current_context(), **self._bound, **fields}
        self._logger.log(level, event, extra=extra, exc_info=exc_info)


class StdlibLoggerFactory:
    """Configures the root logger once, then hands out port-shaped loggers."""

    def __init__(self, settings: LoggingSettings, environment: str) -> None:
        self._settings = settings
        formatter: logging.Formatter = (
            JsonFormatter(settings.service_name, environment)
            if settings.format == "json"
            else TextFormatter()
        )
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(formatter)

        root = logging.getLogger(settings.service_name)
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(settings.level)
        # Own the output format; do not also emit through uvicorn's root handler.
        root.propagate = False
        self._root = root

    def get_logger(self, name: str) -> StdlibLogger:
        return StdlibLogger(self._root.getChild(name))
