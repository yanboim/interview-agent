import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

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
