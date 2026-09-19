"""Cookies and CSRF state for the GitHub OAuth flow.

Two cookies, both `HttpOnly` so that no script — ours or an injected one — can
read them. That is the whole reason this flow uses cookies instead of the
localStorage-plus-header pattern the access code uses: the OAuth callback is a
top-level navigation, during which no JavaScript of ours runs at all.
"""

from __future__ import annotations

import secrets

from fastapi import Response

SESSION_COOKIE = "gh_session"
STATE_COOKIE = "gh_oauth_state"


def set_cookie(
    response: Response, name: str, value: str, *, max_age: int, secure: bool
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=secure,
        # Lax rather than Strict: the callback arrives as a top-level navigation
        # from github.com, and Strict would withhold the cookie at exactly that
        # moment. Lax still blocks it on cross-site POST, which is what matters.
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response, name: str, *, secure: bool) -> None:
    response.delete_cookie(
        name, path="/", httponly=True, secure=secure, samesite="lax"
    )


def state_matches(expected: str, provided: str) -> bool:
    """Constant-time comparison of the CSRF nonce.

    Absent on either side is a failure: a callback with no state cookie is
    either a stale tab or someone else's code being planted on this browser.
    """
    if not expected or not provided:
        return False
    return secrets.compare_digest(expected, provided)
