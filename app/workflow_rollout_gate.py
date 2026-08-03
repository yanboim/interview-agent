"""Workflow V2 生产观察与 Supervisor 退役的纯验证策略。"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping

from app.workflow_observation import (
    BASELINE_QUERY_IDS,
    BASELINE_WORKFLOW_NAME,
    WORKFLOW_QUERY_IDS,
)


REPORT_SCHEMA = "workflow-v2-rollout-observation-v2"
WORKFLOW_VERSION = "chat-workflow-v2"
MIN_PRODUCTION_OBSERVATION_HOURS = 24
MIN_PRODUCTION_COMPLETED_REQUESTS = 100
METRIC_FIELDS = (
    "quality_pass_rate",
    "completion_rate",
    "p95_latency_ms",
    "cost_per_completed_training_action_usd",
)


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


def _number(
    mapping: Mapping[str, Any], field: str, prefix: str, errors: list[str]
) -> float | None:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{prefix}.{field} must be numeric")
        return None
    number = float(value)
    if number < 0:
        errors.append(f"{prefix}.{field} must be non-negative")
        return None
    return number


def validate_workflow_rollout_report(
    report: Mapping[str, Any],
    *,
    release: Mapping[str, Any] | None = None,
    rollback_release: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return every reason the report cannot authorize Supervisor retirement."""
    errors: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA:
        errors.append(f"schema_version must be {REPORT_SCHEMA}")
    if report.get("workflow_version") != WORKFLOW_VERSION:
        errors.append(f"workflow_version must be {WORKFLOW_VERSION}")
    if report.get("baseline_workflow_version") != BASELINE_WORKFLOW_NAME:
        errors.append(
            f"baseline_workflow_version must be {BASELINE_WORKFLOW_NAME}"
        )
    if report.get("environment") != "production":
        errors.append("environment must be production")
    if report.get("evidence_type") != "production-observability":
        errors.append("evidence_type must be production-observability")

    release_id = report.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        errors.append("release_id is required")

    window = report.get("observation_window")
    baseline_window = report.get("baseline_observation_window")
    baseline_started: datetime | None = None
    baseline_ended: datetime | None = None
    if not isinstance(baseline_window, Mapping):
        errors.append("baseline_observation_window is required")
    else:
        baseline_started = _timestamp(
            baseline_window.get("started_at"),
            "baseline_observation_window.started_at",
            errors,
        )
        baseline_ended = _timestamp(
            baseline_window.get("ended_at"),
            "baseline_observation_window.ended_at",
            errors,
        )
        if baseline_started and baseline_ended:
            baseline_hours = (
                baseline_ended - baseline_started
            ).total_seconds() / 3600
            if baseline_hours < MIN_PRODUCTION_OBSERVATION_HOURS:
                errors.append(
                    "baseline observation window must be at least "
                    f"{MIN_PRODUCTION_OBSERVATION_HOURS} hours"
                )
        baseline_completed = baseline_window.get("completed_requests")
        if isinstance(baseline_completed, bool) or not isinstance(
            baseline_completed, int
        ):
            errors.append(
                "baseline_observation_window.completed_requests must be an integer"
            )
        elif baseline_completed < MIN_PRODUCTION_COMPLETED_REQUESTS:
            errors.append(
                "baseline_observation_window.completed_requests must be at least "
                f"{MIN_PRODUCTION_COMPLETED_REQUESTS}"
            )
    started: datetime | None = None
    ended: datetime | None = None
    if not isinstance(window, Mapping):
        errors.append("observation_window is required")
    else:
        started = _timestamp(
            window.get("started_at"), "observation_window.started_at", errors
        )
        ended = _timestamp(
            window.get("ended_at"), "observation_window.ended_at", errors
        )
        if started and ended:
            hours = (ended - started).total_seconds() / 3600
            if hours < MIN_PRODUCTION_OBSERVATION_HOURS:
                errors.append(
                    "observation window must be at least "
                    f"{MIN_PRODUCTION_OBSERVATION_HOURS} hours"
                )
        completed = window.get("completed_requests")
        if isinstance(completed, bool) or not isinstance(completed, int):
            errors.append("observation_window.completed_requests must be an integer")
        elif completed < MIN_PRODUCTION_COMPLETED_REQUESTS:
            errors.append(
                "observation_window.completed_requests must be at least "
                f"{MIN_PRODUCTION_COMPLETED_REQUESTS}"
            )
    if baseline_ended and started and baseline_ended > started:
        errors.append(
            "retained Supervisor baseline must end before Workflow V2 observation starts"
        )

    if report.get("zero_tolerance_failures") != 0:
        errors.append("zero_tolerance_failures must equal 0")

    rollback = report.get("rollback")
    if not isinstance(rollback, Mapping):
        errors.append("rollback evidence is required")
    else:
        if rollback.get("stage") != "off":
            errors.append("rollback.stage must be off")
        if rollback.get("verified") is not True:
            errors.append("rollback.verified must be true")
        if not str(rollback.get("exercise_release_id") or "").strip():
            errors.append("rollback.exercise_release_id is required")

    baseline = report.get("baseline")
    observed = report.get("observed")
    if not isinstance(baseline, Mapping) or not isinstance(observed, Mapping):
        errors.append("baseline and observed metrics are required")
    else:
        values: dict[str, tuple[float | None, float | None]] = {}
        for field in METRIC_FIELDS:
            values[field] = (
                _number(baseline, field, "baseline", errors),
                _number(observed, field, "observed", errors),
            )
        for field in ("quality_pass_rate", "completion_rate"):
            base, current = values[field]
            if base is not None and current is not None and current < base:
                errors.append(f"observed.{field} regresses from baseline")
            if current is not None and current > 1:
                errors.append(f"observed.{field} must be at most 1")
        for field in (
            "p95_latency_ms",
            "cost_per_completed_training_action_usd",
        ):
            base, current = values[field]
            if base is not None and current is not None and current > base:
                errors.append(f"observed.{field} regresses from baseline")

    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        errors.append("traceable observability evidence is required")
    else:
        if not str(evidence.get("metrics_source") or "").strip():
            errors.append("evidence.metrics_source is required")
        query_ids = evidence.get("query_ids")
        if (
            not isinstance(query_ids, list)
            or not query_ids
            or any(not isinstance(item, str) or not item.strip() for item in query_ids)
        ):
            errors.append("evidence.query_ids must contain stable query identifiers")
        elif not (BASELINE_QUERY_IDS | WORKFLOW_QUERY_IDS).issubset(
            set(query_ids)
        ):
            errors.append(
                "evidence.query_ids must include retained Supervisor and Workflow V2 queries"
            )
        digest = str(evidence.get("quality_report_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append("evidence.quality_report_sha256 must be a SHA-256 digest")
        if evidence.get("contains_user_content") is not False:
            errors.append("evidence.contains_user_content must be false")

    approval = report.get("approval")
    if not isinstance(approval, Mapping):
        errors.append("approval is required")
    else:
        if approval.get("status") != "approved":
            errors.append("approval.status must be approved")
        approved_by = str(approval.get("approved_by") or "").strip()
        if not approved_by or approved_by == "repository-quality-gate":
            errors.append("approval.approved_by must identify an external approver")
        if not str(approval.get("ticket") or "").strip():
            errors.append("approval.ticket is required")
        approved_at = _timestamp(
            approval.get("approved_at"), "approval.approved_at", errors
        )
        if approved_at and ended and approved_at < ended:
            errors.append("approval must occur after the observation window")

    if release is not None:
        if release.get("release_id") != release_id:
            errors.append("release ledger ID does not match report")
        if release.get("environment") != "production":
            errors.append("release ledger environment must be production")
        if release.get("status") != "succeeded":
            errors.append("release ledger status must be succeeded")
        report_version = str(report.get("release_version") or "").strip()
        if not report_version or release.get("version") != report_version:
            errors.append("release ledger version does not match report")
        release_completed = _timestamp(
            release.get("completed_at"), "release.completed_at", errors
        )
        if release_completed and started and release_completed > started:
            errors.append("production release must complete before observation starts")
        if release_completed and baseline_ended and baseline_ended > release_completed:
            errors.append(
                "retained Supervisor baseline must complete before production release"
            )
    if rollback_release is not None:
        expected_rollback_id = (
            rollback.get("exercise_release_id")
            if isinstance(rollback, Mapping)
            else None
        )
        if rollback_release.get("release_id") != expected_rollback_id:
            errors.append("rollback release ledger ID does not match report")
        if rollback_release.get("environment") != "production":
            errors.append("rollback release environment must be production")
        if rollback_release.get("status") != "rolled_back":
            errors.append("rollback release status must be rolled_back")
    return errors
