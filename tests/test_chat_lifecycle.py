import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from sqlalchemy import func, select

import app.main as main_module
from app.application.chat_service import ChatTurnConflict, ChatTurnService
from app.chat_context import estimate_message_tokens
from app.database import chat_turns, conversations
from app.storage import ConversationStore
from app.model_routing import ModelUnavailable


def begin(
    service: ChatTurnService,
    *,
    key: str = "chat-command-1",
    content: str = "如何设计可靠聊天？",
) -> dict[str, object]:
    return service.begin(
        user_id="user-1",
        session_id="session-1",
        content=content,
        idempotency_key=key,
    )


def test_completed_turn_materializes_history_atomically_and_replays(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "chat.db")
    service = ChatTurnService(store)
    claim = begin(service)

    assert store.get_messages(
        user_id="user-1",
        session_id="session-1",
    ) == []

    service.complete(
        claim,
        user_id="user-1",
        session_id="session-1",
        answer="使用持久化状态机。",
        metadata={"knowledge_used": False, "sources": []},
    )
    replay = begin(service)
    messages = store.get_messages(
        user_id="user-1",
        session_id="session-1",
    )

    assert replay["outcome"] == "completed"
    assert replay["turn_id"] == claim["turn_id"]
    assert replay["answer"] == "使用持久化状态机。"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == [
        "如何设计可靠聊天？",
        "使用持久化状态机。",
    ]


def test_session_allows_only_one_generating_turn_across_stores(
    tmp_path,
) -> None:
    database = tmp_path / "concurrent-chat.db"
    first_service = ChatTurnService(ConversationStore(database))
    second_service = ChatTurnService(ConversationStore(database))
    first = begin(first_service)

    with pytest.raises(ChatTurnConflict, match="已有正在生成"):
        begin(second_service, key="chat-command-2", content="并发请求")

    first_service.complete(
        first,
        user_id="user-1",
        session_id="session-1",
        answer="第一答",
        metadata={},
    )
    second = begin(
        second_service,
        key="chat-command-2",
        content="第二问",
    )
    assert second["turn_index"] == 2


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled"])
def test_terminal_turn_releases_session_and_same_key_reclaims(
    tmp_path,
    terminal_status,
) -> None:
    store = ConversationStore(tmp_path / f"{terminal_status}.db")
    service = ChatTurnService(store)
    first = begin(service)
    terminate = service.fail if terminal_status == "failed" else service.cancel
    assert terminate(
        first,
        partial_answer="部分回答",
        error="connection ended",
    )

    turn = store.get_chat_turn(
        user_id="user-1",
        session_id="session-1",
        turn_id=str(first["turn_id"]),
    )
    retried = begin(service)

    assert turn["status"] == terminal_status
    assert turn["assistant_content"] == "部分回答"
    assert retried["outcome"] == "claimed"
    assert retried["turn_id"] == first["turn_id"]
    assert retried["turn_index"] == first["turn_index"]
    assert store.get_messages(
        user_id="user-1",
        session_id="session-1",
    ) == []


def test_same_key_with_different_content_is_rejected(tmp_path) -> None:
    service = ChatTurnService(ConversationStore(tmp_path / "key-reuse.db"))
    begin(service)

    with pytest.raises(ChatTurnConflict, match="不能用于不同"):
        begin(service, content="更换后的内容")


def test_context_summary_is_durable_and_retry_does_not_duplicate_it(
    tmp_path,
) -> None:
    database = tmp_path / "context-summary.db"
    store = ConversationStore(database)
    for index in range(4):
        store.append_message(
            user_id="user-1",
            session_id="session-1",
            role="user" if index % 2 == 0 else "assistant",
            content=chr(ord("a") + index) * 30,
        )
    service = ChatTurnService(
        store,
        context_token_budget=170,
        summary_token_budget=60,
    )

    claim = begin(service, content="next")
    with store.engine.connect() as connection:
        conversation = dict(
            connection.execute(select(conversations)).mappings().one()
        )
    assert conversation["chat_summary"]
    assert conversation["chat_summary_through_message_id"] == 2
    assert claim["messages"][0]["role"] == "system"
    assert sum(
        estimate_message_tokens(item["role"], item["content"])
        for item in claim["messages"]
    ) <= 170

    assert service.fail(claim, partial_answer="", error="retry")
    recreated = ChatTurnService(
        ConversationStore(database),
        context_token_budget=170,
        summary_token_budget=60,
    )
    retried = begin(recreated, content="next")
    with recreated.repository.engine.connect() as connection:
        after_retry = dict(
            connection.execute(select(conversations)).mappings().one()
        )

    assert retried["turn_id"] == claim["turn_id"]
    assert after_retry["chat_summary"] == conversation["chat_summary"]
    assert after_retry["chat_summary_through_message_id"] == 2


def test_oversized_current_message_does_not_claim_or_create_session(
    tmp_path,
) -> None:
    store = ConversationStore(tmp_path / "oversized-context.db")
    service = ChatTurnService(
        store,
        context_token_budget=50,
        summary_token_budget=20,
    )

    with pytest.raises(ValueError, match="超过聊天上下文预算"):
        begin(service, content="x" * 100)

    store.initialize()
    with store.engine.connect() as connection:
        assert connection.execute(
            select(func.count()).select_from(conversations)
        ).scalar_one() == 0
        assert connection.execute(
            select(func.count()).select_from(chat_turns)
        ).scalar_one() == 0


