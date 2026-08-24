"""In-process sliding-window rate limiter.

Keeps a timestamp log per (bucket, identity) and counts what falls inside the
window. More accurate than fixed windows, which let a caller spend two full
quotas back-to-back across a boundary.

State is per-process, which is correct while the app runs a single worker. With
more than one instance each would enforce its own copy of the quota, and this
would need to move to Redis — hence the port.

Memory is bounded on purpose: identity comes from a request header, so an
attacker rotating it must not be able to grow this map without limit.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Callable, Mapping

from app.domain.ports.logging import Logger
from app.domain.ports.rate_limit import Quota, RateLimitVerdict

_ALLOWED_UNLIMITED = RateLimitVerdict(allowed=True, remaining=-1, retry_after_seconds=0)


class InMemoryRateLimiter:
    def __init__(
        self,
        quotas: Mapping[str, Quota],
        logger: Logger,
        *,
        max_identities: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._quotas = dict(quotas)
        self._logger = logger
        self._max_identities = max_identities
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()

    def check(self, bucket: str, identity: str) -> RateLimitVerdict:
        quota = self._quotas.get(bucket)
        if quota is None or quota.disabled:
            return _ALLOWED_UNLIMITED

        now = self._clock()
        key = (bucket, identity)

        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                self._evict_if_full()
                hits = self._hits[key] = deque()

            cutoff = now - quota.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= quota.limit:
                retry_after = int(hits[0] + quota.window_seconds - now) + 1
                return RateLimitVerdict(
                    allowed=False, remaining=0, retry_after_seconds=max(1, retry_after)
                )

            hits.append(now)
            self._hits.move_to_end(key)
            return RateLimitVerdict(
                allowed=True,
                remaining=quota.limit - len(hits),
                retry_after_seconds=0,
            )

    def _evict_if_full(self) -> None:
        """Drop the least recently seen identity once the map is full.

        Evicting resets that caller's window, so the cap is set high enough
        that filling it is itself abusive rather than ordinary traffic.
        """
        while len(self._hits) >= self._max_identities:
            self._hits.popitem(last=False)
            self._logger.warning("ratelimit.evicted", tracked=len(self._hits))
