"""Shared-secret gate on the endpoints that cost money.

A bearer token, not an identity: it proves the caller knows the secret, not who
they are. That is enough for "let the people I gave the code to submit prompts"
and it needs no user table, no sessions, and no login flow.

Reads stay open on purpose. A portfolio piece has to be visible — a visitor can
watch existing animations and read the generated source immediately — while the
one action that spends Groq tokens and CPU is gated.

Unset key means open, so local dev and the test suite are unaffected.
"""

from __future__ import annotations

import secrets

from starlette.requests import Request

from app.domain.errors import UnauthorizedError

API_KEY_HEADER = "X-API-Key"


def is_enabled(expected: str) -> bool:
    return bool(expected)


def verify(provided: str, expected: str) -> bool:
    """Constant-time comparison.

    `==` on strings short-circuits at the first differing byte, so response
    timing would leak the secret one character at a time.
    """
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_api_key(request: Request) -> None:
    container = request.app.state.container
    expected = container.settings.api_key
    if not is_enabled(expected):
        return

    provided = request.headers.get(API_KEY_HEADER, "")
    if not provided:
        raise UnauthorizedError(
            "An access code is required to submit a prompt.",
            code="api_key_required",
        )
    if not verify(provided, expected):
        # Logged without the attempted value: it goes to a log aggregator, and
        # a near-miss guess is still sensitive.
        container.logger.warning("auth.rejected", path=request.url.path)
        raise UnauthorizedError(
            "That access code is not valid.", code="invalid_api_key"
        )
