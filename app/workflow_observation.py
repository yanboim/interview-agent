"""Stable Prometheus evidence queries for Workflow V2 production observation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any


WORKFLOW_NAME = "chat-workflow-v2"
BASELINE_WORKFLOW_NAME = "chat-supervisor-v1"
QUERY_SUFFIXES = {
    "completed-window-v1": (
        'sum(increase(interview_agent_workflow_runs_total{{workflow="{workflow}",'
        'outcome="completed"}}[{window}]))'
    ),
    "attempted-window-v1": (
        'sum(increase(interview_agent_workflow_runs_total{{workflow="{workflow}"}}'
        "[{window}]))"
    ),
    "p95-window-v1": (
        "histogram_quantile(0.95, sum by (le) "
        '(increase(interview_agent_workflow_duration_seconds_bucket{{workflow="'
        '{workflow}"}}[{window}])))'
    ),
    "cost-window-v1": (
        'sum(increase(interview_agent_workflow_cost_usd_total{{workflow="'
        '{workflow}"}}[{window}]))'
    ),
}
WORKFLOW_QUERY_IDS = frozenset(f"workflow-v2-{suffix}" for suffix in QUERY_SUFFIXES)
BASELINE_QUERY_IDS = frozenset(
    f"retained-supervisor-{suffix}" for suffix in QUERY_SUFFIXES
)


def _workflow_queries(
    workflow: str,
    query_prefix: str,
    started_at: datetime,
    ended_at: datetime,
) -> dict[str, str]:
    seconds = int((ended_at - started_at).total_seconds())
    if seconds < 24 * 60 * 60:
        raise ValueError("observation window must be at least 24 hours")
    replacements = {"workflow": workflow, "window": f"{seconds}s"}
    return {
        f"{query_prefix}-{suffix}": template.format(**replacements)
        for suffix, template in QUERY_SUFFIXES.items()
    }


def observation_queries(started_at: datetime, ended_at: datetime) -> dict[str, str]:
    return _workflow_queries(
        WORKFLOW_NAME, "workflow-v2", started_at, ended_at
    )


def baseline_queries(started_at: datetime, ended_at: datetime) -> dict[str, str]:
    return _workflow_queries(
        BASELINE_WORKFLOW_NAME,
        "retained-supervisor",
        started_at,
        ended_at,
    )


def _collect_operational_observation(
    queries: Mapping[str, str],
    query_prefix: str,
    ended_at: datetime,
    query_scalar: Callable[[str, str, datetime], float],
) -> tuple[dict[str, float | int], list[str]]:
    values = {
        query_id: max(0.0, float(query_scalar(query_id, query, ended_at)))
        for query_id, query in queries.items()
    }
    completed = values[f"{query_prefix}-completed-window-v1"]
    attempted = values[f"{query_prefix}-attempted-window-v1"]
    return (
        {
            "completed_requests": int(completed),
            "completion_rate": completed / attempted if attempted else 0.0,
            "p95_latency_ms": values[f"{query_prefix}-p95-window-v1"] * 1000,
            "cost_per_completed_training_action_usd": (
                values[f"{query_prefix}-cost-window-v1"] / completed
                if completed
                else 0.0
            ),
        },
        list(queries),
    )


def collect_operational_observation(
    started_at: datetime,
    ended_at: datetime,
    query_scalar: Callable[[str, str, datetime], float],
) -> tuple[dict[str, float | int], list[str]]:
    """Execute fixed queries and derive bounded operational rollout metrics."""
    return _collect_operational_observation(
        observation_queries(started_at, ended_at),
        "workflow-v2",
        ended_at,
        query_scalar,
    )


def collect_baseline_operational_observation(
    started_at: datetime,
    ended_at: datetime,
    query_scalar: Callable[[str, str, datetime], float],
) -> tuple[dict[str, float | int], list[str]]:
    """Collect the same metrics for the retained production Supervisor path."""
    return _collect_operational_observation(
        baseline_queries(started_at, ended_at),
        "retained-supervisor",
        ended_at,
        query_scalar,
    )


def build_observation_draft(
    *,
    release_id: str,
    release_version: str,
    baseline_started_at: datetime,
    baseline_ended_at: datetime,
    started_at: datetime,
    ended_at: datetime,
    baseline_quality_pass_rate: float,
    baseline_operational: Mapping[str, float | int],
    operational: Mapping[str, float | int],
    metrics_source: str,
    query_ids: list[str],
) -> dict[str, Any]:
    """Build an intentionally non-approving draft around collected metrics."""
    return {
        "schema_version": "workflow-v2-rollout-observation-v2",
        "workflow_version": WORKFLOW_NAME,
        "environment": "production",
        "evidence_type": "production-observability",
        "release_id": release_id,
        "release_version": release_version,
        "baseline_workflow_version": BASELINE_WORKFLOW_NAME,
        "baseline_observation_window": {
            "started_at": baseline_started_at.isoformat(),
            "ended_at": baseline_ended_at.isoformat(),
            "completed_requests": int(
                baseline_operational["completed_requests"]
            ),
        },
        "observation_window": {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "completed_requests": int(operational["completed_requests"]),
        },
        "zero_tolerance_failures": -1,
        "rollback": {
            "stage": "off",
            "verified": False,
            "exercise_release_id": "",
        },
        "baseline": {
            "quality_pass_rate": float(baseline_quality_pass_rate),
            "completion_rate": float(baseline_operational["completion_rate"]),
            "p95_latency_ms": float(baseline_operational["p95_latency_ms"]),
            "cost_per_completed_training_action_usd": float(
                baseline_operational[
                    "cost_per_completed_training_action_usd"
                ]
            ),
        },
        "observed": {
            "quality_pass_rate": 0,
            "completion_rate": float(operational["completion_rate"]),
            "p95_latency_ms": float(operational["p95_latency_ms"]),
            "cost_per_completed_training_action_usd": float(
                operational["cost_per_completed_training_action_usd"]
            ),
        },
        "evidence": {
            "metrics_source": metrics_source,
            "query_ids": query_ids,
            "quality_report_sha256": "",
            "contains_user_content": False,
        },
        "approval": {
            "status": "pending",
            "approved_by": "",
            "approved_at": "",
            "ticket": "",
        },
    }