def test_chat_route_maps_context_budget_failure_to_413(
    tmp_path,
    monkeypatch,
) -> None:
    service = ChatTurnService(
        ConversationStore(tmp_path / "route-context-budget.db"),
        context_token_budget=50,
        summary_token_budget=20,
    )

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module, "chat_turn_service", service)
    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    request = SimpleNamespace(state=SimpleNamespace())
    payload = main_module.ChatRequest(
        user_id="user-1",
        session_id="session-1",
        message="x" * 100,
    )

    with pytest.raises(main_module.HTTPException) as error:
        asyncio.run(
            main_module.chat(
                payload,
                request,
                idempotency_key="chat-command-1",
            )
        )

    assert error.value.status_code == 413


def test_normal_chat_replay_does_not_invoke_agent_twice(
    tmp_path,
    monkeypatch,
) -> None:
    store = ConversationStore(tmp_path / "route-chat.db")
    service = ChatTurnService(store)
    agent = SimpleNamespace()
    agent.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content="持久化回答")]}
    )

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module, "chat_turn_service", service)
    monkeypatch.setattr(main_module, "get_interview_agent", lambda: agent)
    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    request = SimpleNamespace(state=SimpleNamespace())
    payload = main_module.ChatRequest(
        user_id="user-1",
        session_id="session-1",
        message="解释状态机",
    )

    async def submit_twice():
        first_result = await main_module.chat(
            payload,
            request,
            idempotency_key="chat-command-1",
        )
        replay_result = await main_module.chat(
            payload,
            request,
            idempotency_key="chat-command-1",
        )
        return first_result, replay_result

    first, replay = asyncio.run(submit_twice())

    assert first == replay
    assert agent.ainvoke.call_count == 1


def test_normal_chat_failure_is_durable_and_retryable(
    tmp_path,
    monkeypatch,
) -> None:
    store = ConversationStore(tmp_path / "failed-route-chat.db")
    service = ChatTurnService(store)
    agent = SimpleNamespace(
        ainvoke=AsyncMock(side_effect=RuntimeError("provider unavailable"))
    )

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module, "chat_turn_service", service)
    monkeypatch.setattr(main_module, "get_interview_agent", lambda: agent)
    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    request = SimpleNamespace(state=SimpleNamespace())
    payload = main_module.ChatRequest(
        user_id="user-1",
        session_id="session-1",
        message="触发失败",
    )

    with pytest.raises(main_module.HTTPException, match="Agent 执行失败"):
        asyncio.run(
            main_module.chat(
                payload,
                request,
                idempotency_key="chat-command-1",
            )
        )
    with store.engine.connect() as connection:
        failed = dict(
            connection.execute(select(chat_turns)).mappings().one()
        )
    retried = begin(service, content="触发失败")

    assert failed["status"] == "failed"
    assert "provider unavailable" in failed["error"]
    assert retried["turn_id"] == failed["turn_id"]
    assert store.get_messages(
        user_id="user-1",
        session_id="session-1",
    ) == []


def test_recoverable_model_unavailable_returns_503_and_safe_retry_state(
    tmp_path, monkeypatch,
) -> None:
    store = ConversationStore(tmp_path / "unavailable-route-chat.db")
    service = ChatTurnService(store)
    agent = SimpleNamespace(
        ainvoke=AsyncMock(side_effect=ModelUnavailable("internal provider detail"))
    )

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module, "chat_turn_service", service)
    monkeypatch.setattr(main_module, "get_interview_agent", lambda: agent)
    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    request = SimpleNamespace(state=SimpleNamespace())
    payload = main_module.ChatRequest(
        user_id="user-1", session_id="session-1", message="模型暂不可用"
    )

    with pytest.raises(main_module.HTTPException) as captured:
        asyncio.run(main_module.chat(
            payload, request, idempotency_key="chat-unavailable-1"
        ))

    assert captured.value.status_code == 503
    assert "internal provider detail" not in captured.value.detail
    with store.engine.connect() as connection:
        failed = dict(connection.execute(select(chat_turns)).mappings().one())
    assert failed["status"] == "failed"
    assert "internal provider detail" not in failed["error"]
    assert begin(service, key="chat-unavailable-1", content="模型暂不可用")["outcome"] == "claimed"


def test_closing_stream_marks_turn_cancelled(
    tmp_path,
    monkeypatch,
) -> None:
    store = ConversationStore(tmp_path / "cancel-stream.db")
    service = ChatTurnService(store)

    class StreamingAgent:
        async def astream(self, *_args, **_kwargs):
            yield AIMessageChunk(content="部分"), {}
            await asyncio.Event().wait()

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(main_module, "chat_turn_service", service)
    monkeypatch.setattr(main_module.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        main_module,
        "get_interview_agent",
        lambda: StreamingAgent(),
    )
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    request = SimpleNamespace(state=SimpleNamespace())
    payload = main_module.ChatRequest(
        user_id="user-1",
        session_id="session-1",
        message="开始流式生成",
    )

    async def consume_and_close():
        response = await main_module.chat_stream(
            payload,
            request,
            idempotency_key="chat-command-1",
        )
        iterator = response.body_iterator
        first_chunk = await iterator.__anext__()
        await iterator.aclose()
        return first_chunk

    chunk = asyncio.run(consume_and_close())
    with store.engine.connect() as connection:
        cancelled = dict(
            connection.execute(select(chat_turns)).mappings().one()
        )
    retried = begin(service, content="开始流式生成")

    assert '"type": "token"' in chunk
    assert cancelled["status"] == "cancelled"
    assert cancelled["assistant_content"] == "部分"
    assert retried["outcome"] == "claimed"
    assert retried["turn_id"] == cancelled["turn_id"]
