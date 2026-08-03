"""仓库结构基线（目录/文件存在性）的测试。"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = (
    ROOT / "eval" / "reports" / "repository-structure-baseline-2026-08-01.json"
)


def _load(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_repository_structure_baseline_is_derived_from_retained_reports() -> None:
    baseline = _load(BASELINE.relative_to(ROOT).as_posix())
    retained_quality = baseline["agent_quality"]
    retained_routing = baseline["model_routing_canary"]
    assert isinstance(retained_quality, dict)
    assert isinstance(retained_routing, dict)

    quality = _load(str(retained_quality["source_report"]))
    routing = _load(str(retained_routing["source_report"]))
    groups = quality["groups"]
    assert isinstance(groups, dict)
    actual_rates = {
        name: group["pass_rate"]
        for name, group in groups.items()
        if isinstance(group, dict)
    }
    retained_rates = {
        name: group["pass_rate"]
        for name, group in retained_quality["groups"].items()
    }
    assert retained_rates == actual_rates
    assert retained_quality["confirmation_workflow_completion_rate"] == actual_rates[
        "confirmation_workflow"
    ]
    assert retained_quality["citation_coverage"] == actual_rates["grounded_answer"]
    assert retained_quality["estimated_cost_usd"] == quality["estimated_cost_usd"]

    provider_calls = sum(
        int(item.get("provider_calls", 0))
        for group in groups.values()
        if isinstance(group, dict)
        for item in group.get("results", [])
        if isinstance(item, dict)
    )
    assert retained_quality["deterministic_provider_call_count"] == provider_calls
    assert retained_routing["baseline"] == routing["baseline"]
    assert retained_routing["routed"] == routing["routed"]


def test_repository_structure_baseline_evidence_exists() -> None:
    baseline = _load(BASELINE.relative_to(ROOT).as_posix())
    quality = baseline["agent_quality"]
    routing = baseline["model_routing_canary"]
    assert isinstance(quality, dict)
    assert isinstance(routing, dict)
    assert (ROOT / str(quality["source_report"])).is_file()
    assert (ROOT / str(routing["source_report"])).is_file()
