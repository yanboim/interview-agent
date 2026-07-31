import json
from copy import deepcopy
from pathlib import Path

from scripts.evaluate_agent_stack import (
    MINIMUM_COUNTS,
    REPORT_SCHEMA_VERSION,
    evaluate_suite,
    expand_cases,
    load_suite,
)


SUITE_PATH = Path("eval/agent_quality_suite.v1.json")


def test_frozen_agent_suite_meets_every_group_minimum():
    suite = load_suite(SUITE_PATH)
    cases = expand_cases(suite)

    assert {name: len(rows) for name, rows in cases.items()} == MINIMUM_COUNTS
    assert suite["dataset_version"]


def test_deterministic_agent_stack_report_schema_and_group_gates():
    report = evaluate_suite(load_suite(SUITE_PATH))

    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["provider"] == "deterministic-mock-v1"
    assert report["execution_mode"] == "application-stack"
    assert report["estimated_cost_usd"] == 0.0
    assert report["gate_passed"] is True
    assert all(group["gate_passed"] for group in report["groups"].values())
    assert report["groups"]["grounded_answer"]["results"][0]["provider_calls"] == 1


def test_zero_tolerance_safety_failure_fails_the_group_gate():
    suite = deepcopy(load_suite(SUITE_PATH))
    suite["groups"]["safety"]["templates"][0]["forbidden"] = "安全策略拒绝"
    report = evaluate_suite(suite)

    safety = report["groups"]["safety"]
    assert safety["zero_tolerance_failures"] > 0
    assert safety["gate_passed"] is False
    assert report["gate_passed"] is False


def test_human_calibration_dataset_is_versioned_and_privacy_reviewed():
    payload = json.loads(
        Path("eval/capability_calibration.v1.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "capability-calibration-dataset-v1"
    assert payload["review_status"] == "privacy_reviewed"
    assert len(payload["examples"]) >= 10
