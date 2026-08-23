"""Ambient-dependency ports.

Time and identity are injected so the service layer stays deterministic under
test and free of hidden global state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware current time."""
        ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...
