"""Version 1 of the HTTP API.

Versioning lives in the URL so a future breaking change can ship as `/api/v2`
alongside this one.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import animations, health

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(animations.router)
