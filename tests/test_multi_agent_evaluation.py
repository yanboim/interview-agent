from app.multi_agent import evaluator_agent
from scripts.evaluate_multi_agent import selected_tool, summarize


def test_selected_tool_reads_first_supervisor_delegation():
    class Response:
        tool_calls = [{"name": evaluator_agent.name, "args": {}}]

    assert selected_tool(Response()) == "evaluator_agent"


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
