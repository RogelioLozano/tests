"""GitHub session storage and token handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.tokens import hash_session_token, new_session_token
from app.domain.errors import RepositoryError
from app.domain.models import GitHubSession

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def make_session(token: str, *, login: str = "octocat", ttl_hours: int = 8):
    return GitHubSession(
        token_hash=hash_session_token(token),
        login=login,
        access_token="gho_secret",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=ttl_hours),
        avatar_url="https://avatars.githubusercontent.com/u/1",
    )


def test_round_trips_a_session(sessions) -> None:
    token = new_session_token()
    sessions.add(make_session(token))

    found = sessions.find(hash_session_token(token), now=NOW)
    assert found is not None
    assert found.login == "octocat"
    assert found.access_token == "gho_secret"


def test_the_raw_token_is_not_what_is_stored(sessions) -> None:
    """The cookie value must not be recoverable from the table."""
    token = new_session_token()
    sessions.add(make_session(token))

    assert sessions.find(token, now=NOW) is None


def test_an_unknown_token_finds_nothing(sessions) -> None:
    sessions.add(make_session(new_session_token()))
    assert sessions.find(hash_session_token(new_session_token()), now=NOW) is None


def test_an_expired_session_is_never_returned(sessions) -> None:
    token = new_session_token()
    sessions.add(make_session(token, ttl_hours=8))

    later = NOW + timedelta(hours=9)
    assert sessions.find(hash_session_token(token), now=later) is None


def test_expiry_is_exclusive_at_the_boundary(sessions) -> None:
    token = new_session_token()
    sessions.add(make_session(token, ttl_hours=8))
    boundary = NOW + timedelta(hours=8)

    assert sessions.find(hash_session_token(token), now=boundary) is None
    assert (
        sessions.find(hash_session_token(token), now=boundary - timedelta(seconds=1))
        is not None
    )


def test_delete_ends_the_session(sessions) -> None:
    token = new_session_token()
    sessions.add(make_session(token))
    sessions.delete(hash_session_token(token))

    assert sessions.find(hash_session_token(token), now=NOW) is None


def test_delete_is_idempotent(sessions) -> None:
    """Logging out twice, or after expiry, must not be an error."""
    sessions.delete(hash_session_token("never-existed"))


def test_purge_removes_only_expired_rows(sessions) -> None:
    live, dead = new_session_token(), new_session_token()
    sessions.add(make_session(live, ttl_hours=8))
    sessions.add(make_session(dead, login="ghost", ttl_hours=1))

    later = NOW + timedelta(hours=2)
    assert sessions.purge_expired(now=later) == 1
    assert sessions.find(hash_session_token(live), now=later) is not None


def test_a_colliding_session_is_refused_rather_than_overwritten(sessions) -> None:
    """A silent upsert would hand one visitor another visitor's GitHub token."""
    token = new_session_token()
    sessions.add(make_session(token))

    with pytest.raises(RepositoryError):
        sessions.add(make_session(token, login="attacker"))

    assert sessions.find(hash_session_token(token), now=NOW).login == "octocat"


def test_tokens_are_unique_and_hash_stably() -> None:
    first, second = new_session_token(), new_session_token()
    assert first != second
    assert hash_session_token(first) == hash_session_token(first)
    assert hash_session_token(first) != hash_session_token(second)


def test_repr_does_not_leak_the_access_token() -> None:
    assert "gho_secret" not in repr(make_session(new_session_token()))
