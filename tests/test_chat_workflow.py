"""聊天工作流端到端行为的测试。"""

from types import SimpleNamespace

from app.application.chat_workflow import (
    WORKFLOW_STAGES,
    ChatWorkflowPlanner,
    ChatWorkflowRouteRequest,
)


def settings(**overrides):
    values = {
        "multi_agent_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_explicit_workflow_plan_is_code_defined_and_model_free():
    plan = ChatWorkflowPlanner(settings()).plan(
        ChatWorkflowRouteRequest(
            message="请评价回答并指出错误", user_id="user-a", role="user"
        )
    )

    assert plan.version == "chat-workflow-v2"
    assert plan.purpose == "evaluator"
    assert plan.routes == ("evaluator",)
    assert plan.explicit_path is True
    assert plan.stages == WORKFLOW_STAGES


def test_multi_intent_uses_bounded_explicit_routes_when_rollout_admits():
    plan = ChatWorkflowPlanner(settings()).plan(
        ChatWorkflowRouteRequest(
            message="先解释 RAG 原理，再出题考我", user_id="user-a", role="user"
        )
    )

    assert plan.purpose == "workflow_v2"
    assert plan.routes == ("knowledge", "interviewer")
    assert plan.explicit_path is True
    assert plan.fallback_reason == ""


def test_retired_rollout_flags_cannot_restore_supervisor():
    plan = ChatWorkflowPlanner(
        settings(agent_routing_rollout_stage="off")
    ).plan(
        ChatWorkflowRouteRequest(
            message="请评价回答并指出错误", user_id="user-a", role="user"
        )
    )

    assert plan.purpose == "evaluator"
    assert plan.routes == ("evaluator",)
    assert plan.explicit_path is True


def test_multi_agent_disabled_uses_single_agent_without_supervisor():
    plan = ChatWorkflowPlanner(settings(multi_agent_enabled=False)).plan(
        ChatWorkflowRouteRequest(
            message="请评价回答并指出错误", user_id="user-a", role="user"
        )
    )

    assert plan.purpose == "single_agent"
    assert plan.routes == ()
    assert plan.explicit_path is False
    assert plan.fallback_reason == "multi_agent_off"
