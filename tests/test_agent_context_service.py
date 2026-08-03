"""Agent 上下文快照服务的构建与不可信记忆过滤测试。"""

import json

import pytest

from app.agent_context import reset_conversation_context, set_conversation_context
from app.agent_context_service import AgentContextService
from app.multi_agent import build_specialist_messages
from app.storage import ConversationStore
from app.tool_context import reset_tool_identity, set_tool_identity


class ContextRepository:
    def get_user_profile(self, *, user_id):
        return {
            "target_role": "Staff Backend Engineer",
            "experience_level": "高级",
            "focus_areas": "分布式系统",
            "interview_date": "2026-09-01",
            "job_description": "需要系统设计与故障处理经验。" * 100,
        }

    def list_coaching_memories(self, **_kwargs):
        return [
            {
                "memory_id": "memory-1",
                "kind": "preference",
                "content": "先给结论，再讲原理。",
                "source_type": "user",
                "source_id": None,
            }
        ]

    def get_capability_rows(self, *, user_id):
        return []

    def list_learning_tasks(self, *, user_id):
        return []


def test_context_snapshot_is_immutable_budgeted_and_delegated_once():
    service = AgentContextService(ContextRepository(), token_budget=1600)
    snapshot = service.build(
        user_id="user-a",
        role="user",
        conversation_messages=[
            {"role": "assistant", "content": "用户一定喜欢极简回答。"},
            {"role": "user", "content": "继续分析上一题"},
        ],
    )

    assert snapshot.estimated_tokens <= 1600
    assert [memory.content for memory in snapshot.memories] == [
        "先给结论，再讲原理。"
    ]
    assert "用户一定喜欢极简回答" not in snapshot.render_system_context()
    with pytest.raises(Exception):
        snapshot.user_id = "other"  # type: ignore[misc]

    context_token = set_conversation_context(
        [
            {"role": "user", "content": "前一个问题"},
            {"role": "assistant", "content": "前一个回答"},
            {"role": "user", "content": "继续分析上一题"},
        ],
        snapshot,
    )
    identity_token = set_tool_identity(
        "user-a",
        "user",
        request_id="request-1",
        interaction_type="chat",
        interaction_id="turn-1",
    )
    try:
        messages = build_specialist_messages("评价这个回答")
    finally:
        reset_tool_identity(identity_token)
        reset_conversation_context(context_token)

    assert len(messages) == 1
    envelope = json.loads(messages[0].content)
    assert envelope["schema_version"] == "delegation-envelope-v1"
    assert envelope["original_request"] == "继续分析上一题"
    assert envelope["request_id"] == "request-1"
    assert envelope["context"]["memories"][0]["content"] == "先给结论，再讲原理。"


def test_memory_requires_confirmation_and_is_owner_scoped(tmp_path):
    store = ConversationStore(tmp_path / "memories.db")
    memory = store.create_coaching_memory(
        user_id="user-a",
        kind="goal",
        content="准备 Staff 级系统设计面试",
    )

    assert store.list_coaching_memories(
        user_id="user-a", status="confirmed", context_ready_only=True
    ) == []
    assert store.update_coaching_memory(
        user_id="user-b",
        memory_id=str(memory["memory_id"]),
        action="confirm",
    ) is None
    confirmed = store.update_coaching_memory(
        user_id="user-a",
        memory_id=str(memory["memory_id"]),
        action="confirm",
    )
    assert confirmed and confirmed["status"] == "confirmed"

    corrected = store.update_coaching_memory(
        user_id="user-a",
        memory_id=str(memory["memory_id"]),
        action="correct",
        content="准备 Principal 级系统设计面试",
    )
    assert corrected and corrected["status"] == "proposed"
    assert store.list_coaching_memories(
        user_id="user-a", status="confirmed", context_ready_only=True
    ) == []

    reconfirmed = store.update_coaching_memory(
        user_id="user-a",
        memory_id=str(memory["memory_id"]),
        action="confirm",
    )
    assert reconfirmed and reconfirmed["status"] == "confirmed"
    service = AgentContextService(store, token_budget=1600)
    first_session = service.build(
        user_id="user-a",
        role="user",
        conversation_messages=[{"role": "user", "content": "制定训练计划"}],
    )
    later_session = service.build(
        user_id="user-a",
        role="user",
        conversation_messages=[{"role": "user", "content": "继续昨天的训练"}],
    )
    for snapshot in (first_session, later_session):
        rendered = snapshot.render_system_context()
        assert "准备 Principal 级系统设计面试" in rendered
        assert "准备 Staff 级系统设计面试" not in rendered

    context_token = set_conversation_context(
        [{"role": "user", "content": "继续昨天的训练"}], later_session
    )
    identity_token = set_tool_identity(
        "user-a",
        "user",
        request_id="request-after-correction",
        interaction_type="chat",
        interaction_id="turn-after-correction",
    )
    try:
        delegated = json.loads(build_specialist_messages("制定训练计划")[0].content)
    finally:
        reset_tool_identity(identity_token)
        reset_conversation_context(context_token)
    delegated_context = json.dumps(delegated["context"], ensure_ascii=False)
    assert "准备 Principal 级系统设计面试" in delegated_context
    assert "准备 Staff 级系统设计面试" not in delegated_context

    assert not store.delete_coaching_memory(
        user_id="user-b", memory_id=str(memory["memory_id"])
    )
    assert store.delete_coaching_memory(
        user_id="user-a", memory_id=str(memory["memory_id"])
    )


def test_derived_memory_with_missing_source_never_enters_context(tmp_path):
    store = ConversationStore(tmp_path / "stale-memory.db")
    memory = store.create_coaching_memory(
        user_id="user-a",
        kind="observation",
        content="工程实践需要加强",
        source_type="interview_review",
        source_id="missing-review",
        source_revision=1,
    )
    store.update_coaching_memory(
        user_id="user-a",
        memory_id=str(memory["memory_id"]),
        action="confirm",
    )

    assert store.list_coaching_memories(
        user_id="user-a", status="confirmed", context_ready_only=True
    ) == []
