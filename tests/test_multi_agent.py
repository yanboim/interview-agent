from types import SimpleNamespace
from unittest.mock import MagicMock

from app import agent as agent_module
from app import multi_agent
from app.operations import RequestMetrics
from app.agent_contracts import SpecialistResultV1


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


def test_interviewer_and_evaluator_have_read_only_retrieval(monkeypatch):
    created = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(multi_agent, "create_agent", created)
    monkeypatch.setattr(multi_agent, "_model", lambda **_: MagicMock())
    for factory in (
        multi_agent.get_interviewer_agent,
        multi_agent.get_evaluator_agent,
    ):
        factory.cache_clear()
        factory()
        kwargs = created.call_args.kwargs
        assert [item.name for item in kwargs["tools"]] == [
            "search_interview_knowledge"
        ]
        assert kwargs["response_format"] is SpecialistResultV1
        factory.cache_clear()

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


def test_high_confidence_direct_route_skips_supervisor_but_ambiguous_uses_it(
    monkeypatch,
):
    direct = MagicMock()
    supervisor = MagicMock()
    monkeypatch.setattr(multi_agent, "get_evaluator_agent", lambda: direct)
    settings = SimpleNamespace(
        multi_agent_enabled=True,
        agent_direct_route_enabled=True,
        agent_routing_rollout_stage="production",
        agent_routing_canary_percent=0,
        agent_direct_route_min_confidence=0.9,
    )

    selected = agent_module.select_interview_agent(
        message="请评价回答并指出错误",
        user_id="user-a",
        role="user",
        default_agent=supervisor,
        settings=settings,
    )
    ambiguous = agent_module.select_interview_agent(
        message="先解释 RAG 原理，再出题考我",
        user_id="user-a",
        role="user",
        default_agent=supervisor,
        settings=settings,
    )

    assert selected is direct
    assert ambiguous is supervisor
