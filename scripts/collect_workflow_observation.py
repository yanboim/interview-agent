"""Collect a non-approving Workflow V2 observation draft from Prometheus."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.workflow_observation import (
    build_observation_draft,
    collect_baseline_operational_observation,
    collect_operational_observation,
)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def _prometheus_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise argparse.ArgumentTypeError("Prometheus URL must use HTTP(S)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError(
            "Prometheus URL must not contain credentials, query, or fragment"
        )
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect sanitized Workflow V2 operational evidence."
    )
    parser.add_argument("--prometheus-url", required=True, type=_prometheus_origin)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--baseline-started-at", required=True, type=_timestamp)
    parser.add_argument("--baseline-ended-at", required=True, type=_timestamp)
    parser.add_argument("--started-at", required=True, type=_timestamp)
    parser.add_argument("--ended-at", required=True, type=_timestamp)
    parser.add_argument(
        "--quality-baseline",
        type=Path,
        default=Path("eval/reports/model-routing-canary-approved.json"),
        help="Deterministic quality baseline; production metrics come from Prometheus.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".var/workflow-v2-production-observation.draft.json"),
    )
    return parser


def _query_client(origin: str):
    client = httpx.Client(timeout=15.0)

    def query_scalar(query_id: str, query: str, ended_at: datetime) -> float:
        del query_id
        response = client.get(
            f"{origin}/api/v1/query",
            params={"query": query, "time": ended_at.timestamp()},
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("data", {}).get("result", [])
        if payload.get("status") != "success" or len(result) != 1:
            raise RuntimeError("Prometheus query did not return one scalar series")
        value = result[0].get("value", [])
        if len(value) != 2:
            raise RuntimeError("Prometheus scalar result is malformed")
        return float(value[1])

    return client, query_scalar


def main() -> None:
    args = build_parser().parse_args()
    baseline_report = json.loads(
        args.quality_baseline.read_text(encoding="utf-8")
    )
    baseline = baseline_report.get("baseline")
    baseline_quality = (
        baseline.get("quality_pass_rate")
        if isinstance(baseline, dict)
        else None
    )
    if (
        baseline_report.get("evidence_type") != "deterministic-internal-canary"
        or isinstance(baseline_quality, bool)
        or not isinstance(baseline_quality, (int, float))
    ):
        raise SystemExit("workflow_observation=blocked code=baseline_invalid")

    client, query_scalar = _query_client(args.prometheus_url)
    try:
        baseline_operational, baseline_query_ids = (
            collect_baseline_operational_observation(
                args.baseline_started_at,
                args.baseline_ended_at,
                query_scalar,
            )
        )
        operational, query_ids = collect_operational_observation(
            args.started_at,
            args.ended_at,
            query_scalar,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        del exc
        raise SystemExit(
            "workflow_observation=blocked code=metrics_collection_failed"
        ) from None
    finally:
        client.close()

    draft = build_observation_draft(
        release_id=args.release_id,
        release_version=args.release_version,
        baseline_started_at=args.baseline_started_at,
        baseline_ended_at=args.baseline_ended_at,
        started_at=args.started_at,
        ended_at=args.ended_at,
        baseline_quality_pass_rate=float(baseline_quality),
        baseline_operational=baseline_operational,
        operational=operational,
        metrics_source=args.prometheus_url,
        query_ids=[*baseline_query_ids, *query_ids],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "workflow_observation=draft "
        f"baseline_completed_requests={baseline_operational['completed_requests']} "
        f"completed_requests={operational['completed_requests']}"
    )


if __name__ == "__main__":
    main()
