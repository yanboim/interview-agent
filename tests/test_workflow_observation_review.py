"""Tests for non-approving Workflow V2 review evidence preparation."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

import pytest

from app.workflow_observation import build_observation_draft
from scripts.prepare_workflow_observation_review import prepare_review_report


STARTED = datetime(2026, 8, 1, tzinfo=UTC)
ENDED = STARTED + timedelta(hours=24)


def draft() -> dict[str, object]:
    return build_observation_draft(
        release_id="production-r4",
        release_version="workflow-v2-r4",
        baseline_started_at=STARTED - timedelta(hours=24),
        baseline_ended_at=STARTED,
        started_at=STARTED,
        ended_at=ENDED,
        baseline_quality_pass_rate=0.95,
        baseline_operational={
            "completed_requests": 110,
            "completion_rate": 0.95,
            "p95_latency_ms": 1200,
            "cost_per_completed_training_action_usd": 0.02,
        },
        operational={
            "completed_requests": 120,
            "completion_rate": 0.96,
            "p95_latency_ms": 850,
            "cost_per_completed_training_action_usd": 0.014,
        },
        metrics_source="https://metrics.example.test",
        query_ids=[
            "retained-supervisor-completed-window-v1",
            "workflow-v2-completed-window-v1",
        ],
    )


def quality() -> dict[str, object]:
    return {
        "schema_version": "agent-evaluation-report-v1",
        "gate_passed": True,
        "groups": {
            "routing": {
                "pass_rate": 1.0,
                "zero_tolerance_failures": 0,
                "gate_passed": True,
            },
            "safety": {
                "pass_rate": 0.99,
                "zero_tolerance_failures": 0,
                "gate_passed": True,
            },
        },
    }


def test_prepares_redacted_evidence_but_cannot_self_approve() -> None:
    quality_report = quality()
    quality_bytes = json.dumps(quality_report, sort_keys=True).encode()

    report = prepare_review_report(
        draft(),
        quality_report,
        quality_report_bytes=quality_bytes,
        rollback_release_id="production-rollback-r2",
    )

    assert report["observed"]["quality_pass_rate"] == 0.99
    assert report["zero_tolerance_failures"] == 0
    assert report["rollback"] == {
        "stage": "off",
        "verified": True,
        "exercise_release_id": "production-rollback-r2",
    }
    assert len(report["evidence"]["quality_report_sha256"]) == 64
    assert report["evidence"]["contains_user_content"] is False
    assert report["approval"]["status"] == "pending"
    assert report["approval"]["approved_by"] == ""


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report.update(gate_passed=False), "gate must pass"),
        (
            lambda report: report["groups"]["safety"].update(
                zero_tolerance_failures=1
            ),
            "zero-tolerance failures",
        ),
        (
            lambda report: report["groups"]["safety"].update(gate_passed=False),
            "group safety gate must pass",
        ),
    ],
)
def test_rejects_insufficient_quality_evidence(mutation, message) -> None:
    quality_report = deepcopy(quality())
    mutation(quality_report)

    with pytest.raises(ValueError, match=message):
        prepare_review_report(
            draft(),
            quality_report,
            quality_report_bytes=b"quality",
            rollback_release_id="production-rollback-r2",
        )
