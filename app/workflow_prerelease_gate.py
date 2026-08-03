"""Fail-closed policy for retiring Supervisor before the first public release."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


REPORT_SCHEMA = "workflow-v2-prerelease-acceptance-v1"
WORKFLOW_VERSION = "chat-workflow-v2"
REQUIRED_SPECIALISTS = {"knowledge", "interviewer", "evaluator", "planner"}
MIN_DETERMINISTIC_CASES = 230
MIN_LIVE_CASES = 6
MIN_MULTI_INTENT_CASES = 2
DETERMINISTIC_REPORT_PATH = "eval/reports/agent-stack-ci.json"
LIVE_REPORT_PATH = ".var/workflow-v2-prerelease-live-acceptance.json"


def _timestamp(value: object, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed.astimezone(UTC)


def _digest(value: object, field: str, errors: list[str]) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", str(value or "")):
        errors.append(f"{field} must be a SHA-256 digest")


def validate_workflow_prerelease_report(
    report: Mapping[str, Any],
    *,
    release: Mapping[str, Any] | None = None,
    rollback_release: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return every reason pre-release Supervisor retirement must stop."""
    errors: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA:
        errors.append(f"schema_version must be {REPORT_SCHEMA}")
    if report.get("workflow_version") != WORKFLOW_VERSION:
        errors.append(f"workflow_version must be {WORKFLOW_VERSION}")
    if report.get("lifecycle_stage") != "prerelease":
        errors.append("lifecycle_stage must be prerelease")
    if report.get("contains_production_user_content") is not False:
        errors.append("contains_production_user_content must be false")

    release_id = str(report.get("release_id") or "").strip()
    release_version = str(report.get("release_version") or "").strip()
    if not release_id:
        errors.append("release_id is required")
    if not release_version:
        errors.append("release_version is required")

    deterministic = report.get("deterministic_evaluation")
    if not isinstance(deterministic, Mapping):
        errors.append("deterministic_evaluation is required")
    else:
        if deterministic.get("report_path") != DETERMINISTIC_REPORT_PATH:
            errors.append(
                f"deterministic_evaluation.report_path must be {DETERMINISTIC_REPORT_PATH}"
            )
        _digest(deterministic.get("report_sha256"), "deterministic_evaluation.report_sha256", errors)
        total = deterministic.get("total_cases")
        passed = deterministic.get("passed_cases")
        if isinstance(total, bool) or not isinstance(total, int) or total < MIN_DETERMINISTIC_CASES:
            errors.append(
                f"deterministic_evaluation.total_cases must be at least {MIN_DETERMINISTIC_CASES}"
            )
        if isinstance(passed, bool) or not isinstance(passed, int) or passed != total:
            errors.append("deterministic_evaluation must pass every case")
        if deterministic.get("zero_tolerance_failures") != 0:
            errors.append("deterministic_evaluation.zero_tolerance_failures must equal 0")
        if deterministic.get("gate_passed") is not True:
            errors.append("deterministic_evaluation.gate_passed must be true")

    live = report.get("live_acceptance")
    live_ended: datetime | None = None
    if not isinstance(live, Mapping):
        errors.append("live_acceptance is required")
    else:
        if live.get("report_path") != LIVE_REPORT_PATH:
            errors.append(f"live_acceptance.report_path must be {LIVE_REPORT_PATH}")
        _digest(live.get("report_sha256"), "live_acceptance.report_sha256", errors)
        live_ended = _timestamp(live.get("ended_at"), "live_acceptance.ended_at", errors)
        total = live.get("total_cases")
        passed = live.get("passed_cases")
        if isinstance(total, bool) or not isinstance(total, int) or total < MIN_LIVE_CASES:
            errors.append(f"live_acceptance.total_cases must be at least {MIN_LIVE_CASES}")
        if isinstance(passed, bool) or not isinstance(passed, int) or passed != total:
            errors.append("live_acceptance must pass every case")
        multi = live.get("multi_intent_cases")
        if isinstance(multi, bool) or not isinstance(multi, int) or multi < MIN_MULTI_INTENT_CASES:
            errors.append(
                f"live_acceptance.multi_intent_cases must be at least {MIN_MULTI_INTENT_CASES}"
            )
        coverage = live.get("specialist_coverage")
        if not isinstance(coverage, list) or set(coverage) != REQUIRED_SPECIALISTS:
            errors.append("live_acceptance.specialist_coverage must include every specialist")
        if live.get("zero_tolerance_failures") != 0:
            errors.append("live_acceptance.zero_tolerance_failures must equal 0")
        if live.get("contains_user_content") is not False:
            errors.append("live_acceptance.contains_user_content must be false")
        if live.get("cleanup_verified") is not True:
            errors.append("live_acceptance.cleanup_verified must be true")

    rollback = report.get("rollback")
    if not isinstance(rollback, Mapping):
        errors.append("rollback is required")
    else:
        if rollback.get("stage") != "off" or rollback.get("verified") is not True:
            errors.append("rollback off-stage exercise must be verified")
        if not str(rollback.get("exercise_release_id") or "").strip():
            errors.append("rollback.exercise_release_id is required")
        _digest(rollback.get("app_artifact_sha256"), "rollback.app_artifact_sha256", errors)
        _digest(rollback.get("worker_artifact_sha256"), "rollback.worker_artifact_sha256", errors)

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, Mapping):
        errors.append("artifacts are required")
    else:
        for field in ("app_image", "worker_image"):
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(artifacts.get(field) or "")):
                errors.append(f"artifacts.{field} must be an immutable image ID")

    approval = report.get("approval")
    if not isinstance(approval, Mapping):
        errors.append("approval is required")
    else:
        if approval.get("status") != "approved":
            errors.append("approval.status must be approved")
        approved_by = str(approval.get("approved_by") or "").strip()
        if not approved_by or approved_by in {
            "repository-quality-gate",
            "codex",
            "deployment",
        }:
            errors.append("approval.approved_by must identify the project owner")
        if not str(approval.get("ticket") or "").strip():
            errors.append("approval.ticket is required")
        approved_at = _timestamp(approval.get("approved_at"), "approval.approved_at", errors)
        if approved_at and live_ended and approved_at < live_ended:
            errors.append("approval must occur after live acceptance")

    if release is not None:
        if release.get("release_id") != release_id:
            errors.append("release ledger ID does not match report")
        if release.get("version") != release_version:
            errors.append("release ledger version does not match report")
        if release.get("status") != "succeeded":
            errors.append("release ledger status must be succeeded")
        if isinstance(artifacts, Mapping):
            if release.get("app_image") != artifacts.get("app_image"):
                errors.append("release ledger app image does not match report")
            if release.get("worker_image") != artifacts.get("worker_image"):
                errors.append("release ledger worker image does not match report")
    if rollback_release is not None:
        expected_id = rollback.get("exercise_release_id") if isinstance(rollback, Mapping) else None
        if rollback_release.get("release_id") != expected_id:
            errors.append("rollback release ledger ID does not match report")
        if rollback_release.get("status") != "rolled_back":
            errors.append("rollback release ledger status must be rolled_back")
    return errors


