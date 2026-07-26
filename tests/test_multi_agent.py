from types import SimpleNamespace
from unittest.mock import MagicMock

from app import agent as agent_module
from app import multi_agent
from app.operations import RequestMetrics


def test_supervisor_has_all_specialist_tools(monkeypatch):
    created = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(multi_agent, "create_agent", created)
    monkeypatch.setattr(multi_agent, "_model", lambda **_: MagicMock())
    multi_agent.get_supervisor_agent.cache_clear()

    result = multi_agent.get_supervisor_agent()

    assert result is created.return_value
    kwargs = created.call_args.kwargs
    assert kwargs["name"] == "interview_supervisor"
    assert {item.name for item in kwargs["tools"]} == {
        "knowledge_agent",
        "interviewer_agent",
        "evaluator_agent",
        "planner_agent",
    }
    multi_agent.get_supervisor_agent.cache_clear()


def test_specialist_invocation_is_observable(monkeypatch):
    metrics = RequestMetrics()
    monkeypatch.setattr(multi_agent, "request_metrics", metrics)
    specialist = MagicMock()
    specialist.invoke.return_value = {
        "messages": [SimpleNamespace(content="专业 Agent 结果")]
    }

    result = multi_agent._invoke(
        specialist,
        "分析 RAG",
        "agent_knowledge",
    )

    assert result == "专业 Agent 结果"
    assert (
        'dependency_calls_total{dependency="agent_knowledge"} 1'
        in metrics.render_prometheus()
    )


def test_agent_topology_reflects_feature_flag(monkeypatch):
    monkeypatch.setattr(
        multi_agent,
        "get_settings",
        lambda: SimpleNamespace(multi_agent_enabled=True),
    )

    topology = multi_agent.agent_topology()

    assert topology["mode"] == "multi_agent"
    assert len(topology["specialists"]) == 4


def test_interview_agent_can_fall_back_to_single_agent(monkeypatch):
    legacy = MagicMock()
    monkeypatch.setattr(
        agent_module,
        "get_settings",
        lambda: SimpleNamespace(multi_agent_enabled=False),
    )
    monkeypatch.setattr(
        agent_module,
        "get_single_interview_agent",
        lambda: legacy,
    )
    agent_module.get_interview_agent.cache_clear()

    assert agent_module.get_interview_agent() is legacy
    agent_module.get_interview_agent.cache_clear()
