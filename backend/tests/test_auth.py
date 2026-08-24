"""Access-code tests.

The model is a bearer token: possession is permission, no identity involved.
Reads stay open so a portfolio visitor sees a working demo; only the action
that spends money is gated.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.auth import API_KEY_HEADER, verify
from app.core.config import RateLimitSettings, Settings
from app.infrastructure.rate_limit.factory import build_rate_limiter
from tests.conftest import RecordingLogger, build_client, build_service

SECRET = "s3cret-access-code"


@pytest.fixture
def gated_client(settings: Settings, repository, storage, renderer, logger):
    guarded = Settings(
        environment=settings.environment,
        api_key=SECRET,
        ai=settings.ai,
        validation=settings.validation,
        render=settings.render,
        storage=settings.storage,
        database=settings.database,
        logging=settings.logging,
    )
    service = build_service(
        settings=guarded,
        repository=repository,
        storage=storage,
        renderer=renderer,
        logger=logger,
    )
    limiter = build_rate_limiter(RateLimitSettings(), logger)
    return build_client(
        settings=guarded, service=service, logger=logger, rate_limiter=limiter
    )


def test_a_correct_code_is_accepted() -> None:
    assert verify(SECRET, SECRET)


def test_a_wrong_code_is_rejected() -> None:
    assert not verify("nope", SECRET)
    assert not verify(SECRET + "x", SECRET)
    assert not verify("", SECRET)


def test_a_non_ascii_code_does_not_crash_the_comparison() -> None:
    """compare_digest rejects non-ASCII str, so both sides are encoded first."""
    assert not verify("café-\u00e9", SECRET)


def test_submitting_without_a_code_is_rejected(gated_client: TestClient) -> None:
    response = gated_client.post("/api/v1/animations", json={"prompt": "a circle"})

    assert response.status_code == 401
    assert response.json()["code"] == "api_key_required"


def test_submitting_with_a_wrong_code_is_rejected(gated_client: TestClient) -> None:
    response = gated_client.post(
        "/api/v1/animations",
        json={"prompt": "a circle"},
        headers={API_KEY_HEADER: "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


def test_submitting_with_the_right_code_works(gated_client: TestClient) -> None:
    response = gated_client.post(
        "/api/v1/animations",
        json={"prompt": "a circle"},
        headers={API_KEY_HEADER: SECRET},
    )
    assert response.status_code == 202


def test_reads_stay_open(gated_client: TestClient) -> None:
    """A portfolio piece has to be visible without a code."""
    gated_client.post(
        "/api/v1/animations",
        json={"prompt": "a circle"},
        headers={API_KEY_HEADER: SECRET},
    )

    listing = gated_client.get("/api/v1/animations")
    assert listing.status_code == 200
    job_id = listing.json()["items"][0]["id"]

    assert gated_client.get(f"/api/v1/animations/{job_id}").status_code == 200
    assert gated_client.get(f"/api/v1/animations/{job_id}/source").status_code == 200
    assert gated_client.get(f"/api/v1/animations/{job_id}/video").status_code == 200
    assert gated_client.get("/api/v1/health").status_code == 200


def test_the_check_endpoint_validates_a_code(gated_client: TestClient) -> None:
    assert (
        gated_client.post(
            "/api/v1/auth/check", headers={API_KEY_HEADER: SECRET}
        ).status_code
        == 204
    )
    assert (
        gated_client.post(
            "/api/v1/auth/check", headers={API_KEY_HEADER: "wrong"}
        ).status_code
        == 401
    )


def test_capabilities_advertises_the_requirement(gated_client: TestClient) -> None:
    """So the UI knows to show the field, without learning the code itself."""
    body = gated_client.get("/api/v1/capabilities").json()
    assert body["requires_key"] is True
    assert SECRET not in str(body)


def test_an_unset_key_leaves_everything_open(client: TestClient) -> None:
    assert client.get("/api/v1/capabilities").json()["requires_key"] is False
    assert (
        client.post("/api/v1/animations", json={"prompt": "a circle"}).status_code
        == 202
    )


def test_the_key_stays_out_of_reprs() -> None:
    assert SECRET not in repr(Settings(api_key=SECRET))


def test_a_rejection_does_not_log_the_attempt(
    gated_client: TestClient, logger: RecordingLogger
) -> None:
    """Near-miss guesses are sensitive and logs get shipped elsewhere."""
    gated_client.post(
        "/api/v1/animations",
        json={"prompt": "a circle"},
        headers={API_KEY_HEADER: "almost-the-secret"},
    )

    assert "auth.rejected" in logger.names()
    assert "almost-the-secret" not in str(logger.events)
