from unittest.mock import MagicMock

import pytest

from app.operations import (
    FixedWindowRateLimiter,
    JobClaim,
    JobIdempotencyConflict,
    RedisRuntime,
    RequestMetrics,
    SharedRateLimiter,
)


def test_rate_limiter_blocks_requests_inside_window():
    limiter = FixedWindowRateLimiter(requests=2, window_seconds=10)

    assert limiter.allow("client", now=0)[0]
    assert limiter.allow("client", now=1)[0]
    allowed, retry_after = limiter.allow("client", now=2)

    assert not allowed
    assert retry_after == 8
    assert limiter.allow("client", now=11)[0]


def test_metrics_render_prometheus_counters():
    metrics = RequestMetrics()
    started = metrics.start()
    metrics.finish(started, 500)

    rendered = metrics.render_prometheus()

    assert "interview_agent_requests_total 1" in rendered
    assert "interview_agent_errors_total 1" in rendered
    assert "interview_agent_active_requests 0" in rendered


def test_dependency_metrics_include_duration_and_errors():
    metrics = RequestMetrics()
    with metrics.dependency("database"):
        pass
    try:
        with metrics.dependency("qdrant"):
            raise RuntimeError("offline")
    except RuntimeError:
        pass

    rendered = metrics.render_prometheus()
    assert 'dependency_calls_total{dependency="database"} 1' in rendered
    assert 'dependency_errors_total{dependency="qdrant"} 1' in rendered


def test_llm_token_metrics_are_grouped_by_agent():
    metrics = RequestMetrics()

    metrics.observe_tokens("knowledge", 120, 30)
    metrics.observe_tokens("knowledge", 80, 20)

    rendered = metrics.render_prometheus()
    assert 'llm_input_tokens_total{agent="knowledge"} 200' in rendered
    assert 'llm_output_tokens_total{agent="knowledge"} 50' in rendered


def test_shared_rate_limiter_uses_redis_when_available():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.allow = MagicMock(return_value=(False, 10))
    limiter = SharedRateLimiter(2, 10, runtime)

    assert limiter.allow("client") == (False, 10)
    runtime.allow.assert_called_once_with("client", 2, 10)


def test_redis_runtime_enqueues_serialized_job():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.client.eval.return_value = "job-1"

    job_id = runtime.enqueue(
        "knowledge_import",
        {"actor": "admin"},
        idempotency_key="import-command-1",
    )

    assert job_id == "job-1"
    script_args = runtime.client.eval.call_args.args
    assert "job_enqueue_v1" in script_args[0]
    assert "import-command-1" in script_args


def test_redis_runtime_rejects_idempotency_key_payload_mismatch():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.client.eval.return_value = "!conflict"

    with pytest.raises(JobIdempotencyConflict):
        runtime.enqueue(
            "knowledge_import",
            {"actor": "another-admin"},
            idempotency_key="import-command-1",
        )


def test_redis_runtime_claim_recovers_crashed_and_due_jobs_first():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.client.eval.side_effect = [1, 1, ["job-1", "2"]]
    runtime.client.hgetall.return_value = {
        "type": "knowledge_import",
        "payload": '{"actor": "admin"}',
        "max_attempts": "3",
    }

    claim = runtime.claim_job(lease_seconds=60)

    assert claim is not None
    assert claim.job_id == "job-1"
    assert claim.attempt == 2
    assert claim.payload == {"actor": "admin"}
    scripts = [call.args[0] for call in runtime.client.eval.call_args_list]
    assert "job_recover_v1" in scripts[0]
    assert "job_promote_v1" in scripts[1]
    assert "job_claim_v1" in scripts[2]


def test_job_ack_failure_and_heartbeat_are_owner_fenced():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.client.eval.side_effect = [1, "retry_scheduled", 1]
    claim = JobClaim(
        job_id="job-1",
        job_type="knowledge_import",
        payload={},
        claim_token="owner-1",
        attempt=1,
        max_attempts=3,
    )

    assert runtime.acknowledge_job(claim, result={"chunks": 10})
    assert (
        runtime.fail_job(
            claim,
            error="temporary",
            retry_delay_seconds=30,
        )
        == "retry_scheduled"
    )
    assert runtime.heartbeat_job(claim, lease_seconds=60)

    scripts = [call.args[0] for call in runtime.client.eval.call_args_list]
    assert "job_ack_v1" in scripts[0]
    assert "job_fail_v1" in scripts[1]
    assert "job_heartbeat_v1" in scripts[2]


def test_redis_runtime_reads_and_updates_job_status():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.client.hgetall.return_value = {
        "job_id": "job-1",
        "status": "completed",
    }

    runtime.update_job("job-1", status="completed", result={"chunks": 10})
    result = runtime.get_job("job-1")

    runtime.client.hset.assert_called_once()
    assert result == {"job_id": "job-1", "status": "completed"}


def test_redis_runtime_lock_is_token_owned():
    runtime = RedisRuntime("", "jobs")
    runtime.client = MagicMock()
    runtime.client.set.return_value = True
    runtime.client.eval.return_value = 1

    assert runtime.acquire_lock("publish", "owner-1", 60)
    assert runtime.release_lock("publish", "owner-1")

    runtime.client.set.assert_called_once_with(
        "publish",
        "owner-1",
        nx=True,
        ex=60,
    )
    runtime.client.eval.assert_called_once()
    assert runtime.client.eval.call_args.args[-2:] == ("publish", "owner-1")
