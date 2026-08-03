"""Redis 可恢复任务队列的集成测试。"""

import hashlib
import os
from dataclasses import replace
from uuid import uuid4

import pytest

from app.operations import RedisRuntime


@pytest.mark.integration
def test_durable_job_lifecycle_against_redis() -> None:
    redis_url = os.getenv("TEST_REDIS_URL", "")
    if not redis_url:
        pytest.skip("TEST_REDIS_URL is not configured")
    queue = f"interview-agent:test:jobs:{uuid4().hex}"
    runtime = RedisRuntime(redis_url, queue)
    idempotency_key = "integration-command-1"
    job_id = ""
    try:
        job_id = runtime.enqueue(
            "knowledge_import",
            {"requested_by": "integration-test"},
            idempotency_key=idempotency_key,
            max_attempts=3,
        )
        assert (
            runtime.enqueue(
                "knowledge_import",
                {"requested_by": "integration-test"},
                idempotency_key=idempotency_key,
                max_attempts=3,
            )
            == job_id
        )
        first = runtime.claim_job(lease_seconds=1)
        assert first and first.attempt == 1
        assert not runtime.acknowledge_job(
            replace(first, claim_token="stale-owner"),
            result={},
        )
        assert runtime.recover_expired_jobs(now=9_999_999_999) == 1
        second = runtime.claim_job(lease_seconds=1)
        assert second and second.attempt == 2
        assert (
            runtime.fail_job(
                second,
                error="temporary",
                retry_delay_seconds=0,
            )
            == "retry_scheduled"
        )
        third = runtime.claim_job(lease_seconds=1)
        assert third and third.attempt == 3
        assert (
            runtime.fail_job(
                third,
                error="exhausted",
                retry_delay_seconds=0,
            )
            == "dead"
        )
        assert runtime.get_job(job_id)["status"] == "dead"
    finally:
        if runtime.client:
            digest = hashlib.sha256(
                f"knowledge_import:{idempotency_key}".encode()
            ).hexdigest()
            keys = [
                queue,
                f"{queue}:processing",
                f"{queue}:delayed",
                f"{queue}:dead",
                f"{queue}:idempotency:{digest}",
            ]
            if job_id:
                keys.append(f"interview-agent:job:{job_id}")
            runtime.client.delete(*keys)
