"""Manim renderer adapter.

Rendering happens in a child process, never in the API process: a scene that
loops forever, allocates without bound, or crashes the interpreter must not be
able to take the server down with it. The child gets a scrubbed environment, a
private working directory, a hard timeout, and no shell — arguments are passed
as a list, so nothing in the generated file is ever interpreted by a shell.

The generated source has already passed static validation by the time it gets
here. Both layers are needed: validation blocks the obvious, isolation contains
what it misses.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.core.config import RenderSettings
from app.domain.errors import RenderError
from app.domain.models import Quality, RenderedScene
from app.domain.ports.logging import Logger

_QUALITY_FLAGS = {
    Quality.LOW: "l",
    Quality.MEDIUM: "m",
    Quality.HIGH: "h",
}

# Environment the child is allowed to see. Anything not listed (API keys, DB
# paths, cloud credentials) stays out of reach of the rendered scene.
_ENV_PASSTHROUGH = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE")

_MAX_LOG_OUTPUT = 2_000


class ManimCliRenderer:
    def __init__(self, settings: RenderSettings, logger: Logger) -> None:
        self._settings = settings
        self._logger = logger
        self._scratch_root = Path(settings.scratch_dir).resolve()
        self._scratch_root.mkdir(parents=True, exist_ok=True)

    def render(
        self, code: str, *, scene_name: str, quality: Quality, job_id: str
    ) -> RenderedScene:
        if not scene_name.isidentifier():
            raise RenderError(f"Invalid scene name {scene_name!r}")

        workdir = self._scratch_root / job_id
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)

        source = workdir / "scene.py"
        source.write_text(code, encoding="utf-8")
        media_dir = workdir / "media"

        command = [
            sys.executable,
            "-m",
            "manim",
            "render",
            "--quality",
            _QUALITY_FLAGS[quality],
            "--format",
            "mp4",
            "--media_dir",
            str(media_dir),
            "--disable_caching",
            str(source),
            scene_name,
        ]

        self._logger.info(
            "render.started",
            scene_name=scene_name,
            quality=quality.value,
            timeout_seconds=self._settings.timeout_seconds,
        )
        started = time.monotonic()
        try:
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command,
                cwd=workdir,
                env=self._child_env(),
                capture_output=True,
                text=True,
                timeout=self._settings.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            self._logger.error(
                "render.timeout",
                scene_name=scene_name,
                timeout_seconds=self._settings.timeout_seconds,
            )
            raise RenderError(
                f"Render exceeded {self._settings.timeout_seconds}s"
            ) from exc
        except OSError as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            raise RenderError(f"Could not start the renderer: {exc}") from exc

        render_ms = int((time.monotonic() - started) * 1000)

        if result.returncode != 0:
            detail = _tail(result.stderr or result.stdout)
            shutil.rmtree(workdir, ignore_errors=True)
            self._logger.error(
                "render.failed",
                scene_name=scene_name,
                exit_code=result.returncode,
                render_ms=render_ms,
                stderr=detail,
            )
            raise RenderError(f"Manim exited with code {result.returncode}: {detail}")

        try:
            video = self._locate_video(media_dir)
            # Lift the file out of the tree that is about to be deleted.
            output = self._scratch_root / f"{job_id}.mp4"
            output.unlink(missing_ok=True)
            shutil.move(str(video), output)
        except RenderError:
            self._logger.error("render.no_output", scene_name=scene_name)
            raise
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        size_bytes = output.stat().st_size
        self._logger.info(
            "render.completed",
            scene_name=scene_name,
            render_ms=render_ms,
            size_bytes=size_bytes,
        )
        return RenderedScene(
            path=str(output), render_ms=render_ms, size_bytes=size_bytes
        )

    def discard(self, path: str) -> None:
        candidate = Path(path).resolve()
        if candidate.parent != self._scratch_root:
            return  # Never delete outside our own scratch space.
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            self._logger.warning("render.discard_failed", path=str(candidate))

    def _child_env(self) -> dict[str, str]:
        env = {
            name: os.environ[name]
            for name in _ENV_PASSTHROUGH
            if name in os.environ
        }
        env["MPLBACKEND"] = "Agg"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def _locate_video(self, media_dir: Path) -> Path:
        videos = sorted(
            media_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not videos:
            raise RenderError("Renderer produced no video file")
        return videos[0]


def _tail(output: str | None) -> str:
    if not output:
        return ""
    return output.strip()[-_MAX_LOG_OUTPUT:]
