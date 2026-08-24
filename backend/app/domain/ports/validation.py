"""Validation port: the gate between generated source and execution."""

from __future__ import annotations

from typing import Protocol

from app.domain.models import ValidationReport


class SceneCodeValidator(Protocol):
    def validate(self, code: str, *, scene_name: str) -> ValidationReport:
        """Statically check `code` without importing or executing any of it."""
        ...
