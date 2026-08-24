"""Rate limiting port.

Two quotas rather than one, because the endpoints cost wildly different
amounts: a render spends LLM tokens and CPU seconds, while a status poll is a
single indexed SQLite read. The frontend polls roughly once a second, so a
limit strict enough to protect the expensive path would break the cheap one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Bucket names, so a caller cannot invent one that was never configured.
RENDERS = "renders"
REQUESTS = "requests"


@dataclass(frozen=True, slots=True)
class Quota:
    limit: int
    window_seconds: int

    @property
    def disabled(self) -> bool:
        return self.limit <= 0


@dataclass(frozen=True, slots=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    def check(self, bucket: str, identity: str) -> RateLimitVerdict:
        """Record an attempt by `identity` against `bucket` and rule on it.

        Implementations must be safe to call from multiple threads.
        """
        ...
