"""Logging port.

Call sites emit an event name plus structured fields, never a preformatted
string. That is what lets the backend swap the stdlib adapter for a Datadog (or
OpenTelemetry) one without touching a single log statement.
"""

from __future__ import annotations

from typing import Any, Protocol


class Logger(Protocol):
    def debug(self, event: str, /, **fields: Any) -> None: ...

    def info(self, event: str, /, **fields: Any) -> None: ...

    def warning(self, event: str, /, **fields: Any) -> None: ...

    def error(self, event: str, /, exc_info: bool = False, **fields: Any) -> None: ...

    def bind(self, **fields: Any) -> "Logger":
        """Return a logger that adds `fields` to every record it emits."""
        ...


class LoggerFactory(Protocol):
    def get_logger(self, name: str) -> Logger: ...
