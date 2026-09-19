"""Opaque session tokens.

The value handed to a browser and the value kept in the database are
deliberately different. Only the digest is stored, so a dump of the session
table yields nothing that can be replayed as a login — the same reason a
password table stores hashes rather than passwords.
"""

from __future__ import annotations

import hashlib
import secrets

# 256 bits from the OS CSPRNG. Guessing is infeasible, which is precisely why a
# plain digest suffices here: a password-style KDF defends against brute force
# over a small search space, and there is no small search space to defend.
_TOKEN_BYTES = 32


def new_session_token() -> str:
    """Mint a cookie value. Never store the result."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Derive the database key for a cookie value."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
