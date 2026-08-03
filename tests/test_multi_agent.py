"""多 Agent 组装与拓扑的测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app import multi_agent
from app.agent_contracts import SpecialistResultV1


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

    assert topology["mode"] == "workflow_v2"
    assert topology["workflow"] == {
        "version": "chat-workflow-v2",
        "planner": "deterministic",
        "max_specialists": 4,
    }
    assert "supervisor" not in topology
    assert len(topology["specialists"]) == 4
