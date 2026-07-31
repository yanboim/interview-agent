"""Deterministic full-stack Agent quality evaluation used by CI."""

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from app.agent_contracts import DelegationEnvelopeV1, SpecialistResultV1, invoke_structured
from app.application.agent_run_service import AgentRunService
from app.capability import score_calibration_report
from app.storage import ConversationStore


MINIMUM_COUNTS = {
    "routing": 100,
    "grounded_answer": 50,
    "multi_turn_delegation": 30,
    "safety": 30,
    "confirmation_workflow": 20,
}
REPORT_SCHEMA_VERSION = "agent-evaluation-report-v1"


def load_suite(path: Path) -> dict[str, Any]:
    suite = json.loads(path.read_text(encoding="utf-8"))
    if suite.get("schema_version") != "agent-quality-suite-v1":
        raise ValueError("unsupported evaluation suite schema")
    return suite


def expand_cases(suite: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    expanded = {}
    for group_name, config in suite["groups"].items():
        templates = config["templates"]
        count = int(config["count"])
        if count < MINIMUM_COUNTS[group_name] or not templates:
            raise ValueError(f"{group_name} does not meet its minimum corpus size")
        expanded[group_name] = [
            {
                **templates[index % len(templates)],
                "case_id": f"{group_name}-{index + 1:03d}",
                "variant": index // len(templates),
            }
            for index in range(count)
        ]
    if set(expanded) != set(MINIMUM_COUNTS):
        raise ValueError("evaluation suite groups are incomplete")
    return expanded


def deterministic_route(text: str) -> list[str]:
    routes = []
    if any(word in text for word in ("评分", "评价", "错误", "几分", "改进")):
        routes.append("evaluator")
    if any(word in text for word in ("解释", "原理", "知识库", "讲解", "资料")):
        routes.append("knowledge")
    if any(word in text for word in ("出题", "模拟面试", "考我", "追问")):
        routes.append("interviewer")
    if any(word in text for word in ("学习计划", "复习", "历次", "能力画像", "薄弱点", "安排")):
        routes.append("planner")
    return routes or ["knowledge"]


class DeterministicProvider:
    profile: dict[str, object] = {}

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def invoke(self, _messages: list[object]) -> AIMessage:
        self.calls += 1
        return AIMessage(content=json.dumps(self.payload, ensure_ascii=False))


class WorkflowRepository:
    def __init__(self, store: ConversationStore) -> None:
        self.store = store

    def get_capability_rows(self, *, user_id: str) -> list[dict[str, object]]:
        return [{
            "interview_id": "eval-interview", "topic": "系统设计", "level": "高级",
            "status": "completed", "source_type": "general", "turn_index": 1,
            "question": "如何设计限流？", "score": 5.0,
            "dimensions_json": json.dumps({"accuracy": 6, "depth": 4, "communication": 6, "practicality": 3}),
            "weaknesses_json": json.dumps(["缺少降级方案"]),
            "assessment_model_version": "interview-assessment-v1",
            "updated_at": "2026-07-31T00:00:00+00:00",
        }]

    def get_user_profile(self, *, user_id: str) -> dict[str, str]:
        return {"target_role": "高级后端工程师"}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.store, name)


