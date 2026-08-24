"""Quality ceiling tests.

Peak memory scales sharply with quality (~217/388/981 MB), so on a small
instance the top of the range is not "slow", it is an OOM kill that takes the
whole service down. The ceiling has to be refused up front, and the UI has to
be told what it is rather than hard-coding a list.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.errors import ValidationError
from app.domain.models import Quality


def test_quality_is_ordered() -> None:
    assert Quality.LOW.rank < Quality.MEDIUM.rank < Quality.HIGH.rank
    assert Quality.HIGH.exceeds(Quality.LOW)
    assert not Quality.LOW.exceeds(Quality.LOW)


@pytest.mark.parametrize(
    ("ceiling", "expected"),
    [
        (Quality.LOW, ("low",)),
        (Quality.MEDIUM, ("low", "medium")),
        (Quality.HIGH, ("low", "medium", "high")),
    ],
)
def test_up_to_lists_affordable_qualities(ceiling: Quality, expected) -> None:
    assert tuple(q.value for q in Quality.up_to(ceiling)) == expected


def test_capabilities_reports_the_ceiling(client: TestClient) -> None:
    body = client.get("/api/v1/capabilities").json()
    assert body["qualities"] == ["low", "medium", "high"]
    assert body["default_quality"] == "low"
    assert body["max_prompt_chars"] == 1000


def test_a_capped_server_offers_less(capped_client: TestClient) -> None:
    body = capped_client.get("/api/v1/capabilities").json()
    assert body["qualities"] == ["low"]


def test_a_capped_server_refuses_a_too_high_quality(capped_client: TestClient) -> None:
    response = capped_client.post(
        "/api/v1/animations", json={"prompt": "a circle", "quality": "high"}
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "validation_error"
    assert "maximum is 'low'" in body["message"]


def test_a_capped_server_still_accepts_what_it_can_afford(
    capped_client: TestClient,
) -> None:
    response = capped_client.post(
        "/api/v1/animations", json={"prompt": "a circle", "quality": "low"}
    )
    assert response.status_code == 202


def test_the_refusal_happens_before_any_render(capped_service, renderer) -> None:
    """Nothing should be spent on a job the instance cannot finish."""
    with pytest.raises(ValidationError):
        capped_service.submit_prompt("a circle", Quality.HIGH)
    assert not list(renderer.scratch.glob("*.mp4"))
