"""Ambient request context.

A context variable carries the correlation id from the HTTP middleware into
every log record without threading an argument through the service layer.
Reads are safe anywhere; writes belong to the middleware and the job runner.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


def current_context() -> dict[str, Any]:
    return dict(_context.get())


def request_id() -> str | None:
    return _context.get().get("request_id")


@contextmanager
def bound_context(**fields: Any) -> Iterator[None]:
    """Add `fields` to the ambient context for the duration of the block."""
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)
