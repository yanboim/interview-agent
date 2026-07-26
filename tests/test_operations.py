from unittest.mock import MagicMock

from app.operations import (
    FixedWindowRateLimiter,
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

    job_id = runtime.enqueue("knowledge_import", {"actor": "admin"})

    assert job_id
    pipeline = runtime.client.pipeline.return_value
    pipeline.hset.assert_called_once()
    pipeline.rpush.assert_called_once()
    pipeline.execute.assert_called_once()


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
