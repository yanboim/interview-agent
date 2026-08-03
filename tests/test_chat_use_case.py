"""聊天应用服务用例的测试。"""

import asyncio
from types import SimpleNamespace

from app.application.chat_execution import (
    ChatExecutionEvent,
    ChatExecutionRequest,
    ChatExecutionResult,
)
from app.application.chat_service import ChatTurnService
from app.application.chat_use_case import ChatCommand, ChatUseCase
from app.storage import ConversationStore


class FakeMetrics:
    def __init__(self) -> None:
        self.observations: list[tuple[str, int]] = []

    def observe_product(self, name: str, value: int = 1) -> None:
        self.observations.append((name, value))


class FakeExecutor:
    def __init__(self) -> None:
        self.invoke_count = 0
        self.stream_count = 0

    async def invoke(self, request: ChatExecutionRequest) -> ChatExecutionResult:
        self.invoke_count += 1
        return ChatExecutionResult(
            answer="使用状态机。",
            evidence=[],
            purpose="knowledge",
            model_version="model-v1",
            budget={"model_calls": 1},
        )

    async def stream(self, request: ChatExecutionRequest):
        self.stream_count += 1
        yield ChatExecutionEvent(kind="token", content="使用")
        yield ChatExecutionEvent(kind="token", content="状态机。")
        yield ChatExecutionEvent(
            kind="completed",
            purpose="knowledge",
            model_version="model-v1",
            budget={"model_calls": 1},
        )


class InlineSyncExecutor:
    async def run(self, function, /, *args, **kwargs):
        return function(*args, **kwargs)


def build_use_case(tmp_path):
    store = ConversationStore(tmp_path / "chat-use-case.db")
    executor = FakeExecutor()
    use_case = ChatUseCase(
        turn_service=ChatTurnService(store),
        agent_executor=executor,
        sync_executor=InlineSyncExecutor(),
        trace_repository=store,
        metrics=FakeMetrics(),
        settings=SimpleNamespace(
            agent_prompt_version="prompt-v1",
            zhipu_model="model-v1",
        ),
    )
    return use_case, executor, store


def command(*, key: str = "chat-use-case-1") -> ChatCommand:
    return ChatCommand(
        user_id="user-1",
        role="user",
        session_id="session-1",
        message="解释状态机",
        idempotency_key=key,
        request_id="request-1",
    )


def test_non_streaming_use_case_owns_completion_and_replay(tmp_path) -> None:
    use_case, executor, store = build_use_case(tmp_path)

    async def run_twice():
        return await use_case.execute(command()), await use_case.execute(command())

    first, replay = asyncio.run(run_twice())
    assert first.answer == replay.answer == "使用状态机。"
    assert first.replayed is False
    assert replay.replayed is True
    assert executor.invoke_count == 1
    assert [item.role for item in store.get_messages(
        user_id="user-1", session_id="session-1"
    )] == ["user", "assistant"]


def test_streaming_use_case_uses_same_terminal_metadata_and_state(tmp_path) -> None:
    use_case, executor, store = build_use_case(tmp_path)

    async def consume():
        prepared = await use_case.prepare_stream(command(key="chat-use-case-stream"))
        return [event async for event in use_case.stream(prepared)]

    events = asyncio.run(consume())
    assert [event.kind for event in events] == ["token", "token", "citations", "done"]
    assert executor.stream_count == 1
    messages = store.get_messages(user_id="user-1", session_id="session-1")
    assert [item.content for item in messages] == ["解释状态机", "使用状态机。"]
