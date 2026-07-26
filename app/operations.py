import threading
import time
import json
import logging
from contextlib import contextmanager
from collections import defaultdict, deque
from dataclasses import dataclass
from uuid import uuid4

from redis import Redis
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


@dataclass
class MetricsSnapshot:
    requests_total: int
    errors_total: int
    active_requests: int
    duration_seconds_total: float


class RequestMetrics:
    def __init__(self) -> None:
        self._requests_total = 0
        self._errors_total = 0
        self._active_requests = 0
        self._duration_seconds_total = 0.0
        self._lock = threading.Lock()
        self._dependencies: dict[str, list[float | int]] = {}
        self._token_usage: dict[str, list[int]] = {}

    def start(self) -> float:
        with self._lock:
            self._active_requests += 1
        return time.monotonic()

    def finish(self, started_at: float, status_code: int) -> None:
        duration = time.monotonic() - started_at
        with self._lock:
            self._active_requests -= 1
            self._requests_total += 1
            self._duration_seconds_total += duration
            if status_code >= 500:
                self._errors_total += 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                requests_total=self._requests_total,
                errors_total=self._errors_total,
                active_requests=self._active_requests,
                duration_seconds_total=self._duration_seconds_total,
            )

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
                "# TYPE interview_agent_requests_total counter",
                f"interview_agent_requests_total {snapshot.requests_total}",
                "# TYPE interview_agent_errors_total counter",
                f"interview_agent_errors_total {snapshot.errors_total}",
                "# TYPE interview_agent_active_requests gauge",
                f"interview_agent_active_requests {snapshot.active_requests}",
                "# TYPE interview_agent_request_duration_seconds_total counter",
                (
                    "interview_agent_request_duration_seconds_total "
                    f"{snapshot.duration_seconds_total:.6f}"
                ),
        ]
        with self._lock:
            for name, values in sorted(self._dependencies.items()):
                count, errors, duration = values
                lines.extend(
                    [
                        f'interview_agent_dependency_calls_total{{dependency="{name}"}} {int(count)}',
                        f'interview_agent_dependency_errors_total{{dependency="{name}"}} {int(errors)}',
                        f'interview_agent_dependency_duration_seconds_total{{dependency="{name}"}} {float(duration):.6f}',
                    ]
                )
            for name, values in sorted(self._token_usage.items()):
                input_tokens, output_tokens = values
                lines.extend(
                    [
                        f'interview_agent_llm_input_tokens_total{{agent="{name}"}} {input_tokens}',
                        f'interview_agent_llm_output_tokens_total{{agent="{name}"}} {output_tokens}',
                    ]
                )
        return "\n".join([*lines, ""])

    @contextmanager
    def dependency(self, name: str):
        started = time.monotonic()
        success = False
        try:
            yield
            success = True
        finally:
            duration = time.monotonic() - started
            with self._lock:
                values = self._dependencies.setdefault(name, [0, 0, 0.0])
                values[0] += 1
                values[1] += int(not success)
                values[2] += duration

    def observe_tokens(
        self,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        with self._lock:
            values = self._token_usage.setdefault(agent_name, [0, 0])
            values[0] += max(0, int(input_tokens))
            values[1] += max(0, int(output_tokens))


request_metrics = RequestMetrics()


class RedisRuntime:
    def __init__(self, url: str, queue_name: str) -> None:
        self.url = url
        self.queue_name = queue_name
        self.client = (
            Redis.from_url(url, decode_responses=True)
            if isinstance(url, str) and url
            else None
        )

    def check(self) -> None:
        if self.client:
            self.client.ping()

    def allow(
        self,
        key: str,
        requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        if not self.client:
            raise RedisError("Redis is not configured")
        bucket = int(time.time()) // window_seconds
        redis_key = f"interview-agent:rate:{key}:{bucket}"
        pipe = self.client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 1)
        count, _ = pipe.execute()
        return int(count) <= requests, window_seconds if int(count) > requests else 0

    def get(self, key: str) -> str | None:
        return self.client.get(key) if self.client else None

    def set(self, key: str, value: str, ttl: int) -> None:
        if self.client:
            self.client.setex(key, ttl, value)

    def enqueue(self, job_type: str, payload: dict[str, object]) -> str:
        if not self.client:
            raise RedisError("Redis is not configured")
        job_id = str(uuid4())
        job = {
            "job_id": job_id,
            "type": job_type,
            "payload": payload,
        }
        job_key = f"interview-agent:job:{job_id}"
        pipe = self.client.pipeline()
        pipe.hset(
            job_key,
            mapping={
                "job_id": job_id,
                "type": job_type,
                "status": "queued",
                "payload": json.dumps(payload, ensure_ascii=False),
                "result": "",
                "error": "",
                "updated_at": str(int(time.time())),
            },
        )
        pipe.expire(job_key, 7 * 24 * 60 * 60)
        pipe.rpush(
            self.queue_name,
            json.dumps(job, ensure_ascii=False),
        )
        pipe.execute()
        return job_id

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        result: object = "",
        error: str = "",
    ) -> None:
        if not self.client:
            raise RedisError("Redis is not configured")
        job_key = f"interview-agent:job:{job_id}"
        self.client.hset(
            job_key,
            mapping={
                "status": status,
                "result": (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False)
                ),
                "error": error[:2000],
                "updated_at": str(int(time.time())),
            },
        )
        self.client.expire(job_key, 7 * 24 * 60 * 60)

    def get_job(self, job_id: str) -> dict[str, str] | None:
        if not self.client:
            raise RedisError("Redis is not configured")
        result = self.client.hgetall(f"interview-agent:job:{job_id}")
        return result or None


class SharedRateLimiter:
    def __init__(
        self,
        requests: int,
        window_seconds: int,
        redis_runtime: RedisRuntime,
    ) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.redis = redis_runtime
        self.fallback = FixedWindowRateLimiter(requests, window_seconds)

    def allow(self, key: str) -> tuple[bool, int]:
        if self.redis.client:
            try:
                return self.redis.allow(
                    key,
                    self.requests,
                    self.window_seconds,
                )
            except RedisError:
                logging.getLogger(__name__).warning(
                    "Redis rate limiter failed; using local fallback.",
                    exc_info=True,
                )
        return self.fallback.allow(key)
