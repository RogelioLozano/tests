"""GitHub port.

The one abstraction over everything this app does with github.com: build the
consent URL, trade an authorization code for a token, and read public profile
and repository data. No layer above this knows a GitHub URL exists.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from app.domain.models import GitHubIdentity, Repository


class GitHubClient(Protocol):
    def authorize_url(self, *, state: str) -> str:
        """Where to send the browser to ask for consent.

        Carries the client id but never the secret: this URL is visible in the
        user's address bar.
        """
        ...

    def exchange_code(self, code: str) -> str:
        """Trade a one-time authorization code for an access token.

        Raises:
            UnauthorizedError: the code was wrong, already spent, or expired.
            IntegrationError: GitHub was unreachable or answered nonsense.
        """
        ...

    def fetch_identity(self, token: str) -> GitHubIdentity:
        """Who the token belongs to.

        Raises:
            UnauthorizedError: GitHub refused the token.
            IntegrationError: GitHub was unreachable or answered nonsense.
        """
        ...

    def list_public_repositories(
        self, login: str, *, token: str
    ) -> Sequence[Repository]:
        """Public repositories owned by `login`, most recently pushed first."""
        ...
