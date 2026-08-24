"""Rate limiting tests.

Two quotas with very different jobs: a strict one on renders (which cost LLM
tokens and CPU) and a generous one everywhere else (which must not break the
frontend's once-a-second polling).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import RateLimitSettings
from app.domain.ports.rate_limit import Quota, RateLimiter, RENDERS, REQUESTS
from app.infrastructure.rate_limit.factory import build_rate_limiter
from app.infrastructure.rate_limit.memory_limiter import InMemoryRateLimiter
from tests.conftest import RecordingLogger, build_client, build_service


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def limiter_with(logger, limit: int, window: int, **kwargs) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(
        {RENDERS: Quota(limit, window)}, logger, **kwargs
    )


def test_allows_up_to_the_limit(logger: RecordingLogger) -> None:
    limiter = limiter_with(logger, 3, 60)
    assert [limiter.check(RENDERS, "ip").allowed for _ in range(3)] == [True] * 3


def test_blocks_past_the_limit(logger: RecordingLogger) -> None:
    limiter = limiter_with(logger, 2, 60)
    limiter.check(RENDERS, "ip")
    limiter.check(RENDERS, "ip")

    verdict = limiter.check(RENDERS, "ip")
    assert not verdict.allowed
    assert verdict.retry_after_seconds > 0


def test_identities_are_independent(logger: RecordingLogger) -> None:
    """One noisy caller must not lock everyone else out."""
    limiter = limiter_with(logger, 1, 60)
    assert limiter.check(RENDERS, "1.1.1.1").allowed
    assert not limiter.check(RENDERS, "1.1.1.1").allowed
    assert limiter.check(RENDERS, "2.2.2.2").allowed


def test_the_window_slides(logger: RecordingLogger) -> None:
    clock = FakeClock()
    limiter = limiter_with(logger, 2, 60, clock=clock)
    limiter.check(RENDERS, "ip")
    limiter.check(RENDERS, "ip")
    assert not limiter.check(RENDERS, "ip").allowed

    clock.advance(61)
    assert limiter.check(RENDERS, "ip").allowed


def test_a_sliding_window_does_not_allow_a_double_burst(
    logger: RecordingLogger,
) -> None:
    """The reason for a timestamp log rather than a fixed counter."""
    clock = FakeClock()
    limiter = limiter_with(logger, 2, 60, clock=clock)
    limiter.check(RENDERS, "ip")
    limiter.check(RENDERS, "ip")

    clock.advance(31)  # halfway through the window
    assert not limiter.check(RENDERS, "ip").allowed


def test_remaining_counts_down(logger: RecordingLogger) -> None:
    limiter = limiter_with(logger, 3, 60)
    assert limiter.check(RENDERS, "ip").remaining == 2
    assert limiter.check(RENDERS, "ip").remaining == 1


def test_a_zero_limit_disables_the_bucket(logger: RecordingLogger) -> None:
    limiter = limiter_with(logger, 0, 60)
    assert all(limiter.check(RENDERS, "ip").allowed for _ in range(50))


def test_an_unknown_bucket_is_allowed(logger: RecordingLogger) -> None:
    limiter = limiter_with(logger, 1, 60)
    assert limiter.check("never-configured", "ip").allowed


def test_memory_is_bounded(logger: RecordingLogger) -> None:
    """Identity comes from a forgeable header, so the map must not grow freely."""
    limiter = limiter_with(logger, 5, 60, max_identities=10)
    for i in range(50):
        limiter.check(RENDERS, f"ip-{i}")

    assert len(limiter._hits) <= 10  # noqa: SLF001 - asserting the bound itself
    assert "ratelimit.evicted" in logger.names()


# --- HTTP behaviour ---------------------------------------------------------


@pytest.fixture
def strict_client(settings, repository, storage, renderer, logger) -> TestClient:
    service = build_service(
        settings=settings,
        repository=repository,
        storage=storage,
        renderer=renderer,
        logger=logger,
    )
    limiter = build_rate_limiter(
        RateLimitSettings(render_limit=2, render_window_seconds=600),
        logger,
    )
    return build_client(
        settings=settings, service=service, logger=logger, rate_limiter=limiter
    )


def render(client: TestClient):
    return client.post("/api/v1/animations", json={"prompt": "a circle"})


def test_renders_are_limited(strict_client: TestClient) -> None:
    assert render(strict_client).status_code == 202
    assert render(strict_client).status_code == 202

    blocked = render(strict_client)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"


def test_a_blocked_render_says_when_to_retry(strict_client: TestClient) -> None:
    render(strict_client)
    render(strict_client)
    blocked = render(strict_client)

    assert int(blocked.headers["Retry-After"]) > 0


def test_polling_is_not_blocked_by_the_render_quota(strict_client: TestClient) -> None:
    """The frontend polls about once a second; the strict quota must not touch it."""
    job_id = render(strict_client).json()["id"]
    render(strict_client)
    assert render(strict_client).status_code == 429

    for _ in range(20):
        assert strict_client.get(f"/api/v1/animations/{job_id}").status_code == 200


def test_health_is_never_rate_limited(logger: RecordingLogger, settings, repository, storage, renderer) -> None:
    """The platform probes it every 30s; counting it would be self-inflicted."""
    service = build_service(
        settings=settings,
        repository=repository,
        storage=storage,
        renderer=renderer,
        logger=logger,
    )
    limiter = build_rate_limiter(
        RateLimitSettings(request_limit=3, request_window_seconds=60), logger
    )
    client = build_client(
        settings=settings, service=service, logger=logger, rate_limiter=limiter
    )

    for _ in range(20):
        assert client.get("/api/v1/health").status_code == 200


def test_the_global_quota_blocks_a_flood(
    logger: RecordingLogger, settings, repository, storage, renderer
) -> None:
    service = build_service(
        settings=settings,
        repository=repository,
        storage=storage,
        renderer=renderer,
        logger=logger,
    )
    limiter = build_rate_limiter(
        RateLimitSettings(request_limit=5, request_window_seconds=60), logger
    )
    client = build_client(
        settings=settings, service=service, logger=logger, rate_limiter=limiter
    )

    codes = [client.get("/api/v1/capabilities").status_code for _ in range(10)]
    assert 429 in codes
    assert codes[:5] == [200] * 5
