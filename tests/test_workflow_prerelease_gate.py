"""Pre-release Supervisor retirement gate tests."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from app.workflow_prerelease_gate import (
    validate_workflow_prerelease_evidence_files,
    validate_workflow_prerelease_report,
)


def approved_report() -> dict[str, object]:
    return {
        "schema_version": "workflow-v2-prerelease-acceptance-v1",
        "workflow_version": "chat-workflow-v2",
        "lifecycle_stage": "prerelease",
        "release_id": "production-r4",
        "release_version": "workflow-v2-r4",
        "contains_production_user_content": False,
        "deterministic_evaluation": {
            "report_path": "eval/reports/agent-stack-ci.json",
            "report_sha256": "a" * 64,
            "total_cases": 230,
            "passed_cases": 230,
            "zero_tolerance_failures": 0,
            "gate_passed": True,
        },
        "live_acceptance": {
            "report_path": ".var/workflow-v2-prerelease-live-acceptance.json",
            "report_sha256": "b" * 64,
            "ended_at": "2026-08-02T10:00:00Z",
            "total_cases": 6,
            "passed_cases": 6,
            "multi_intent_cases": 2,
            "specialist_coverage": ["knowledge", "interviewer", "evaluator", "planner"],
            "zero_tolerance_failures": 0,
            "contains_user_content": False,
            "cleanup_verified": True,
        },
        "rollback": {
            "stage": "off",
            "verified": True,
            "exercise_release_id": "rollback-r2",
            "app_artifact_sha256": "c" * 64,
            "worker_artifact_sha256": "d" * 64,
        },
        "artifacts": {
            "app_image": "sha256:" + "e" * 64,
            "worker_image": "sha256:" + "f" * 64,
        },
        "approval": {
            "status": "approved",
            "approved_by": "project-owner-via-codex-thread",
            "approved_at": "2026-08-02T10:01:00Z",
            "ticket": "OWNER-APPROVAL-1",
        },
    }


def test_approved_prerelease_evidence_and_ledgers_pass() -> None:
    report = approved_report()
    release = {
        "release_id": "production-r4",
        "version": "workflow-v2-r4",
        "status": "succeeded",
        "app_image": report["artifacts"]["app_image"],
        "worker_image": report["artifacts"]["worker_image"],
    }
    rollback = {"release_id": "rollback-r2", "status": "rolled_back"}

    assert validate_workflow_prerelease_report(
        report, release=release, rollback_release=rollback
    ) == []


def test_prerelease_gate_rejects_small_or_incomplete_live_cohort() -> None:
    report = approved_report()
    report["live_acceptance"] = deepcopy(report["live_acceptance"])
    report["live_acceptance"].update(
        total_cases=5,
        passed_cases=4,
        multi_intent_cases=1,
        specialist_coverage=["knowledge"],
        cleanup_verified=False,
    )

    errors = validate_workflow_prerelease_report(report)

    assert any("at least 6" in error for error in errors)
    assert any("pass every case" in error for error in errors)
    assert any("at least 2" in error for error in errors)
    assert any("every specialist" in error for error in errors)
    assert any("cleanup_verified" in error for error in errors)


def test_prerelease_gate_rejects_self_approval_and_mutable_images() -> None:
    report = approved_report()
    report["approval"] = deepcopy(report["approval"])
    report["approval"]["approved_by"] = "codex"
    report["artifacts"] = {"app_image": "latest", "worker_image": "latest"}

    errors = validate_workflow_prerelease_report(report)

    assert any("project owner" in error for error in errors)
    assert sum("immutable image ID" in error for error in errors) == 2


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def test_evidence_files_are_hashed_and_recomputed(tmp_path: Path) -> None:
    report = approved_report()
    deterministic = {
        "schema_version": "agent-evaluation-report-v1",
        "execution_mode": "application-stack",
        "gate_passed": True,
        "groups": {
            "routing": {
                "cases": 230,
                "passed": 230,
                "zero_tolerance_failures": 0,
                "gate_passed": True,
            }
        },
    }
    live = {
        "schema_version": "workflow-v2-prerelease-live-v1",
        "ended_at": report["live_acceptance"]["ended_at"],
        "total_cases": 6,
        "passed_cases": 6,
        "multi_intent_cases": 2,
        "specialist_coverage": ["knowledge", "interviewer", "evaluator", "planner"],
        "zero_tolerance_failures": 0,
        "contains_user_content": False,
        "api_conversation_cleanup_verified": True,
        "identity_cleanup_verified": True,
        "cases": [{"case_id": f"case-{index}", "status": "passed"} for index in range(6)],
    }
    report["deterministic_evaluation"]["report_sha256"] = _write_json(
        tmp_path / "eval/reports/agent-stack-ci.json", deterministic
    )
    report["live_acceptance"]["report_sha256"] = _write_json(
        tmp_path / ".var/workflow-v2-prerelease-live-acceptance.json", live
    )

    assert validate_workflow_prerelease_evidence_files(
        report, evidence_root=tmp_path
    ) == []

    live["cases"][0]["prompt"] = "must not be retained"
    _write_json(tmp_path / ".var/workflow-v2-prerelease-live-acceptance.json", live)
    errors = validate_workflow_prerelease_evidence_files(report, evidence_root=tmp_path)
    assert any("SHA-256" in error for error in errors)
    assert any("forbidden content" in error for error in errors)
