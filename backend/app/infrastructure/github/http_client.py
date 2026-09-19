"""HTTP client for github.com.

The only module that knows GitHub's URLs, wire format, and quirks. Failures are
translated into domain errors here, so nothing above ever handles an
`httpx.HTTPError` or reads a status code.

Two quirks drive most of the shape of this file:

1. The token endpoint answers a *rejected* code with HTTP 200 and an error in
   the body. Trusting the status line would treat a forged code as a login.
2. `Accept` decides the response format. Without it the token endpoint replies
   form-encoded and `.json()` fails.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence
from urllib.parse import quote, urlencode

import httpx

from app.core.config import GitHubSettings
from app.domain.errors import IntegrationError, UnauthorizedError
from app.domain.models import GitHubIdentity, Repository
from app.domain.ports.logging import Logger

_API_VERSION = "2022-11-28"
# One page is plenty for a profile page, and it keeps the response bounded no
# matter how many repositories the visitor owns.
_PAGE_SIZE = 100


class HttpGitHubClient:
    def __init__(
        self,
        settings: GitHubSettings,
        logger: Logger,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger
        # Injected only by tests; in production each call opens and closes its
        # own client, so there is no connection state to manage at shutdown.
        self._client = client

    def authorize_url(self, *, state: str) -> str:
        params = {
            "client_id": self._settings.client_id,
            "redirect_uri": self._settings.redirect_uri,
            "state": state,
        }
        # Omitted entirely when empty: GitHub reads an absent scope as "public
        # data only", which is exactly what this feature wants.
        if self._settings.scopes:
            params["scope"] = " ".join(self._settings.scopes)
        return f"{self._settings.authorize_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        payload = self._send(
            "POST",
            self._settings.token_url,
            headers={"Accept": "application/json"},
            data={
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret,
                "code": code,
                # Checked a second time here: GitHub confirms the code was
                # issued for this same URL, not merely for a registered one.
                "redirect_uri": self._settings.redirect_uri,
            },
        )
        if not isinstance(payload, dict):
            raise IntegrationError("GitHub returned an unexpected token response")

        if payload.get("error"):
            # GitHub's own description is logged but never echoed back: it is
            # attacker-influenced text, and the user can act on none of it.
            self._logger.warning(
                "github.exchange_rejected", reason=str(payload.get("error"))
            )
            raise UnauthorizedError(
                "GitHub would not complete that sign-in. Please try again.",
                code="github_exchange_failed",
            )

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise IntegrationError("GitHub returned no access token")
        self._logger.info("github.exchange_succeeded")
        return token

    def fetch_identity(self, token: str) -> GitHubIdentity:
        payload = self._send("GET", self._url("/user"), headers=self._headers(token))
        if not isinstance(payload, dict) or not payload.get("login"):
            raise IntegrationError("GitHub returned an account with no login")
        return GitHubIdentity(
            login=str(payload["login"]),
            avatar_url=_text(payload.get("avatar_url")),
        )

    def list_public_repositories(
        self, login: str, *, token: str
    ) -> Sequence[Repository]:
        # /users/{login}/repos, not /user/repos: this endpoint returns public
        # repositories by construction, so no scope could ever widen it. The
        # token rides along only to buy the authenticated rate limit.
        payload = self._send(
            "GET",
            self._url(f"/users/{quote(login, safe='')}/repos"),
            headers=self._headers(token),
            params={
                "type": "owner",
                "sort": "pushed",
                "direction": "desc",
                "per_page": _PAGE_SIZE,
            },
        )
        if not isinstance(payload, list):
            raise IntegrationError("GitHub returned an unexpected repository list")

        repositories = tuple(
            _to_repository(item) for item in payload if isinstance(item, dict)
        )
        self._logger.info(
            "github.repositories_listed", login=login, count=len(repositories)
        )
        return repositories

    def _url(self, path: str) -> str:
        return f"{self._settings.api_base_url.rstrip('/')}{path}"

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "Authorization": f"Bearer {token}",
        }

    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
    ) -> Any:
        try:
            if self._client is not None:
                response = self._client.request(
                    method, url, headers=headers, params=params, data=data
                )
            else:
                with httpx.Client(timeout=self._settings.timeout_seconds) as client:
                    response = client.request(
                        method, url, headers=headers, params=params, data=data
                    )
        except httpx.TimeoutException as exc:
            raise IntegrationError(
                f"GitHub did not respond within {self._settings.timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            # Deliberately does not interpolate the exception: httpx embeds the
            # request in it, and the token request body holds the client secret.
            self._logger.error(
                "github.transport_error", error_type=type(exc).__name__
            )
            raise IntegrationError("Could not reach GitHub") from exc

        if response.status_code in (401, 403):
            self._logger.warning(
                "github.access_refused", status_code=response.status_code
            )
            raise UnauthorizedError(
                "GitHub refused this access. Please connect again.",
                code="github_unauthorized",
            )
        if response.status_code >= 400:
            self._logger.error(
                "github.error_response", status_code=response.status_code
            )
            raise IntegrationError(f"GitHub replied {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationError("GitHub returned a malformed response") from exc


def _to_repository(item: dict[str, Any]) -> Repository:
    return Repository(
        name=_text(item.get("name")) or "",
        full_name=_text(item.get("full_name")) or "",
        url=_text(item.get("html_url")) or "",
        description=_text(item.get("description")),
        language=_text(item.get("language")),
        stars=_count(item.get("stargazers_count")),
        forks=_count(item.get("forks_count")),
        pushed_at=_timestamp(item.get("pushed_at")),
        is_fork=bool(item.get("fork")),
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
