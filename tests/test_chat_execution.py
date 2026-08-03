"""聊天用例同步执行边界（移出事件循环）的测试。"""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from langchain_core.messages import AIMessage, ToolMessage

from app.application.chat_execution import ChatExecutionRequest
from app.agent_budget import current_agent_budget
from app.chat_agent_executor import RoutedChatAgentExecutor
from app import chat_agent_executor
from app.config import Settings
from app.operations import RequestMetrics


def test_routed_executor_owns_agent_selection_timeout_and_budget() -> None:
    agent = AsyncMock()
    agent.ainvoke.return_value = {"messages": [AIMessage(content="answer")]}
    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=False,
    )
    executor = RoutedChatAgentExecutor(settings, lambda: agent)

    result = asyncio.run(executor.invoke(ChatExecutionRequest(
        message="解释状态机",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "解释状态机"}],
    )))

    assert result.answer == "answer"
    assert result.evidence == []
    assert result.purpose == "single_agent"
    assert result.model_version == "model-v1"
    assert result.budget["request_class"] == "chat"
    agent.ainvoke.assert_awaited_once()


def test_explicit_workflow_bypasses_nested_supervisor_for_multi_intent() -> None:
    evaluator = AsyncMock()
    evaluator.ainvoke.return_value = {"messages": [AIMessage(content="评分结果")]}
    interviewer = AsyncMock()
    interviewer.ainvoke.return_value = {"messages": [AIMessage(content="追问题目")]}
    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: (_ for _ in ()).throw(AssertionError("supervisor must not run")),
        specialist_factories={
            "evaluator": lambda: evaluator,
            "interviewer": lambda: interviewer,
        },
    )

    result = asyncio.run(executor.invoke(ChatExecutionRequest(
        message="请评价我的回答并继续追问",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "请评价我的回答并继续追问"}],
    )))

    assert result.purpose == "workflow_v2:evaluator+interviewer"
    assert result.answer == "## 回答评估\n\n评分结果\n\n## 模拟面试\n\n追问题目"
    evaluator.ainvoke.assert_awaited_once()
    interviewer.ainvoke.assert_awaited_once()


def test_explicit_workflow_runs_independent_routes_concurrently() -> None:
    both_started = asyncio.Event()
    started = 0

    class ConcurrentAgent:
        def __init__(self, answer: str) -> None:
            self.answer = answer

        async def ainvoke(self, *_args, **_kwargs):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)
            return {"messages": [AIMessage(content=self.answer)]}

    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={
            "evaluator": lambda: ConcurrentAgent("评分结果"),
            "interviewer": lambda: ConcurrentAgent("追问题目"),
        },
    )

    result = asyncio.run(executor.invoke(ChatExecutionRequest(
        message="请评价我的回答并继续追问",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "请评价我的回答并继续追问"}],
    )))

    assert started == 2
    assert result.answer == "## 回答评估\n\n评分结果\n\n## 模拟面试\n\n追问题目"


def test_explicit_workflow_cancels_sibling_route_after_failure() -> None:
    waiting_started = asyncio.Event()
    waiting_cancelled = asyncio.Event()

    class FailingAgent:
        async def ainvoke(self, *_args, **_kwargs):
            await waiting_started.wait()
            raise RuntimeError("specialist failed")

    class WaitingAgent:
        async def ainvoke(self, *_args, **_kwargs):
            waiting_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                waiting_cancelled.set()

    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={
            "evaluator": FailingAgent,
            "interviewer": WaitingAgent,
        },
    )

    with pytest.raises(RuntimeError, match="specialist failed"):
        asyncio.run(executor.invoke(ChatExecutionRequest(
            message="请评价我的回答并继续追问",
            user_id="user-1",
            role="user",
            messages=[{"role": "user", "content": "请评价我的回答并继续追问"}],
        )))

    assert waiting_cancelled.is_set()


def test_explicit_stream_runs_independent_routes_concurrently_in_route_order() -> None:
    both_started = asyncio.Event()
    started = 0

    class ConcurrentStructuredAgent:
        def __init__(self, answer: str) -> None:
            self.answer = answer

        async def ainvoke(self, *_args, **_kwargs):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)
            return {
                "messages": [
                    ToolMessage(content="evidence", tool_call_id=self.answer),
                    AIMessage(content=""),
                ],
                "structured_response": {"answer": self.answer},
            }

    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={
            "evaluator": lambda: ConcurrentStructuredAgent("评分结果"),
            "interviewer": lambda: ConcurrentStructuredAgent("追问题目"),
        },
    )

    async def collect() -> list[str]:
        return [
            event.content
            async for event in executor.stream(ChatExecutionRequest(
                message="请评价我的回答并继续追问",
                user_id="user-1",
                role="user",
                messages=[{"role": "user", "content": "请评价我的回答并继续追问"}],
            ))
            if event.kind == "token"
        ]

    tokens = asyncio.run(collect())

    assert started == 2
    assert "".join(tokens) == (
        "## 回答评估\n\n评分结果\n\n## 模拟面试\n\n追问题目"
    )


