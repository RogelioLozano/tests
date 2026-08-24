"""Renderer registry."""

from __future__ import annotations

from typing import Callable

from app.core.config import RenderSettings
from app.domain.errors import ConfigurationError
from app.domain.ports.logging import Logger
from app.domain.ports.rendering import SceneRenderer
from app.infrastructure.rendering.manim_renderer import ManimCliRenderer

_BACKENDS: dict[str, Callable[[RenderSettings, Logger], SceneRenderer]] = {
    "manim": ManimCliRenderer,
}


def build_renderer(settings: RenderSettings, logger: Logger) -> SceneRenderer:
    try:
        build = _BACKENDS[settings.backend]
    except KeyError:
        raise ConfigurationError(
            f"Unknown render backend {settings.backend!r}; "
            f"available: {', '.join(sorted(_BACKENDS))}"
        ) from None
    return build(settings, logger)