def _load_evidence(
    root: Path,
    relative_path: str,
    expected_digest: object,
    field: str,
    errors: list[str],
) -> Mapping[str, Any] | None:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{field} escapes evidence root")
        return None
    try:
        payload = candidate.read_bytes()
    except OSError:
        errors.append(f"{field} is missing")
        return None
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != expected_digest:
        errors.append(f"{field} SHA-256 does not match report")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{field} is not valid JSON")
        return None
    if not isinstance(decoded, Mapping):
        errors.append(f"{field} must contain a JSON object")
        return None
    return decoded


def _contains_forbidden_content_key(value: object) -> bool:
    forbidden = {"prompt", "answer", "message", "content", "username", "user_id"}
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in forbidden
            or _contains_forbidden_content_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_content_key(item) for item in value)
    return False


def validate_workflow_prerelease_evidence_files(
    report: Mapping[str, Any],
    *,
    evidence_root: Path,
) -> list[str]:
    """Verify the summarized claims against the exact sanitized evidence files."""
    errors: list[str] = []
    deterministic_summary = report.get("deterministic_evaluation")
    live_summary = report.get("live_acceptance")
    if not isinstance(deterministic_summary, Mapping) or not isinstance(
        live_summary, Mapping
    ):
        return ["evidence summaries are required"]

    deterministic = _load_evidence(
        evidence_root,
        DETERMINISTIC_REPORT_PATH,
        deterministic_summary.get("report_sha256"),
        "deterministic evidence",
        errors,
    )
    if deterministic is not None:
        groups = deterministic.get("groups")
        if (
            deterministic.get("schema_version") != "agent-evaluation-report-v1"
            or deterministic.get("execution_mode") != "application-stack"
            or deterministic.get("gate_passed") is not True
            or not isinstance(groups, Mapping)
        ):
            errors.append("deterministic evidence is not a passing application-stack report")
        else:
            group_values = [item for item in groups.values() if isinstance(item, Mapping)]
            total = sum(int(item.get("cases", 0)) for item in group_values)
            passed = sum(int(item.get("passed", 0)) for item in group_values)
            zero = sum(int(item.get("zero_tolerance_failures", 0)) for item in group_values)
            if len(group_values) != len(groups) or any(
                item.get("gate_passed") is not True for item in group_values
            ):
                errors.append("every deterministic evidence group must pass")
            if total != deterministic_summary.get("total_cases"):
                errors.append("deterministic evidence total does not match summary")
            if passed != deterministic_summary.get("passed_cases"):
                errors.append("deterministic evidence passed count does not match summary")
            if zero != deterministic_summary.get("zero_tolerance_failures"):
                errors.append("deterministic evidence zero-tolerance count does not match summary")

    live = _load_evidence(
        evidence_root,
        LIVE_REPORT_PATH,
        live_summary.get("report_sha256"),
        "live evidence",
        errors,
    )
    if live is not None:
        cases = live.get("cases")
        comparable_fields = (
            "ended_at",
            "total_cases",
            "passed_cases",
            "multi_intent_cases",
            "specialist_coverage",
            "zero_tolerance_failures",
            "contains_user_content",
        )
        if live.get("schema_version") != "workflow-v2-prerelease-live-v1":
            errors.append("live evidence schema is invalid")
        for field in comparable_fields:
            if live.get(field) != live_summary.get(field):
                errors.append(f"live evidence {field} does not match summary")
        if (
            not isinstance(cases, list)
            or len(cases) != live.get("total_cases")
            or any(
                not isinstance(case, Mapping) or case.get("status") != "passed"
                for case in cases
            )
        ):
            errors.append("every live evidence case must be present and passed")
        if live.get("api_conversation_cleanup_verified") is not True or live.get(
            "identity_cleanup_verified"
        ) is not True:
            errors.append("live evidence cleanup must be verified at API and identity levels")
        if _contains_forbidden_content_key(live):
            errors.append("live evidence contains a forbidden content or identity field")
    return errors