def test_explicit_stream_emits_single_route_structured_answer() -> None:
    agent = AsyncMock()
    agent.ainvoke.return_value = {
        "messages": [AIMessage(content="")],
        "structured_response": {"answer": "结构化知识回答"},
    }
    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={"knowledge": lambda: agent},
    )

    async def collect() -> list[str]:
        return [
            event.content
            async for event in executor.stream(ChatExecutionRequest(
                message="请解释幂等性",
                user_id="user-1",
                role="user",
                messages=[{"role": "user", "content": "请解释幂等性"}],
            ))
            if event.kind == "token"
        ]

    assert asyncio.run(collect()) == ["结构化知识回答"]
    agent.ainvoke.assert_awaited_once()


def test_explicit_stream_timeout_does_not_wait_for_uncooperative_route() -> None:
    cancellation_seen = asyncio.Event()

    class IgnoresCancellationBriefly:
        async def ainvoke(self, *_args, **_kwargs):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                # Simulate an HTTP client that needs a bounded amount of time
                # to unwind after cancellation.  The parent must not await
                # this indefinitely while holding the chat turn lock.
                await asyncio.sleep(0.1)
                raise

    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
        chat_agent_timeout_seconds=0.01,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={"knowledge": IgnoresCancellationBriefly},
    )
    request = ChatExecutionRequest(
        message="请解释幂等性",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "请解释幂等性"}],
    )

    async def collect() -> None:
        async for _ in executor.stream(request):
            pass

    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(collect())

    assert cancellation_seen.is_set()
    assert time.monotonic() - started < 0.5


def test_explicit_workflow_allocates_a_bounded_budget_per_route() -> None:
    class BudgetClaimingAgent:
        async def ainvoke(self, *_args, **_kwargs):
            budget = current_agent_budget()
            assert budget is not None
            for _ in range(5):
                budget.claim_call("specialist")
            return {"messages": [AIMessage(content="answer")]}

    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=True,
        agent_chat_max_model_calls=5,
        agent_workflow_v2_max_model_calls_per_route=5,
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={
            "evaluator": BudgetClaimingAgent,
            "interviewer": BudgetClaimingAgent,
        },
    )

    result = asyncio.run(executor.invoke(ChatExecutionRequest(
        message="请评价我的回答并继续追问",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "请评价我的回答并继续追问"}],
    )))

    assert result.budget["max_calls"] == 10
    assert result.budget["call_count"] == 10


def test_explicit_workflow_records_success_and_failure_metrics(monkeypatch) -> None:
    metrics = RequestMetrics()
    monkeypatch.setattr(chat_agent_executor, "request_metrics", metrics)
    agent = AsyncMock()
    agent.ainvoke.return_value = {"messages": [AIMessage(content="评分结果")]}
    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
    )
    executor = RoutedChatAgentExecutor(
        settings,
        lambda: AsyncMock(),
        specialist_factories={"evaluator": lambda: agent},
    )
    request = ChatExecutionRequest(
        message="请评价我的回答",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "请评价我的回答"}],
    )

    asyncio.run(executor.invoke(request))
    agent.ainvoke.side_effect = RuntimeError("provider failed")
    with pytest.raises(RuntimeError, match="provider failed"):
        asyncio.run(executor.invoke(request))

    rendered = metrics.render_prometheus()
    assert (
        'workflow_runs_total{workflow="chat-workflow-v2",outcome="completed"} 1'
        in rendered
    )
    assert (
        'workflow_runs_total{workflow="chat-workflow-v2",outcome="failed"} 1'
        in rendered
    )
    assert 'model_runs_total{request_class="chat",price_version="zhipu-2026-07"} 2' in rendered


def test_single_agent_mode_never_emits_retired_supervisor_metric(monkeypatch) -> None:
    metrics = RequestMetrics()
    monkeypatch.setattr(chat_agent_executor, "request_metrics", metrics)
    single_agent = AsyncMock()
    single_agent.ainvoke.return_value = {"messages": [AIMessage(content="回答")]}
    settings = Settings(
        zhipu_api_key="test-key",
        zhipu_model="model-v1",
        multi_agent_enabled=False,
    )
    executor = RoutedChatAgentExecutor(settings, lambda: single_agent)

    result = asyncio.run(executor.invoke(ChatExecutionRequest(
        message="请评价我的回答并继续追问",
        user_id="user-1",
        role="user",
        messages=[{"role": "user", "content": "请评价我的回答并继续追问"}],
    )))

    assert result.purpose == "single_agent"
    assert "chat-supervisor-v1" not in metrics.render_prometheus()
