"""Serving the built frontend from the API process.

Only mounted when `ANIM_STATIC_DIR` is set, which is the containerised case:
one image, one service, no separate static host or CORS hop. In development the
Vite dev server does this instead and the mount stays off.

The catch-all exists because the Vue router owns paths like `/animations` that
have no file behind them; a request for a *missing asset* still has to 404
rather than silently return HTML.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.domain.ports.logging import Logger


def mount_frontend(app: FastAPI, static_dir: Path, logger: Logger) -> None:
    index = static_dir / "index.html"
    if not index.is_file():
        logger.warning("static.missing", path=str(static_dir))
        return

    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount(
            "/assets", StaticFiles(directory=assets), name="assets"
        )

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (static_dir / path).resolve()
        if (
            path
            and static_dir in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        if "." in Path(path).name:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(index)

    logger.info("static.mounted", path=str(static_dir))
