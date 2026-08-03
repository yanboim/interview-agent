"""Local and Redis-backed request rate limiting."""

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any

from redis.exceptions import RedisError


class FixedWindowRateLimiter:
    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current = now if now is not None else time.monotonic()
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                retry_after = max(1, int(events[0] + self.window_seconds - current))
                return False, retry_after
            events.append(current)
        return True, 0


class SharedRateLimiter:
    def __init__(self, requests: int, window_seconds: int, redis_runtime: Any) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.redis = redis_runtime
        self.fallback = FixedWindowRateLimiter(requests, window_seconds)

    def allow(self, key: str) -> tuple[bool, int]:
        if self.redis.client:
            try:
                return self.redis.allow(key, self.requests, self.window_seconds)
            except RedisError:
                logging.getLogger(__name__).warning(
                    "Redis rate limiter failed; using local fallback.",
                    exc_info=True,
                )
        return self.fallback.allow(key)
