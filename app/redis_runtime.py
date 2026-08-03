"""Redis cache, lock, durable-job, lease, and worker-heartbeat runtime."""

import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

@dataclass(frozen=True)
class JobClaim:
    job_id: str
    job_type: str
    payload: dict[str, object]
    claim_token: str
    attempt: int
    max_attempts: int


class JobIdempotencyConflict(ValueError):
    """An idempotency key was reused for a different job request."""


class RedisRuntime:
    _ENQUEUE_SCRIPT = """
-- job_enqueue_v1
if ARGV[1] ~= '' then
  local existing = redis.call('GET', ARGV[1])
  if existing then
    local existing_digest = redis.call(
      'HGET', ARGV[3] .. existing, 'request_digest')
    if existing_digest ~= ARGV[11] then return '!conflict' end
    return existing
  end
  redis.call('SET', ARGV[1], ARGV[2], 'EX', ARGV[10])
end
local job_key = ARGV[3] .. ARGV[2]
redis.call('HSET', job_key,
  'job_id', ARGV[2],
  'type', ARGV[4],
  'status', 'queued',
  'payload', ARGV[5],
  'result', '',
  'error', '',
  'attempts', '0',
  'max_attempts', ARGV[6],
  'claim_token', '',
  'lease_expires_at', '',
  'next_attempt_at', '',
  'idempotency_key', ARGV[7],
  'request_digest', ARGV[11],
  'created_at', ARGV[8],
  'updated_at', ARGV[8])
redis.call('EXPIRE', job_key, ARGV[10])
redis.call('RPUSH', KEYS[1], ARGV[2])
return ARGV[2]
"""
    _CLAIM_SCRIPT = """
-- job_claim_v1
local job_id = redis.call('LPOP', KEYS[1])
if not job_id then return nil end
local job_key = ARGV[1] .. job_id
local attempt = redis.call('HINCRBY', job_key, 'attempts', 1)
redis.call('HSET', job_key,
  'status', 'running',
  'claim_token', ARGV[2],
  'lease_expires_at', ARGV[3],
  'updated_at', ARGV[4])
redis.call('ZADD', KEYS[2], ARGV[3], job_id)
return {job_id, tostring(attempt)}
"""
    _ACK_SCRIPT = """
-- job_ack_v1
local job_key = ARGV[1] .. ARGV[2]
if redis.call('HGET', job_key, 'status') ~= 'running'
  or redis.call('HGET', job_key, 'claim_token') ~= ARGV[3] then
  return 0
end
redis.call('HSET', job_key,
  'status', 'completed',
  'claim_token', '',
  'lease_expires_at', '',
  'result', ARGV[4],
  'error', '',
  'updated_at', ARGV[5])
redis.call('ZREM', KEYS[1], ARGV[2])
return 1
"""
    _FAIL_SCRIPT = """
-- job_fail_v1
local job_key = ARGV[1] .. ARGV[2]
if redis.call('HGET', job_key, 'status') ~= 'running'
  or redis.call('HGET', job_key, 'claim_token') ~= ARGV[3] then
  return ''
end
local attempts = tonumber(redis.call('HGET', job_key, 'attempts') or '0')
local max_attempts = tonumber(redis.call('HGET', job_key, 'max_attempts') or '1')
redis.call('ZREM', KEYS[1], ARGV[2])
if attempts >= max_attempts then
  redis.call('HSET', job_key,
    'status', 'dead',
    'claim_token', '',
    'lease_expires_at', '',
    'error', ARGV[4],
    'updated_at', ARGV[6])
  redis.call('LPUSH', KEYS[3], ARGV[2])
  return 'dead'
end
redis.call('HSET', job_key,
  'status', 'retry_scheduled',
  'claim_token', '',
  'lease_expires_at', '',
  'next_attempt_at', ARGV[5],
  'error', ARGV[4],
  'updated_at', ARGV[6])
redis.call('ZADD', KEYS[2], ARGV[5], ARGV[2])
return 'retry_scheduled'
"""
    _HEARTBEAT_SCRIPT = """
-- job_heartbeat_v1
local job_key = ARGV[1] .. ARGV[2]
if redis.call('HGET', job_key, 'status') ~= 'running'
  or redis.call('HGET', job_key, 'claim_token') ~= ARGV[3] then
  return 0
end
redis.call('HSET', job_key,
  'lease_expires_at', ARGV[4],
  'updated_at', ARGV[5])
redis.call('ZADD', KEYS[1], ARGV[4], ARGV[2])
return 1
"""
    _RECOVER_SCRIPT = """
-- job_recover_v1
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
local recovered = 0
for _, job_id in ipairs(expired) do
  local job_key = ARGV[1] .. job_id
  if redis.call('HGET', job_key, 'status') == 'running' then
    local attempts = tonumber(redis.call('HGET', job_key, 'attempts') or '0')
    local max_attempts = tonumber(
      redis.call('HGET', job_key, 'max_attempts') or '1')
    if attempts >= max_attempts then
      redis.call('HSET', job_key,
        'status', 'dead',
        'claim_token', '',
        'lease_expires_at', '',
        'error', 'worker lease expired after maximum attempts',
        'updated_at', ARGV[2])
      redis.call('LPUSH', KEYS[3], job_id)
    else
      redis.call('HSET', job_key,
        'status', 'queued',
        'claim_token', '',
        'lease_expires_at', '',
        'error', 'worker lease expired',
        'updated_at', ARGV[2])
      redis.call('RPUSH', KEYS[2], job_id)
    end
    recovered = recovered + 1
  end
  redis.call('ZREM', KEYS[1], job_id)
end
return recovered
"""
    _PROMOTE_SCRIPT = """
-- job_promote_v1
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
local promoted = 0
for _, job_id in ipairs(due) do
  local job_key = ARGV[1] .. job_id
  if redis.call('HGET', job_key, 'status') == 'retry_scheduled' then
    redis.call('HSET', job_key,
      'status', 'queued',
      'next_attempt_at', '',
      'updated_at', ARGV[2])
    redis.call('RPUSH', KEYS[2], job_id)
    promoted = promoted + 1
  end
  redis.call('ZREM', KEYS[1], job_id)
end
return promoted
"""

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

    @property
    def _worker_heartbeat_key(self) -> str:
        return f"{self.queue_name}:worker:heartbeat"

    def publish_worker_heartbeat(
        self,
        instance_id: str,
        *,
        ttl_seconds: int,
        now: float | None = None,
    ) -> None:
        if not self.client:
            raise RedisError("Redis is not configured")
        if not instance_id:
            raise ValueError("Worker heartbeat instance ID is required")
        payload = json.dumps(
            {
                "version": 1,
                "instance_id": instance_id,
                "heartbeat_at": (
                    float(now) if now is not None else time.time()
                ),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        self.client.set(
            self._worker_heartbeat_key,
            payload,
            ex=max(3, int(ttl_seconds)),
        )

    def read_worker_heartbeat(
        self,
        *,
        max_age_seconds: int,
        now: float | None = None,
    ) -> dict[str, object]:
        if not self.client:
            raise RedisError("Redis is not configured")
        raw = self.client.get(self._worker_heartbeat_key)
        if not raw:
            raise RedisError("Worker heartbeat is unavailable")
        try:
            payload = json.loads(str(raw))
            version = int(payload["version"])
            instance_id = str(payload["instance_id"])
            heartbeat_at = float(payload["heartbeat_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RedisError("Worker heartbeat is invalid") from exc
        if version != 1 or not instance_id:
            raise RedisError("Worker heartbeat is invalid")

        current = float(now) if now is not None else time.time()
        max_age = max(1, int(max_age_seconds))
        age = current - heartbeat_at
        if not math.isfinite(heartbeat_at) or age < 0 or age > max_age:
            raise RedisError("Worker heartbeat is stale")
        return {
            "version": version,
            "instance_id": instance_id,
            "heartbeat_at": heartbeat_at,
        }

    def check_worker_heartbeat(self, *, max_age_seconds: int) -> None:
        self.read_worker_heartbeat(max_age_seconds=max_age_seconds)

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

    def acquire_lock(self, key: str, token: str, ttl_seconds: int) -> bool:
        if not self.client:
            raise RedisError("Redis is not configured")
        return bool(
            self.client.set(
                key,
                token,
                nx=True,
                ex=max(1, ttl_seconds),
            )
        )

    def release_lock(self, key: str, token: str) -> bool:
        if not self.client:
            raise RedisError("Redis is not configured")
        deleted = self.client.eval(
            (
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end"
            ),
            1,
            key,
            token,
        )
        return bool(deleted)

    @property
    def _job_prefix(self) -> str:
        return "interview-agent:job:"

    @property
    def _processing_key(self) -> str:
        return f"{self.queue_name}:processing"

    @property
    def _delayed_key(self) -> str:
        return f"{self.queue_name}:delayed"

    @property
    def _dead_key(self) -> str:
        return f"{self.queue_name}:dead"

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> str:
        if not self.client:
            raise RedisError("Redis is not configured")
        # Lua 脚本把幂等占位与入队合成一次原子操作，避免多副本重复任务。
        job_id = str(uuid4())
        idempotency_redis_key = ""
        if idempotency_key:
            digest = hashlib.sha256(
                f"{job_type}:{idempotency_key}".encode()
            ).hexdigest()
            idempotency_redis_key = (
                f"{self.queue_name}:idempotency:{digest}"
            )
        now = str(int(time.time()))
        ttl = 7 * 24 * 60 * 60
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_digest = hashlib.sha256(
            f"{job_type}:{serialized_payload}".encode()
        ).hexdigest()
        result = str(
            self.client.eval(
                self._ENQUEUE_SCRIPT,
                1,
                self.queue_name,
                idempotency_redis_key,
                job_id,
                self._job_prefix,
                job_type,
                serialized_payload,
                str(max(1, max_attempts)),
                idempotency_key or "",
                now,
                self.queue_name,
                str(ttl),
                request_digest,
            )
        )
        if result == "!conflict":
            raise JobIdempotencyConflict(
                "Idempotency-Key 不能用于不同的后台任务请求"
            )
        return result

    def claim_job(self, *, lease_seconds: int = 300) -> JobClaim | None:
        if not self.client:
            raise RedisError("Redis is not configured")
        now = int(time.time())
        # 每次领取前先回收失联任务并提升到期重试，无需额外调度进程。
        self.recover_expired_jobs(now=now)
        self.promote_due_jobs(now=now)
        claim_token = str(uuid4())
        claimed = self.client.eval(
            self._CLAIM_SCRIPT,
            2,
            self.queue_name,
            self._processing_key,
            self._job_prefix,
            claim_token,
            str(now + max(1, lease_seconds)),
            str(now),
        )
        if not claimed:
            return None
        job_id, attempt = str(claimed[0]), int(claimed[1])
        record = self.client.hgetall(f"{self._job_prefix}{job_id}")
        if not record:
            raise RedisError(f"Claimed job metadata is missing: {job_id}")
        return JobClaim(
            job_id=job_id,
            job_type=str(record["type"]),
            payload=json.loads(str(record.get("payload") or "{}")),
            claim_token=claim_token,
            attempt=attempt,
            max_attempts=int(record.get("max_attempts") or 1),
        )

    def acknowledge_job(
        self,
        claim: JobClaim,
        *,
        result: object,
    ) -> bool:
        if not self.client:
            raise RedisError("Redis is not configured")
        serialized = (
            result
            if isinstance(result, str)
            else json.dumps(result, ensure_ascii=False)
        )
        # ACK 脚本校验 claim_token，旧 Worker 的迟到结果会被拒绝。
        return bool(
            self.client.eval(
                self._ACK_SCRIPT,
                1,
                self._processing_key,
                self._job_prefix,
                claim.job_id,
                claim.claim_token,
                serialized,
                str(int(time.time())),
            )
        )

    def fail_job(
        self,
        claim: JobClaim,
        *,
        error: str,
        retry_delay_seconds: int,
    ) -> str:
        if not self.client:
            raise RedisError("Redis is not configured")
        now = int(time.time())
        return str(
            self.client.eval(
                self._FAIL_SCRIPT,
                3,
                self._processing_key,
                self._delayed_key,
                self._dead_key,
                self._job_prefix,
                claim.job_id,
                claim.claim_token,
                error[:2000],
                str(now + max(0, retry_delay_seconds)),
                str(now),
            )
        )

    def heartbeat_job(
        self,
        claim: JobClaim,
        *,
        lease_seconds: int,
    ) -> bool:
        if not self.client:
            raise RedisError("Redis is not configured")
        now = int(time.time())
        return bool(
            self.client.eval(
                self._HEARTBEAT_SCRIPT,
                1,
                self._processing_key,
                self._job_prefix,
                claim.job_id,
                claim.claim_token,
                str(now + max(1, lease_seconds)),
                str(now),
            )
        )

    def recover_expired_jobs(self, *, now: int | None = None) -> int:
        if not self.client:
            raise RedisError("Redis is not configured")
        current = now if now is not None else int(time.time())
        return int(
            self.client.eval(
                self._RECOVER_SCRIPT,
                3,
                self._processing_key,
                self.queue_name,
                self._dead_key,
                self._job_prefix,
                str(current),
            )
        )

    def promote_due_jobs(self, *, now: int | None = None) -> int:
        if not self.client:
            raise RedisError("Redis is not configured")
        current = now if now is not None else int(time.time())
        return int(
            self.client.eval(
                self._PROMOTE_SCRIPT,
                2,
                self._delayed_key,
                self.queue_name,
                self._job_prefix,
                str(current),
            )
        )

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
