"""Workflow V2 路由评测脚本的测试。"""

from scripts.evaluate_multi_agent import selected_routes, summarize


def test_selected_routes_use_explicit_bounded_workflow():
    assert selected_routes("请评价我的回答并继续追问") == [
        "evaluator_agent",
        "interviewer_agent",
    ]


def test_routing_summary_reports_accuracy_by_agent():
    summary = summarize(
        [
            {
                "expected": "knowledge_agent",
                "actual": "knowledge_agent",
                "correct": True,
            },
            {
                "expected": "planner_agent",
                "actual": "knowledge_agent",
                "correct": False,
            },
        ]
    )

    assert summary["routing_accuracy"] == 0.5
    assert summary["per_agent"]["knowledge_agent"]["accuracy"] == 1.0
    assert summary["per_agent"]["planner_agent"]["accuracy"] == 0.0
