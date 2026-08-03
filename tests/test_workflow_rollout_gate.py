"""工作流灰度放行门禁的测试。"""

import json
from copy import deepcopy
from pathlib import Path

from app.workflow_rollout_gate import validate_workflow_rollout_report
from app.workflow_observation import BASELINE_QUERY_IDS, WORKFLOW_QUERY_IDS


def approved_report() -> dict[str, object]:
    return {
        "schema_version": "workflow-v2-rollout-observation-v2",
        "workflow_version": "chat-workflow-v2",
        "environment": "production",
        "evidence_type": "production-observability",
        "release_id": "production-workflow-v2-001",
        "release_version": "v2.0.0",
        "baseline_workflow_version": "chat-supervisor-v1",
        "baseline_observation_window": {
            "started_at": "2026-07-30T00:00:00Z",
            "ended_at": "2026-07-31T00:00:00Z",
            "completed_requests": 100,
        },
        "observation_window": {
            "started_at": "2026-08-01T00:00:00Z",
            "ended_at": "2026-08-02T00:00:00Z",
            "completed_requests": 100,
        },
        "zero_tolerance_failures": 0,
        "rollback": {
            "stage": "off",
            "verified": True,
            "exercise_release_id": "production-workflow-v2-rollback-001",
        },
        "baseline": {
            "quality_pass_rate": 0.99,
            "completion_rate": 0.98,
            "p95_latency_ms": 1200,
            "cost_per_completed_training_action_usd": 0.02,
        },
        "observed": {
            "quality_pass_rate": 0.99,
            "completion_rate": 0.99,
            "p95_latency_ms": 1100,
            "cost_per_completed_training_action_usd": 0.018,
        },
        "evidence": {
            "metrics_source": "prometheus-production",
            "query_ids": sorted(BASELINE_QUERY_IDS | WORKFLOW_QUERY_IDS),
            "quality_report_sha256": "a" * 64,
            "contains_user_content": False,
        },
        "approval": {
            "status": "approved",
            "approved_by": "release-manager@example.test",
            "approved_at": "2026-08-02T01:00:00Z",
            "ticket": "REL-123",
        },
    }


def test_approved_production_observation_and_release_ledger_pass() -> None:
    report = approved_report()
    release = {
        "release_id": report["release_id"],
        "version": report["release_version"],
        "environment": "production",
        "status": "succeeded",
        "completed_at": "2026-07-31T23:00:00Z",
    }
    rollback_release = {
        "release_id": "production-workflow-v2-rollback-001",
        "environment": "production",
        "status": "rolled_back",
    }

    assert validate_workflow_rollout_report(
        report, release=release, rollback_release=rollback_release
    ) == []


def test_gate_rejects_regression_short_window_and_repository_self_approval() -> None:
    report = approved_report()
    report["observation_window"] = {
        "started_at": "2026-08-01T00:00:00Z",
        "ended_at": "2026-08-01T01:00:00Z",
        "completed_requests": 5,
    }
    report["observed"] = deepcopy(report["observed"])
    report["observed"]["completion_rate"] = 0.5
    report["approval"] = deepcopy(report["approval"])
    report["approval"]["approved_by"] = "repository-quality-gate"

    errors = validate_workflow_rollout_report(report)

    assert any("at least 24 hours" in error for error in errors)
    assert any("at least 100" in error for error in errors)
    assert any("completion_rate regresses" in error for error in errors)
    assert any("external approver" in error for error in errors)


def test_gate_requires_traceable_redacted_observability_evidence() -> None:
    report = approved_report()
    report["evidence"] = {
        "metrics_source": "",
        "query_ids": [],
        "quality_report_sha256": "not-a-digest",
        "contains_user_content": True,
    }

    errors = validate_workflow_rollout_report(report)

    assert any("metrics_source" in error for error in errors)
    assert any("query_ids" in error for error in errors)
    assert any("SHA-256" in error for error in errors)
    assert any("contains_user_content" in error for error in errors)


def test_gate_rejects_missing_comparable_supervisor_window() -> None:
    report = approved_report()
    report["baseline_observation_window"] = {
        "started_at": "2026-07-30T00:00:00Z",
        "ended_at": "2026-07-30T01:00:00Z",
        "completed_requests": 5,
    }
    report["evidence"] = deepcopy(report["evidence"])
    report["evidence"]["query_ids"] = sorted(WORKFLOW_QUERY_IDS)

    errors = validate_workflow_rollout_report(report)

    assert any(
        "baseline observation window must be at least 24 hours" in error
        for error in errors
    )
    assert any(
        "baseline_observation_window.completed_requests must be at least 100"
        in error
        for error in errors
    )
    assert any("must include retained Supervisor" in error for error in errors)


def test_repository_template_is_deliberately_not_approval_evidence() -> None:
    template = json.loads(
        Path("eval/reports/workflow-v2-production-observation.template.json")
        .read_text(encoding="utf-8")
    )

    assert validate_workflow_rollout_report(template)
    assert template["approval"]["status"] == "pending"
