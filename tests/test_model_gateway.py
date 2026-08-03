"""模型网关策略（预算/并发/回退/指标）的测试。"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

import app.model_gateway as gateway_module
from app.agent_budget import agent_execution_budget
from app.config import Settings
from app.model_gateway import (
    ModelBudgetExceeded,
    ModelGatewayError,
    create_chat_model,
    create_embeddings,
)


def settings(**overrides) -> Settings:
    return Settings(
        zhipu_api_key="test-key",
        llm_timeout_seconds=3,
        llm_max_retries=1,
        llm_max_concurrency=1,
        llm_input_char_budget=20,
        llm_max_output_tokens=100,
        **overrides,
    )


def result(content: str = "ok") -> ChatResult:
    return ChatResult(
        generations=[
            ChatGeneration(
                message=AIMessage(
                    content=content,
                    usage_metadata={
                        "input_tokens": 2,
                        "output_tokens": 1,
                        "total_tokens": 3,
                    },
                )
            )
        ]
    )


def stream_chunk(content: str) -> ChatGenerationChunk:
    return ChatGenerationChunk(message=AIMessageChunk(content=content))


def test_gateway_applies_timeout_retry_and_output_budget() -> None:
    model = create_chat_model(
        "test",
        temperature=0,
        max_tokens=500,
        settings=settings(),
    )

    assert model.max_retries == 1
    assert model.max_tokens == 100
    assert model.request_timeout == 3


def test_gateway_allows_purpose_specific_timeout_and_retry_policy() -> None:
    model = create_chat_model(
        "resume_analysis",
        temperature=0,
        timeout_seconds=180,
        max_retries=0,
        settings=settings(),
    )

    assert model.request_timeout == 180
    assert model.max_retries == 0


def test_gateway_rejects_oversized_input_before_provider_call(
    monkeypatch,
) -> None:
    provider = pytest.fail
    monkeypatch.setattr(ChatOpenAI, "_generate", provider)
    model = create_chat_model("test", temperature=0, settings=settings())

    with pytest.raises(ModelBudgetExceeded, match="input budget exceeded"):
        model.invoke([HumanMessage(content="x" * 21)])


def test_gateway_maps_provider_errors_without_leaking_message(
    monkeypatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("secret provider payload")

    monkeypatch.setattr(ChatOpenAI, "_generate", fail)
    model = create_chat_model("test", temperature=0, settings=settings())

    with pytest.raises(ModelGatewayError) as captured:
        model.invoke([HumanMessage(content="short")])

    assert "RuntimeError" in str(captured.value)
    assert "secret provider payload" not in str(captured.value)


def test_gateway_uses_only_evaluation_approved_same_provider_fallback(
    monkeypatch,
) -> None:
    calls = []

    def generate(model, *_args, **_kwargs):
        calls.append(model.model_name)
        if model.model_name == "primary-v1":
            raise RuntimeError("primary unavailable")
        return result("fallback")

    monkeypatch.setattr(ChatOpenAI, "_generate", generate)
    model = create_chat_model(
        "knowledge",
        temperature=0,
        settings=settings(
            zhipu_model="primary-v1",
            llm_fallback_enabled=True,
            llm_fallback_evaluation_approved=True,
            llm_fallback_model="fallback-v1",
            llm_fallback_approved_purposes="knowledge",
        ),
    )

    assert model.invoke([HumanMessage(content="short")]).content == "fallback"
    assert calls == ["primary-v1", "fallback-v1"]


def test_sync_stream_restarts_once_before_any_chunk_and_records_recovery(
    monkeypatch,
) -> None:
    calls = 0
    events: list[str] = []

    def stream(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("provider SSE stalled after response headers")
        yield stream_chunk("recovered")

    monkeypatch.setattr(ChatOpenAI, "_stream", stream)
    monkeypatch.setattr(
        gateway_module.request_metrics,
        "observe_product",
        lambda name, value=1.0: events.append(name),
    )
    model_settings = settings(llm_zero_chunk_stream_restarts=1)
    model = create_chat_model("knowledge", temperature=0, settings=model_settings)
    with agent_execution_budget(model_settings, "chat") as budget:
        chunks = list(model._stream([HumanMessage(content="short")]))

    assert [chunk.message.content for chunk in chunks] == ["recovered"]
    assert calls == 2
    assert budget.snapshot()["call_count"] == 2
    assert events == [
        "model_zero_chunk_stream_restart_attempted",
        "model_zero_chunk_stream_restart_recovered",
    ]


def test_async_stream_restarts_once_before_any_chunk(monkeypatch) -> None:
    calls = 0

    async def stream(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("provider SSE stalled after response headers")
        yield stream_chunk("recovered")

    async def consume(model):
        return [
            chunk
            async for chunk in model._astream([HumanMessage(content="short")])
        ]

    monkeypatch.setattr(ChatOpenAI, "_astream", stream)
    model = create_chat_model(
        "knowledge",
        temperature=0,
        settings=settings(llm_zero_chunk_stream_restarts=1),
    )

    chunks = asyncio.run(consume(model))

    assert [chunk.message.content for chunk in chunks] == ["recovered"]
    assert calls == 2


def test_async_stream_never_restarts_or_falls_back_after_a_chunk(
    monkeypatch,
) -> None:
    calls: list[str] = []
    received: list[str] = []

    async def stream(model, *_args, **_kwargs):
        calls.append(str(model.model_name))
        yield stream_chunk("partial")
        raise TimeoutError("provider SSE stalled after a partial response")

    async def consume(model) -> None:
        async for chunk in model._astream([HumanMessage(content="short")]):
            received.append(str(chunk.message.content))

    monkeypatch.setattr(ChatOpenAI, "_astream", stream)
    model = create_chat_model(
        "knowledge",
        temperature=0,
        settings=settings(
            zhipu_model="primary-v1",
            llm_zero_chunk_stream_restarts=2,
            llm_fallback_enabled=True,
            llm_fallback_evaluation_approved=True,
            llm_fallback_model="fallback-v1",
            llm_fallback_approved_purposes="knowledge",
        ),
    )

    with pytest.raises(ModelGatewayError):
        asyncio.run(consume(model))

    assert received == ["partial"]
    assert calls == ["primary-v1"]


def test_zero_chunk_restart_cannot_exceed_request_call_budget(monkeypatch) -> None:
    calls = 0

    async def stream(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("provider SSE stalled after response headers")
        yield  # pragma: no cover - keeps this an async generator

    async def consume(model) -> None:
        async for _ in model._astream([HumanMessage(content="short")]):
            pass

    monkeypatch.setattr(ChatOpenAI, "_astream", stream)
    model_settings = settings(
        llm_zero_chunk_stream_restarts=1,
        agent_chat_max_model_calls=1,
    )
    model = create_chat_model("knowledge", temperature=0, settings=model_settings)

    with agent_execution_budget(model_settings, "chat"):
        with pytest.raises(ModelBudgetExceeded, match="budget exhausted"):
            asyncio.run(consume(model))

    assert calls == 1


def test_zero_chunk_stream_restart_records_exhaustion(monkeypatch) -> None:
    calls = 0
    events: list[str] = []

    def stream(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("provider SSE remained stalled")
        yield  # pragma: no cover - keeps this a generator

    monkeypatch.setattr(ChatOpenAI, "_stream", stream)
    monkeypatch.setattr(
        gateway_module.request_metrics,
        "observe_product",
        lambda name, value=1.0: events.append(name),
    )
    model = create_chat_model(
        "knowledge",
        temperature=0,
        settings=settings(llm_zero_chunk_stream_restarts=1),
    )

    with pytest.raises(ModelGatewayError):
        list(model._stream([HumanMessage(content="short")]))

    assert calls == 2
    assert events == [
        "model_zero_chunk_stream_restart_attempted",
        "model_zero_chunk_stream_restart_exhausted",
    ]


def test_zero_chunk_stream_restart_setting_is_bounded() -> None:
    with pytest.raises(ValueError, match="between 0 and 2"):
        settings(llm_zero_chunk_stream_restarts=3)


def test_gateway_limits_concurrent_sync_calls(monkeypatch) -> None:
    entered = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()
    first_entered = threading.Event()

    def blocking(*_args, **_kwargs):
        nonlocal entered, peak
        with lock:
            entered += 1
            peak = max(peak, entered)
            first_entered.set()
        assert release.wait(timeout=5)
        with lock:
            entered -= 1
        return result()

    monkeypatch.setattr(ChatOpenAI, "_generate", blocking)
    model = create_chat_model("bounded", temperature=0, settings=settings())
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(model.invoke, [HumanMessage(content="one")])
        assert first_entered.wait(timeout=5)
        second = executor.submit(model.invoke, [HumanMessage(content="two")])
        assert not second.done()
        release.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert peak == 1


def test_embedding_gateway_enforces_same_input_budget() -> None:
    model = create_embeddings(
        settings=settings(zhipu_embedding_api_key="embedding-key")
    )

    with pytest.raises(ModelBudgetExceeded, match="embeddings input budget"):
        model.embed_documents(["x" * 21])
