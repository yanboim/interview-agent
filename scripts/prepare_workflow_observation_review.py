"""Prepare redacted Workflow V2 evidence for independent release review."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


QUALITY_REPORT_SCHEMA = "agent-evaluation-report-v1"


def prepare_review_report(
    draft: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    *,
    quality_report_bytes: bytes,
    rollback_release_id: str,
) -> dict[str, Any]:
    """Attach deterministic redacted evidence without granting approval."""
    if draft.get("schema_version") != "workflow-v2-rollout-observation-v2":
        raise ValueError("observation draft schema is invalid")
    if quality_report.get("schema_version") != QUALITY_REPORT_SCHEMA:
        raise ValueError("quality report schema is invalid")
    if quality_report.get("gate_passed") is not True:
        raise ValueError("quality report gate must pass")
    groups = quality_report.get("groups")
    if not isinstance(groups, Mapping) or not groups:
        raise ValueError("quality report groups are required")

    pass_rates: list[float] = []
    zero_tolerance_failures = 0
    for name, raw_group in groups.items():
        if not isinstance(raw_group, Mapping):
            raise ValueError(f"quality group {name} is invalid")
        if raw_group.get("gate_passed") is not True:
            raise ValueError(f"quality group {name} gate must pass")
        rate = raw_group.get("pass_rate")
        failures = raw_group.get("zero_tolerance_failures")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            raise ValueError(f"quality group {name} pass_rate is invalid")
        if not 0 <= float(rate) <= 1:
            raise ValueError(f"quality group {name} pass_rate is out of range")
        if isinstance(failures, bool) or not isinstance(failures, int):
            raise ValueError(
                f"quality group {name} zero_tolerance_failures is invalid"
            )
        pass_rates.append(float(rate))
        zero_tolerance_failures += failures
    if zero_tolerance_failures != 0:
        raise ValueError("quality report has zero-tolerance failures")

    normalized_rollback_id = rollback_release_id.strip()
    if not normalized_rollback_id:
        raise ValueError("rollback release ID is required")

    report = deepcopy(dict(draft))
    observed = report.get("observed")
    evidence = report.get("evidence")
    if not isinstance(observed, dict) or not isinstance(evidence, dict):
        raise ValueError("observation draft metrics/evidence are invalid")
    report["zero_tolerance_failures"] = 0
    report["rollback"] = {
        "stage": "off",
        "verified": True,
        "exercise_release_id": normalized_rollback_id,
    }
    observed["quality_pass_rate"] = min(pass_rates)
    evidence["quality_report_sha256"] = hashlib.sha256(
        quality_report_bytes
    ).hexdigest()
    evidence["contains_user_content"] = False
    report["approval"] = {
        "status": "pending",
        "approved_by": "",
        "approved_at": "",
        "ticket": "",
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare non-approving Workflow V2 review evidence."
    )
    parser.add_argument(
        "--draft",
        type=Path,
        default=Path(".var/workflow-v2-production-observation.draft.json"),
    )
    parser.add_argument(
        "--quality-report",
        type=Path,
        default=Path("eval/reports/agent-stack-ci.json"),
    )
    parser.add_argument("--rollback-release-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".var/workflow-v2-production-observation.review.json"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    quality_bytes = args.quality_report.read_bytes()
    report = prepare_review_report(
        json.loads(args.draft.read_text(encoding="utf-8")),
        json.loads(quality_bytes),
        quality_report_bytes=quality_bytes,
        rollback_release_id=args.rollback_release_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("workflow_observation=review_pending_external_approval")


if __name__ == "__main__":
    main()
