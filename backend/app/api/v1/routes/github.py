"""GitHub OAuth and repository endpoints.

Three of these are *browser navigations*, not XHR: the user's address bar is
pointed at them, so they answer with redirects rather than JSON. A 401 body
would be a screen full of `{"code": ...}`. The outcome travels back to the SPA
as a query parameter instead.

`/github/repos` is the opposite — called by the page with `fetch` — so it
answers with status codes the client can branch on.

Handlers stay thin: the orchestration (exchange, identity, persist) lives in
GitHubService; what remains here is cookies, redirects, and CSRF, which are
genuinely HTTP concerns.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import ContainerDep
from app.api.oauth import (
    SESSION_COOKIE,
    STATE_COOKIE,
    clear_cookie,
    set_cookie,
    state_matches,
)
from app.api.schemas import GitHubConnectionResponse, RepositoryListResponse
from app.application.github_service import GitHubService
from app.core.container import Container
from app.core.tokens import new_session_token
from app.domain.errors import IntegrationError, NotFoundError, UnauthorizedError

router = APIRouter(tags=["github"])

# Same-origin in both environments: Vite proxies /api/v1 in development, and in
# production the container serves this API and the built SPA together. So the
# way back to the page is a plain absolute path, with nothing to configure.
FRONTEND_PATH = "/github"


@router.get("/auth/github/login", summary="Start the GitHub consent flow")
def github_login(container: ContainerDep) -> RedirectResponse:
    service = _require(container)
    settings = container.settings.github

    # Same generator as a session token: this value's only job is to be
    # unguessable by whoever might forge a callback.
    state = new_session_token()
    response = RedirectResponse(
        service.authorize_url(state=state),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    set_cookie(
        response,
        STATE_COOKIE,
        state,
        max_age=settings.state_ttl_seconds,
        secure=settings.cookie_secure,
    )
    return response


@router.get("/auth/github/callback", summary="Finish the GitHub consent flow")
def github_callback(
    request: Request,
    container: ContainerDep,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> RedirectResponse:
    service = _require(container)
    settings = container.settings.github
    logger = container.logger

    outcome, token = "failed", ""
    if error:
        # The user pressed Cancel on the consent screen. Not a fault.
        logger.info("github.consent_declined", reason=error)
        outcome = "denied"
    elif not state_matches(request.cookies.get(STATE_COOKIE, ""), state):
        # A stale tab, or a forged callback planting someone else's code on this
        # browser. Refused before the code is spent, because a successful
        # exchange would bind this session to an account the user never chose.
        logger.warning(
            "github.state_rejected", had_cookie=bool(request.cookies.get(STATE_COOKIE))
        )
        outcome = "invalid_state"
    elif not code:
        logger.warning("github.callback_without_code")
    else:
        try:
            connection = service.connect(code)
        except UnauthorizedError:
            outcome = "failed"
        except IntegrationError:
            outcome = "unavailable"
        else:
            outcome, token = "ok", connection.token

    response = RedirectResponse(
        f"{FRONTEND_PATH}?connect={outcome}", status_code=status.HTTP_303_SEE_OTHER
    )
    # Single-use by design: it has now served its purpose, or it failed and must
    # not be replayable against a second attempt.
    clear_cookie(response, STATE_COOKIE, secure=settings.cookie_secure)
    if token:
        set_cookie(
            response,
            SESSION_COOKIE,
            token,
            max_age=settings.session_ttl_seconds,
            secure=settings.cookie_secure,
        )
    return response


@router.get(
    "/auth/github/me",
    response_model=GitHubConnectionResponse,
    summary="Whether this browser has connected GitHub",
)
def github_me(request: Request, container: ContainerDep) -> GitHubConnectionResponse:
    """Never 401s: "not connected" is an answer, not a failure.

    Also reports `available`, so a deployment with no OAuth app configured can
    tell the UI to hide the tab entirely rather than offer a broken button.
    """
    if container.github is None:
        return GitHubConnectionResponse(available=False, connected=False)
    return GitHubConnectionResponse.from_domain(
        container.github.find_session(request.cookies.get(SESSION_COOKIE, ""))
    )


@router.get(
    "/github/repos",
    response_model=RepositoryListResponse,
    summary="Public repositories of the connected account",
)
def github_repositories(
    request: Request, container: ContainerDep
) -> RepositoryListResponse:
    service = _require(container)
    return RepositoryListResponse.from_domain(
        service.repositories(request.cookies.get(SESSION_COOKIE, ""))
    )


@router.post(
    "/auth/github/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget the stored GitHub token",
)
def github_logout(request: Request, container: ContainerDep) -> Response:
    service = _require(container)
    service.disconnect(request.cookies.get(SESSION_COOKIE, ""))

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_cookie(
        response, SESSION_COOKIE, secure=container.settings.github.cookie_secure
    )
    return response


def _require(container: Container) -> GitHubService:
    if container.github is None:
        raise NotFoundError(
            "GitHub sign-in is not configured on this deployment.",
            code="github_unavailable",
        )
    return container.github
