from datetime import UTC, datetime, timedelta

import pytest

from app.workflow_observation import (
    BASELINE_QUERY_IDS,
    WORKFLOW_QUERY_IDS,
    baseline_queries,
    build_observation_draft,
    collect_baseline_operational_observation,
    collect_operational_observation,
    observation_queries,
)
from app.workflow_rollout_gate import validate_workflow_rollout_report
from scripts.collect_workflow_observation import _prometheus_origin


STARTED = datetime(2026, 8, 1, tzinfo=UTC)
ENDED = STARTED + timedelta(hours=24)


def test_stable_queries_use_exact_observation_window_and_low_cardinality() -> None:
    queries = observation_queries(STARTED, ENDED)
    assert set(queries) == {
        "workflow-v2-completed-window-v1",
        "workflow-v2-attempted-window-v1",
        "workflow-v2-p95-window-v1",
        "workflow-v2-cost-window-v1",
    }
    assert all("[86400s]" in query for query in queries.values())
    assert all('workflow="chat-workflow-v2"' in query for query in queries.values())
    assert all("user_id" not in query for query in queries.values())

    retained = baseline_queries(STARTED, ENDED)
    assert set(retained) == BASELINE_QUERY_IDS
    assert set(queries) == WORKFLOW_QUERY_IDS
    assert all('workflow="chat-supervisor-v1"' in query for query in retained.values())


def test_operational_collection_derives_completion_latency_and_cost() -> None:
    values = {
        "workflow-v2-completed-window-v1": 120,
        "workflow-v2-attempted-window-v1": 125,
        "workflow-v2-p95-window-v1": 0.85,
        "workflow-v2-cost-window-v1": 1.68,
    }
    seen: list[str] = []

    def query_scalar(query_id, query, ended_at):
        assert query
        assert ended_at == ENDED
        seen.append(query_id)
        return values[query_id]

    observed, query_ids = collect_operational_observation(
        STARTED, ENDED, query_scalar
    )
    assert query_ids == seen
    assert observed == {
        "completed_requests": 120,
        "completion_rate": 0.96,
        "p95_latency_ms": 850.0,
        "cost_per_completed_training_action_usd": 0.014,
    }


def test_retained_supervisor_collection_uses_comparable_metrics() -> None:
    values = {
        "retained-supervisor-completed-window-v1": 110,
        "retained-supervisor-attempted-window-v1": 112,
        "retained-supervisor-p95-window-v1": 1.2,
        "retained-supervisor-cost-window-v1": 2.2,
    }

    observed, query_ids = collect_baseline_operational_observation(
        STARTED,
        ENDED,
        lambda query_id, _query, _ended_at: values[query_id],
    )

    assert set(query_ids) == BASELINE_QUERY_IDS
    assert observed == {
        "completed_requests": 110,
        "completion_rate": 110 / 112,
        "p95_latency_ms": 1200.0,
        "cost_per_completed_training_action_usd": 0.02,
    }


def test_draft_cannot_self_approve_retirement() -> None:
    draft = build_observation_draft(
        release_id="production-1",
        release_version="abc123",
        baseline_started_at=STARTED - timedelta(hours=24),
        baseline_ended_at=STARTED,
        started_at=STARTED,
        ended_at=ENDED,
        baseline_quality_pass_rate=1.0,
        baseline_operational={
            "completed_requests": 110,
            "completion_rate": 0.95,
            "p95_latency_ms": 1000,
            "cost_per_completed_training_action_usd": 0.02,
        },
        operational={
            "completed_requests": 120,
            "completion_rate": 0.96,
            "p95_latency_ms": 850,
            "cost_per_completed_training_action_usd": 0.014,
        },
        metrics_source="https://prometheus.example.test",
        query_ids=sorted(BASELINE_QUERY_IDS | WORKFLOW_QUERY_IDS),
    )
    errors = validate_workflow_rollout_report(draft)
    assert "zero_tolerance_failures must equal 0" in errors
    assert "rollback.verified must be true" in errors
    assert "approval.status must be approved" in errors
    assert "evidence.quality_report_sha256 must be a SHA-256 digest" in errors


def test_prometheus_origin_rejects_embedded_credentials() -> None:
    assert _prometheus_origin("https://metrics.example.test:9090/") == (
        "https://metrics.example.test:9090"
    )
    with pytest.raises(Exception, match="must not contain credentials"):
        _prometheus_origin("https://operator:secret@metrics.example.test")


def test_observation_window_must_cover_24_hours() -> None:
    with pytest.raises(ValueError, match="at least 24 hours"):
        observation_queries(STARTED, STARTED + timedelta(hours=23, minutes=59))
