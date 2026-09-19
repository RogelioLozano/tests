"""GitHub adapter tests.

`httpx.MockTransport` stands in for github.com, so the whole request/response
path is exercised — headers, body, error mapping, field mapping — without a
network call or a real credential.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.config import GitHubSettings
from app.domain.errors import IntegrationError, UnauthorizedError
from app.infrastructure.github.factory import build_github_client
from app.infrastructure.github.http_client import HttpGitHubClient
from tests.conftest import RecordingLogger

SECRET = "super-secret-client-secret"
REDIRECT = "http://localhost:5100/api/v1/auth/github/callback"


def settings_for(**overrides) -> GitHubSettings:
    return GitHubSettings(
        client_id="Ov23liTEST",
        client_secret=SECRET,
        redirect_uri=REDIRECT,
        **overrides,
    )


def client_for(handler, logger: RecordingLogger, **overrides) -> HttpGitHubClient:
    return HttpGitHubClient(
        settings_for(**overrides),
        logger,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def json_handler(payload, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.request = request
        return httpx.Response(status_code, json=payload)

    handler.request = None
    return handler


# --- the consent URL -------------------------------------------------------


def test_authorize_url_carries_the_public_parameters(logger) -> None:
    url = client_for(json_handler({}), logger).authorize_url(state="xyz")
    query = parse_qs(urlparse(url).query)

    assert query["client_id"] == ["Ov23liTEST"]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["state"] == ["xyz"]


def test_authorize_url_never_carries_the_secret(logger) -> None:
    """It ends up in the user's address bar, so this is load-bearing."""
    assert SECRET not in client_for(json_handler({}), logger).authorize_url(state="x")


def test_scope_is_omitted_when_empty(logger) -> None:
    """An absent scope is how GitHub is told 'public data only'."""
    url = client_for(json_handler({}), logger).authorize_url(state="x")
    assert "scope" not in parse_qs(urlparse(url).query)


def test_scope_is_space_delimited_when_set(logger) -> None:
    url = client_for(
        json_handler({}), logger, scopes=("read:user", "user:email")
    ).authorize_url(state="x")
    assert parse_qs(urlparse(url).query)["scope"] == ["read:user user:email"]


# --- the token exchange ----------------------------------------------------


def test_exchange_returns_the_token(logger) -> None:
    handler = json_handler({"access_token": "gho_abc", "token_type": "bearer"})
    assert client_for(handler, logger).exchange_code("code-1") == "gho_abc"


def test_exchange_sends_the_secret_in_the_body_not_the_url(logger) -> None:
    handler = json_handler({"access_token": "gho_abc"})
    client_for(handler, logger).exchange_code("code-1")

    assert SECRET not in str(handler.request.url)
    body = parse_qs(handler.request.content.decode())
    assert body["client_secret"] == [SECRET]
    assert body["code"] == ["code-1"]
    assert body["redirect_uri"] == [REDIRECT]


def test_exchange_asks_for_json(logger) -> None:
    """Without this GitHub answers form-encoded and parsing fails."""
    handler = json_handler({"access_token": "gho_abc"})
    client_for(handler, logger).exchange_code("code-1")
    assert handler.request.headers["Accept"] == "application/json"


def test_a_rejected_code_is_unauthorized_despite_http_200(logger) -> None:
    """GitHub reports a bad code with a 200 and an error body.

    Trusting the status line here would accept a forged code as a login.
    """
    handler = json_handler(
        {
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect or expired.",
        }
    )

    with pytest.raises(UnauthorizedError):
        client_for(handler, logger).exchange_code("forged")


def test_a_rejected_code_does_not_echo_githubs_description(logger) -> None:
    handler = json_handler(
        {"error": "bad_verification_code", "error_description": "<script>oops</script>"}
    )

    with pytest.raises(UnauthorizedError) as caught:
        client_for(handler, logger).exchange_code("forged")
    assert "script" not in caught.value.message


def test_exchange_without_a_token_is_an_integration_error(logger) -> None:
    with pytest.raises(IntegrationError):
        client_for(json_handler({"token_type": "bearer"}), logger).exchange_code("c")