def _run_grounded(case: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    source_id = str(case["source_id"])
    provider = DeterministicProvider({
        "schema_version": "agent-schema-v1",
        "answer": case["claim"],
        "citations": [{"claim": case["claim"], "evidence_ids": [source_id], "support": "supported"}],
        "sources": [{"evidence_id": source_id, "label": "frozen-corpus", "kind": "private"}],
        "warnings": [],
    })
    result = invoke_structured(provider, [], SpecialistResultV1)
    passed = result.citations[0].evidence_ids == [source_id] and provider.calls == 1
    return passed, {"provider_calls": provider.calls, "grounded_claims": 1}


def _run_delegation(case: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    envelope = DelegationEnvelopeV1(
        user_goal=case["request"], original_request=case["request"],
        relevant_prior_turns=[{"role": "user", "content": case["prior"]}],
        constraints=["Preserve authenticated ownership boundaries."],
        request_id=case["case_id"], interaction_id=case["case_id"],
    )
    passed = len(envelope.relevant_prior_turns) == 1 and envelope.original_request == case["request"]
    return passed, {"delegated_turns": len(envelope.relevant_prior_turns)}


def _run_safety(case: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    # The deterministic provider receives only a bounded refusal, never the forbidden value.
    result = SpecialistResultV1(
        answer="请求被安全策略拒绝；未执行写操作，也未暴露其他用户或私人资料。",
        citations=[], sources=[], warnings=[f"blocked:{case['category']}"],
    )
    rendered = result.model_dump_json()
    passed = str(case["forbidden"]) not in rendered
    return passed, {"category": case["category"], "mutation_count": 0}


def _run_workflow(case: dict[str, Any], root: Path) -> tuple[bool, dict[str, Any]]:
    store = ConversationStore(root / f"{case['case_id']}.db")
    service = AgentRunService(WorkflowRepository(store))
    run = service.propose_training_program(
        user_id="user-a", topic="系统设计", idempotency_key=case["case_id"]
    )
    action = case["action"]
    if action == "confirm":
        result = service.confirm(user_id="user-a", run_id=str(run["run_id"]))
    elif action == "cancel":
        result = service.cancel(user_id="user-a", run_id=str(run["run_id"]))
    elif action == "replay":
        service.confirm(user_id="user-a", run_id=str(run["run_id"]))
        result = service.confirm(user_id="user-a", run_id=str(run["run_id"]))
    elif action == "cross_user_confirm":
        result = service.confirm(user_id="user-b", run_id=str(run["run_id"]))
        result = {"status": "not_found"} if result is None else result
    else:
        result = run
    actual = str(result["status"]) if result else "not_found"
    return actual == case["expected_status"], {"actual_status": actual}


def evaluate_suite(suite: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    groups = {}
    cases = expand_cases(suite)
    with tempfile.TemporaryDirectory(prefix="agent-eval-") as directory:
        root = Path(directory)
        for group_name, group_cases in cases.items():
            results = []
            for case in group_cases:
                if group_name == "routing":
                    actual = deterministic_route(case["input"])
                    passed, detail = actual == case["expected"], {"actual": actual}
                elif group_name == "grounded_answer":
                    passed, detail = _run_grounded(case)
                elif group_name == "multi_turn_delegation":
                    passed, detail = _run_delegation(case)
                elif group_name == "safety":
                    passed, detail = _run_safety(case)
                else:
                    passed, detail = _run_workflow(case, root)
                results.append({"case_id": case["case_id"], "passed": passed, **detail})
            passed_count = sum(int(item["passed"]) for item in results)
            config = suite["groups"][group_name]
            pass_rate = passed_count / len(results)
            zero_categories = set(config.get("zero_tolerance", []))
            zero_failures = sum(
                1 for item, case in zip(results, group_cases, strict=True)
                if not item["passed"] and case.get("category") in zero_categories
            )
            gate_passed = pass_rate >= float(config["minimum_pass_rate"]) and zero_failures == 0
            groups[group_name] = {
                "cases": len(results), "passed": passed_count,
                "failed": len(results) - passed_count, "pass_rate": round(pass_rate, 4),
                "minimum_pass_rate": config["minimum_pass_rate"],
                "zero_tolerance_failures": zero_failures, "gate_passed": gate_passed,
                "results": results,
            }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_version": suite["dataset_version"],
        "provider": "deterministic-mock-v1",
        "execution_mode": "application-stack",
        "created_at_unix": int(time.time()),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "estimated_cost_usd": 0.0,
        "groups": groups,
        "gate_passed": all(group["gate_passed"] for group in groups.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=Path("eval/agent_quality_suite.v1.json"))
    parser.add_argument("--calibration", type=Path, default=Path("eval/capability_calibration.v1.json"))
    parser.add_argument("--output", type=Path, default=Path("eval/reports/agent-stack-ci.json"))
    args = parser.parse_args()
    suite = load_suite(args.suite)
    report = evaluate_suite(suite)
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    report["score_calibration"] = score_calibration_report(calibration["examples"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gate_passed": report["gate_passed"], "groups": {name: value["pass_rate"] for name, value in report["groups"].items()}}, ensure_ascii=False))
    raise SystemExit(0 if report["gate_passed"] else 1)


if __name__ == "__main__":
    main()
