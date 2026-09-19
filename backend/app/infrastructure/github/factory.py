"""GitHub client registry.

Returns None when no OAuth app is configured, which is what lets the rest of
the application treat the feature as absent rather than broken.
"""

from __future__ import annotations

from app.core.config import GitHubSettings
from app.domain.ports.github import GitHubClient
from app.domain.ports.logging import Logger
from app.infrastructure.github.http_client import HttpGitHubClient


def build_github_client(
    settings: GitHubSettings, logger: Logger
) -> GitHubClient | None:
    if not settings.enabled:
        logger.info("github.disabled")
        return None
    logger.info("github.enabled", redirect_uri=settings.redirect_uri)
    return HttpGitHubClient(settings, logger)
