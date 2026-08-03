"""评估 Workflow V2 代码定义路由的准确性。"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from app.model_routing import explicit_workflow_routes


def load_cases(path: Path) -> list[dict[str, str]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def selected_routes(query: str) -> list[str]:
    return [f"{route}_agent" for route in explicit_workflow_routes(query)]


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    correct = sum(bool(row["correct"]) for row in rows)
    total = len(rows)
    per_agent: dict[str, dict[str, int]] = {}
    for row in rows:
        expected = str(row["expected"])
        bucket = per_agent.setdefault(expected, {"correct": 0, "total": 0})
        bucket["total"] += 1
        bucket["correct"] += int(bool(row["correct"]))
    return {
        "cases": total,
        "correct": correct,
        "routing_accuracy": round(correct / total, 4) if total else 0.0,
        "single_agent_specialist_routing_baseline": 0.0,
        "per_agent": {
            name: {
                **values,
                "accuracy": round(values["correct"] / values["total"], 4),
            }
            for name, values in per_agent.items()
        },
    }


def evaluate(cases: list[dict[str, str]]) -> dict[str, object]:
    rows = []
    for case in cases:
        routes = selected_routes(case["query"])
        actual = routes[0] if len(routes) == 1 else "+".join(routes)
        rows.append(
            {
                **case,
                "actual": actual,
                "correct": actual == case["expected"],
            }
        )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summarize(rows),
        "results": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate deterministic Workflow V2 routing."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("eval/agent_routing.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/reports/multi-agent-routing.json"),
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    cases = load_cases(args.cases)
    if args.limit > 0:
        cases = cases[: args.limit]
    report = evaluate(cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
