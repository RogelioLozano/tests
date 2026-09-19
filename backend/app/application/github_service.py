"""Application service for delegated GitHub access.

Owns the three use cases behind the OAuth flow: turn a consent code into a
stored session, read the connected identity, and list that account's public
repositories.

The raw session token appears in exactly one place — the `Connection` returned
by `connect` — so the caller can put it in a cookie. Everywhere else, including
the database, only its hash exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from app.core.tokens import hash_session_token, new_session_token
from app.domain.errors import UnauthorizedError
from app.domain.models import GitHubSession, Repository
from app.domain.ports.clock import Clock
from app.domain.ports.github import GitHubClient
from app.domain.ports.logging import Logger
from app.domain.ports.repository import GitHubSessionRepository


@dataclass(frozen=True, slots=True)
class Connection:
    """A newly established session and the cookie value that unlocks it."""

    token: str
    session: GitHubSession


class GitHubService:
    def __init__(
        self,
        *,
        client: GitHubClient,
        sessions: GitHubSessionRepository,
        clock: Clock,
        logger: Logger,
        session_ttl_seconds: int,
    ) -> None:
        self._client = client
        self._sessions = sessions
        self._clock = clock
        self._logger = logger
        self._ttl = session_ttl_seconds

    def authorize_url(self, *, state: str) -> str:
        return self._client.authorize_url(state=state)

    def connect(self, code: str) -> Connection:
        """Spend the authorization code and open a session for this browser."""
        access_token = self._client.exchange_code(code)
        identity = self._client.fetch_identity(access_token)

        now = self._clock.now()
        token = new_session_token()
        session = GitHubSession(
            token_hash=hash_session_token(token),
            login=identity.login,
            access_token=access_token,
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl),
            avatar_url=identity.avatar_url,
        )
        self._sessions.add(session)
        self._logger.info("github.connected", login=identity.login)
        return Connection(token=token, session=session)

    def find_session(self, token: str) -> GitHubSession | None:
        """For endpoints that must report "not connected" rather than refuse."""
        if not token:
            return None
        return self._sessions.find(hash_session_token(token), now=self._clock.now())

    def repositories(self, token: str) -> Sequence[Repository]:
        session = self._require(token)
        return self._client.list_public_repositories(
            session.login, token=session.access_token
        )

    def disconnect(self, token: str) -> None:
        """Drops the stored GitHub token; the app cannot act for the user again."""
        if not token:
            return
        self._sessions.delete(hash_session_token(token))
        self._logger.info("github.disconnected")

    def _require(self, token: str) -> GitHubSession:
        session = self.find_session(token)
        if session is None:
            raise UnauthorizedError(
                "Connect your GitHub account to see this.",
                code="github_not_connected",
            )
        return session