# --- identity and repositories ---------------------------------------------


def test_fetch_identity_maps_the_profile(logger) -> None:
    handler = json_handler({"login": "octocat", "avatar_url": "https://a/1.png"})
    identity = client_for(handler, logger).fetch_identity("gho_abc")

    assert identity.login == "octocat"
    assert identity.avatar_url == "https://a/1.png"
    assert handler.request.headers["Authorization"] == "Bearer gho_abc"


def test_repositories_come_from_the_public_endpoint(logger) -> None:
    """/users/{login}/repos cannot return private data whatever the scope."""
    handler = json_handler([])
    client_for(handler, logger).list_public_repositories("octocat", token="gho_abc")

    assert handler.request.url.path == "/users/octocat/repos"
    assert parse_qs(handler.request.url.query.decode())["sort"] == ["pushed"]


def test_a_login_is_url_encoded_into_the_path(logger) -> None:
    """Without the escaping httpx normalises `a/../b` away to `/users/b/repos`,
    quietly querying a different account than the one asked for."""
    handler = json_handler([])
    client_for(handler, logger).list_public_repositories("a/../b", token="t")
    sent = handler.request.url.raw_path.split(b"?")[0]
    assert sent == b"/users/a%2F..%2Fb/repos"


def test_repositories_are_mapped_off_githubs_wire_format(logger) -> None:
    handler = json_handler(
        [
            {
                "name": "manim-studio",
                "full_name": "octocat/manim-studio",
                "html_url": "https://github.com/octocat/manim-studio",
                "description": "renders things",
                "language": "Python",
                "stargazers_count": 12,
                "forks_count": 3,
                "pushed_at": "2026-01-02T03:04:05Z",
                "fork": False,
                "private": False,
            }
        ]
    )

    repo = client_for(handler, logger).list_public_repositories("octocat", token="t")[0]
    assert repo.name == "manim-studio"
    assert repo.url == "https://github.com/octocat/manim-studio"
    assert repo.stars == 12
    assert repo.forks == 3
    assert repo.pushed_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_missing_and_null_fields_do_not_break_the_mapping(logger) -> None:
    handler = json_handler([{"name": "bare", "description": None, "language": None}])
    repo = client_for(handler, logger).list_public_repositories("octocat", token="t")[0]

    assert repo.description is None
    assert repo.stars == 0
    assert repo.pushed_at is None


# --- failure translation ---------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403])
def test_a_refused_token_is_unauthorized(logger, status_code: int) -> None:
    handler = json_handler({"message": "Bad credentials"}, status_code)
    with pytest.raises(UnauthorizedError):
        client_for(handler, logger).fetch_identity("stale")


@pytest.mark.parametrize("status_code", [418, 500, 503])
def test_other_failures_are_integration_errors(logger, status_code: int) -> None:
    """Not the user's fault, so not a 401 telling them to reconnect."""
    handler = json_handler({"message": "nope"}, status_code)
    with pytest.raises(IntegrationError):
        client_for(handler, logger).fetch_identity("gho_abc")


def test_a_timeout_is_an_integration_error(logger) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow", request=request)

    with pytest.raises(IntegrationError):
        client_for(handler, logger).fetch_identity("gho_abc")


def test_a_transport_failure_never_logs_the_secret(logger: RecordingLogger) -> None:
    """httpx puts the whole request in the exception, secret body included."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(IntegrationError):
        client_for(handler, logger).exchange_code("code-1")

    assert SECRET not in repr(logger.events)


def test_malformed_json_is_an_integration_error(logger) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with pytest.raises(IntegrationError):
        client_for(handler, logger).fetch_identity("gho_abc")


# --- the factory -----------------------------------------------------------


def test_the_feature_is_absent_without_credentials(logger) -> None:
    assert build_github_client(GitHubSettings(), logger) is None


def test_the_client_is_built_when_configured(logger) -> None:
    assert build_github_client(settings_for(), logger) is not None
