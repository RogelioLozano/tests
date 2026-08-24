"""Rendering port."""

from __future__ import annotations

from typing import Protocol

from app.domain.models import Quality, RenderedScene


class SceneRenderer(Protocol):
    def render(
        self, code: str, *, scene_name: str, quality: Quality, job_id: str
    ) -> RenderedScene:
        """Render `code` to a video file in renderer-owned scratch space.

        The caller owns the returned file and is expected to move it into
        storage; implementations clean up anything else they created.

        Raises:
            RenderError: the render failed, timed out, or produced no file.
        """
        ...

    def discard(self, path: str) -> None:
        """Drop a previously returned render that never reached storage.

        Best effort: implementations must not raise.
        """
        ...
