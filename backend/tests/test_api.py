"""API contract tests.

The container is assembled by hand with a fake renderer, which is the payoff of
the port design: the whole HTTP path is exercised without Manim, without a
network, and in milliseconds.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.middleware import REQUEST_ID_HEADER
from app.domain.models import JobStatus
from tests.conftest import RecordingLogger


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submitting_a_prompt_returns_a_job(client: TestClient) -> None:
    response = client.post("/api/v1/animations", json={"prompt": "draw a circle"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == JobStatus.SUCCEEDED.value
    assert body["video_url"] == f"/api/v1/animations/{body['id']}/video"
    assert body["prompt"] == "draw a circle"


def test_the_job_can_be_polled(client: TestClient) -> None:
    """Clients poll even though the queue is inline, so moving to a worker is
    invisible to them."""
    job_id = client.post("/api/v1/animations", json={"prompt": "a circle"}).json()["id"]

    response = client.get(f"/api/v1/animations/{job_id}")
    assert response.status_code == 200
    assert response.json()["id"] == job_id


def test_the_video_is_served(client: TestClient) -> None:
    job_id = client.post("/api/v1/animations", json={"prompt": "a circle"}).json()["id"]

    response = client.get(f"/api/v1/animations/{job_id}/video")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == b"fake-mp4-bytes"


def test_the_generated_source_is_readable(client: TestClient) -> None:
    job_id = client.post("/api/v1/animations", json={"prompt": "a circle"}).json()["id"]

    body = client.get(f"/api/v1/animations/{job_id}/source").json()
    assert "class" in body["code"]
    assert body["scene_name"].startswith("Scene_")


def test_listing_is_paged(client: TestClient) -> None:
    for index in range(3):
        client.post("/api/v1/animations", json={"prompt": f"circle {index}"})

    body = client.get("/api/v1/animations", params={"limit": 2}).json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2


def test_an_unknown_job_is_a_404_with_an_error_code(client: TestClient) -> None:
    response = client.get("/api/v1/animations/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_an_empty_prompt_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/animations", json={"prompt": "   "})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_unknown_fields_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/animations", json={"prompt": "a circle", "callback_url": "http://x"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers[REQUEST_ID_HEADER]


def test_a_malformed_inbound_request_id_is_replaced(client: TestClient) -> None:
    """The header reaches log records, so it is never echoed unvalidated."""
    injected = "abc\nlevel=CRITICAL event=owned"
    response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: injected})
    assert response.headers[REQUEST_ID_HEADER] != injected


def test_requests_are_logged(client: TestClient, logger: RecordingLogger) -> None:
    client.post("/api/v1/animations", json={"prompt": "a circle"})
    events = logger.names()
    assert "request.received" in events
    assert "prompt.received" in events
    assert "request.completed" in events
