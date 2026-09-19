"""GitHub OAuth endpoint tests.

Exercised through the real app with a stub GitHub client, so cookies, redirects
and CSRF go through Starlette exactly as they would in a browser.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.api.oauth import SESSION_COOKIE, STATE_COOKIE
from app.application.github_service import GitHubService
from app.core.config import GitHubSettings, Settings
from app.core.container import Container
from app.domain.errors import IntegrationError, UnauthorizedError
from app.domain.models import GitHubIdentity, Repository
from tests.conftest import FakeLoggerFactory, RecordingLogger

REDIRECT = "http://localhost:5100/api/v1/auth/github/callback"


class StubGitHub:
    """Stands in for github.com at the port boundary."""

    def __init__(self, *, exchange_error: Exception | None = None) -> None:
        self.exchange_error = exchange_error
        self.exchanged: list[str] = []
        self.repositories = (
            Repository(
                name="manim-studio",
                full_name="octocat/manim-studio",
                url="https://github.com/octocat/manim-studio",
                stars=7,
            ),
        )

    def authorize_url(self, *, state: str) -> str:
        return f"https://github.com/login/oauth/authorize?client_id=x&state={state}"

    def exchange_code(self, code: str) -> str:
        if self.exchange_error is not None:
            raise self.exchange_error
        self.exchanged.append(code)
        return "gho_access_token"

    def fetch_identity(self, token: str) -> GitHubIdentity:
        return GitHubIdentity(login="octocat", avatar_url="https://a/1.png")

    def list_public_repositories(self, login: str, *, token: str):
        return self.repositories


class FixedClock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.moment


@pytest.fixture
def github():
    return StubGitHub()


@pytest.fixture
def clock():
    return FixedClock()


@pytest.fixture
def github_client(settings: Settings, sessions, logger, github, clock) -> TestClient:
    from app.main import create_app

    configured = Settings(
        environment="test",
        ai=settings.ai,
        validation=settings.validation,
        render=settings.render,
        storage=settings.storage,
        database=settings.database,
        logging=settings.logging,
        github=GitHubSettings(
            client_id="Ov23liTEST",
            client_secret="shh",
            redirect_uri=REDIRECT,
            session_ttl_seconds=3600,
        ),
    )
    container = Container(
        settings=configured,
        logger_factory=FakeLoggerFactory(logger),
        logger=logger,
        animations=None,
        migrate=lambda: None,
        github=GitHubService(
            client=github,
            sessions=sessions,
            clock=clock,
            logger=logger,
            session_ttl_seconds=3600,
        ),
    )
    return TestClient(create_app(configured, container=container), follow_redirects=False)


def start_login(client: TestClient) -> str:
    """Run the login leg and return the state the server minted."""
    response = client.get("/api/v1/auth/github/login")
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def connect(client: TestClient) -> None:
    state = start_login(client)
    client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")


# --- login -----------------------------------------------------------------


def test_login_redirects_to_github(github_client: TestClient) -> None:
    response = github_client.get("/api/v1/auth/github/login")

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://github.com/login/oauth/")


def test_login_sets_an_httponly_state_cookie(github_client: TestClient) -> None:
    response = github_client.get("/api/v1/auth/github/login")
    header = response.headers["set-cookie"]

    assert STATE_COOKIE in header
    assert "HttpOnly" in header
    assert "samesite=lax" in header.lower()


def test_each_login_mints_a_fresh_state(github_client: TestClient) -> None:
    assert start_login(github_client) != start_login(github_client)


# --- callback --------------------------------------------------------------


def test_callback_opens_a_session(github_client: TestClient, github) -> None:
    state = start_login(github_client)
    response = github_client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")

    assert response.status_code == 303
    assert response.headers["location"] == "/github?connect=ok"
    assert github.exchanged == ["abc"]
    assert github_client.cookies.get(SESSION_COOKIE)


def test_the_session_cookie_is_not_readable_by_script(
    github_client: TestClient,
) -> None:
    state = start_login(github_client)
    response = github_client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")

    session_cookie = [
        value
        for key, value in response.headers.items()
        if key.lower() == "set-cookie" and SESSION_COOKIE in value
    ][0]
    assert "HttpOnly" in session_cookie


def test_the_github_token_never_reaches_the_browser(
    github_client: TestClient,
) -> None:
    state = start_login(github_client)
    response = github_client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")

    assert "gho_access_token" not in str(response.headers)
    assert "gho_access_token" not in response.text


def test_a_forged_callback_is_refused(github_client: TestClient, github) -> None:
    """No state cookie at all: nobody started this flow in this browser."""
    response = github_client.get("/api/v1/auth/github/callback?code=stolen&state=made-up")

    assert response.headers["location"] == "/github?connect=invalid_state"
    assert github.exchanged == []
    assert not github_client.cookies.get(SESSION_COOKIE)


def test_a_mismatched_state_is_refused_before_the_code_is_spent(
    github_client: TestClient, github
) -> None:
    start_login(github_client)
    response = github_client.get(
        "/api/v1/auth/github/callback?code=abc&state=not-the-one"
    )

    assert response.headers["location"] == "/github?connect=invalid_state"
    assert github.exchanged == []


def test_the_state_cookie_is_single_use(github_client: TestClient) -> None:
    state = start_login(github_client)
    github_client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")

    replayed = github_client.get(
        f"/api/v1/auth/github/callback?code=abc&state={state}"
    )
    assert replayed.headers["location"] == "/github?connect=invalid_state"


def test_declining_consent_is_reported_not_crashed(github_client: TestClient) -> None:
    response = github_client.get("/api/v1/auth/github/callback?error=access_denied")
    assert response.headers["location"] == "/github?connect=denied"


def test_a_rejected_code_sends_the_user_back_with_a_reason(
    settings, sessions, logger, clock
) -> None:
    client = _client_with(
        settings, sessions, logger, clock, StubGitHub(exchange_error=UnauthorizedError("no"))
    )
    state = start_login(client)
    response = client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")

    assert response.headers["location"] == "/github?connect=failed"
    assert not client.cookies.get(SESSION_COOKIE)


def test_github_being_down_is_distinguished_from_being_refused(
    settings, sessions, logger, clock
) -> None:
    client = _client_with(
        settings, sessions, logger, clock, StubGitHub(exchange_error=IntegrationError("down"))
    )
    state = start_login(client)
    response = client.get(f"/api/v1/auth/github/callback?code=abc&state={state}")

    assert response.headers["location"] == "/github?connect=unavailable"


# --- me, repos, logout -----------------------------------------------------


def test_me_reports_disconnected_without_failing(github_client: TestClient) -> None:
    response = github_client.get("/api/v1/auth/github/me")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "connected": False,
        "login": None,
        "avatar_url": None,
        "expires_at": None,
    }


def test_me_reports_the_connected_account(github_client: TestClient) -> None:
    connect(github_client)
    body = github_client.get("/api/v1/auth/github/me").json()

    assert body["connected"] is True
    assert body["login"] == "octocat"


def test_repos_require_a_session(github_client: TestClient) -> None:
    response = github_client.get("/api/v1/github/repos")

    assert response.status_code == 401
    assert response.json()["code"] == "github_not_connected"


def test_repos_are_listed_once_connected(github_client: TestClient) -> None:
    connect(github_client)
    body = github_client.get("/api/v1/github/repos").json()

    assert body["total"] == 1
    assert body["items"][0]["full_name"] == "octocat/manim-studio"
    assert body["items"][0]["stars"] == 7


def test_logout_ends_the_session(github_client: TestClient) -> None:
    connect(github_client)
    assert github_client.post("/api/v1/auth/github/logout").status_code == 204

    assert github_client.get("/api/v1/github/repos").status_code == 401
    assert github_client.get("/api/v1/auth/github/me").json()["connected"] is False


def test_an_expired_session_stops_working(github_client: TestClient, clock) -> None:
    connect(github_client)
    clock.moment += timedelta(hours=2)

    assert github_client.get("/api/v1/github/repos").status_code == 401
    assert github_client.get("/api/v1/auth/github/me").json()["connected"] is False


# --- the feature switched off ----------------------------------------------


def test_me_says_unavailable_when_no_oauth_app_is_configured(client) -> None:
    """The default test app has no GitHub credentials."""
    body = client.get("/api/v1/auth/github/me").json()
    assert body == {
        "available": False,
        "connected": False,
        "login": None,
        "avatar_url": None,
        "expires_at": None,
    }


def test_the_other_routes_are_absent_when_unconfigured(client) -> None:
    assert client.get("/api/v1/auth/github/login").status_code == 404
    assert client.get("/api/v1/github/repos").status_code == 404


def _client_with(settings, sessions, logger, clock, github) -> TestClient:
    from app.main import create_app

    configured = Settings(
        environment="test",
        ai=settings.ai,
        validation=settings.validation,
        render=settings.render,
        storage=settings.storage,
        database=settings.database,
        logging=settings.logging,
        github=GitHubSettings(
            client_id="Ov23liTEST", client_secret="shh", redirect_uri=REDIRECT
        ),
    )
    container = Container(
        settings=configured,
        logger_factory=FakeLoggerFactory(logger),
        logger=logger,
        animations=None,
        migrate=lambda: None,
        github=GitHubService(
            client=github,
            sessions=sessions,
            clock=clock,
            logger=logger,
            session_ttl_seconds=3600,
        ),
    )
    return TestClient(create_app(configured, container=container), follow_redirects=False)
