"""外部模型统一策略网关：集中执行预算、并发、超时、重试、指标和安全错误映射。"""

import asyncio
import threading
import weakref
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any, ClassVar

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import Settings, get_settings
from app.operations import request_metrics
from app.model_routing import ModelUnavailable, fallback_policy, model_for_purpose


class ModelGatewayError(RuntimeError):
    """对外暴露给应用服务的、不泄漏供应商细节的安全错误。"""


class ModelBudgetExceeded(ModelGatewayError):
    """请求在发起供应商 I/O 之前就超出输入预算。"""


def _content_size(messages: list[BaseMessage]) -> int:
    """估算消息列表总字符数，作为输入预算的保守度量。"""
    return sum(len(str(message.content)) for message in messages)


def _raise_gateway_error(name: str, exc: Exception) -> None:
    """把任意供应商异常映射为统一的 ``ModelGatewayError``（已是网关错误则原样上抛）。"""
    if isinstance(exc, ModelGatewayError):
        raise exc
    raise ModelGatewayError(
        f"{name} model call failed ({type(exc).__name__})"
    ) from exc


def _claim_budget_call(purpose: str) -> None:
    """若当前处于 Agent 执行预算上下文，则登记一次该用途的模型调用。"""
    from app.agent_budget import current_agent_budget

    budget = current_agent_budget()
    if budget:
        budget.claim_call(purpose)


def _record_budget_usage(input_tokens: int, output_tokens: int) -> None:
    """把本次调用的 token 用量回写到 Agent 执行预算（若存在）。"""
    from app.agent_budget import current_agent_budget

    budget = current_agent_budget()
    if budget:
        budget.record_usage(input_tokens, output_tokens)


def _record_first_token() -> None:
    """记录「首个 token 已产出」，用于 Agent 预算的首 token 时延统计。"""
    from app.agent_budget import current_agent_budget

    budget = current_agent_budget()
    if budget:
        budget.record_first_token()


def _record_stream_chunk(gateway_name: str, chunk: Any) -> None:
    """Account for one provider chunk without inspecting or logging its content."""
    _record_first_token()
    usage = getattr(chunk.message, "usage_metadata", None) or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    request_metrics.observe_tokens(gateway_name, input_tokens, output_tokens)
    _record_budget_usage(input_tokens, output_tokens)


class PolicyChatOpenAI(ChatOpenAI):
    """在 LangChain 模型实现外包一层同步/异步一致的运行策略。"""

    gateway_name: str
    input_char_budget: int
    max_concurrency: int
    schema_repair_model_name: str
    fallback_model_name: str = ""
    zero_chunk_stream_restarts: int = 0

    def for_schema_repair(self) -> "PolicyChatOpenAI":
        """返回切换到结构化输出修复模型的副本（避免原实例被污染）。"""
        if self.model_name == self.schema_repair_model_name:
            return self
        return self.model_copy(update={
            "model_name": self.schema_repair_model_name,
            "gateway_name": "schema_repair",
        })

    def _fallback_copy(self) -> "PolicyChatOpenAI":
        """返回切换到回退模型的副本，并清除其回退链（防止无限回退）。"""
        return self.model_copy(update={
            "model_name": self.fallback_model_name,
            "fallback_model_name": "",
        })

    _sync_limiters: ClassVar[dict[tuple[str, int], threading.BoundedSemaphore]] = {}
    _async_limiters: ClassVar[
        weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            dict[tuple[str, int], asyncio.Semaphore],
        ]
    ] = weakref.WeakKeyDictionary()
    _limiter_lock: ClassVar[threading.Lock] = threading.Lock()

    def _validate_budget(self, messages: list[BaseMessage]) -> None:
        size = _content_size(messages)
        if size > self.input_char_budget:
            raise ModelBudgetExceeded(
                f"{self.gateway_name} input budget exceeded: "
                f"{size}>{self.input_char_budget} characters"
            )

    @contextmanager
    def _sync_slot(self):
        key = (self.gateway_name, self.max_concurrency)
        with self._limiter_lock:
            limiter = self._sync_limiters.setdefault(
                key,
                threading.BoundedSemaphore(self.max_concurrency),
            )
        limiter.acquire()
        try:
            yield
        finally:
            limiter.release()

    def _async_slot(self) -> asyncio.Semaphore:
        # asyncio 原语绑定事件循环，不能像线程信号量一样跨 loop 全局复用。
        loop = asyncio.get_running_loop()
        key = (self.gateway_name, self.max_concurrency)
        with self._limiter_lock:
            by_name = self._async_limiters.setdefault(loop, {})
            return by_name.setdefault(
                key,
                asyncio.Semaphore(self.max_concurrency),
            )

    def _record_result(self, result: ChatResult) -> None:
        _record_first_token()
        for generation in result.generations:
            usage = getattr(generation.message, "usage_metadata", None) or {}
            request_metrics.observe_tokens(
                self.gateway_name,
                int(usage.get("input_tokens", 0)),
                int(usage.get("output_tokens", 0)),
            )
            _record_budget_usage(
                int(usage.get("input_tokens", 0)),
                int(usage.get("output_tokens", 0)),
            )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._validate_budget(messages)
        _claim_budget_call(self.gateway_name)
        try:
            with self._sync_slot(), request_metrics.dependency(
                f"model_{self.gateway_name}"
            ):
                result = super()._generate(
                    messages,
                    stop=stop,
                    run_manager=run_manager,
                    **kwargs,
                )
            self._record_result(result)
            return result
        except Exception as exc:
            if self.fallback_model_name and not isinstance(exc, ModelBudgetExceeded):
                try:
                    _claim_budget_call(f"{self.gateway_name}_fallback")
                    fallback = self._fallback_copy()
                    with request_metrics.dependency(
                        f"model_{self.gateway_name}_fallback"
                    ):
                        result = ChatOpenAI._generate(
                            fallback, messages, stop=stop,
                            run_manager=run_manager, **kwargs,
                        )
                    self._record_result(result)
                    return result
                except Exception as fallback_error:
                    raise ModelUnavailable(
                        f"{self.gateway_name} primary and fallback unavailable"
                    ) from fallback_error
            _raise_gateway_error(self.gateway_name, exc)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._validate_budget(messages)
        _claim_budget_call(self.gateway_name)
        try:
            async with self._async_slot():
                with request_metrics.dependency(f"model_{self.gateway_name}"):
                    result = await super()._agenerate(
                        messages,
                        stop=stop,
                        run_manager=run_manager,
                        **kwargs,
                    )
            self._record_result(result)
            return result
        except Exception as exc:
            if self.fallback_model_name and not isinstance(exc, ModelBudgetExceeded):
                try:
                    _claim_budget_call(f"{self.gateway_name}_fallback")
                    fallback = self._fallback_copy()
                    async with fallback._async_slot():
                        with request_metrics.dependency(
                            f"model_{self.gateway_name}_fallback"
                        ):
                            result = await ChatOpenAI._agenerate(
                                fallback, messages, stop=stop,
                                run_manager=run_manager, **kwargs,
                            )
                    self._record_result(result)
                    return result
                except Exception as fallback_error:
                    raise ModelUnavailable(
                        f"{self.gateway_name} primary and fallback unavailable"
                    ) from fallback_error
            _raise_gateway_error(self.gateway_name, exc)

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        messages = args[0] if args else kwargs.get("messages", [])
        self._validate_budget(messages)
        _claim_budget_call(self.gateway_name)
        yielded_chunk = False
        restarts = 0
        while True:
            try:
                with self._sync_slot(), request_metrics.dependency(
                    f"model_{self.gateway_name}"
                ):
                    for chunk in super()._stream(*args, **kwargs):
                        yielded_chunk = True
                        _record_stream_chunk(self.gateway_name, chunk)
                        yield chunk
                if restarts:
                    request_metrics.observe_product(
                        "model_zero_chunk_stream_restart_recovered"
                    )
                return
            except Exception as exc:
                if isinstance(exc, ModelBudgetExceeded):
                    raise
                if (
                    not yielded_chunk
                    and restarts < self.zero_chunk_stream_restarts
                ):
                    restarts += 1
                    _claim_budget_call(f"{self.gateway_name}_stream_restart")
                    request_metrics.observe_product(
                        "model_zero_chunk_stream_restart_attempted"
                    )
                    continue
                if restarts and not yielded_chunk:
                    request_metrics.observe_product(
                        "model_zero_chunk_stream_restart_exhausted"
                    )
                if not yielded_chunk and self.fallback_model_name:
                    try:
                        _claim_budget_call(f"{self.gateway_name}_fallback")
                        fallback = self._fallback_copy()
                        with request_metrics.dependency(
                            f"model_{self.gateway_name}_fallback"
                        ):
                            for chunk in ChatOpenAI._stream(
                                fallback, *args, **kwargs
                            ):
                                yielded_chunk = True
                                _record_stream_chunk(
                                    f"{self.gateway_name}_fallback", chunk
                                )
                                yield chunk
                        return
                    except Exception as fallback_error:
                        raise ModelUnavailable(
                            f"{self.gateway_name} primary and fallback unavailable"
                        ) from fallback_error
                _raise_gateway_error(self.gateway_name, exc)

    async def _astream(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        messages = args[0] if args else kwargs.get("messages", [])
        self._validate_budget(messages)
        _claim_budget_call(self.gateway_name)
        yielded_chunk = False
        restarts = 0
        while True:
            try:
                async with self._async_slot():
                    with request_metrics.dependency(f"model_{self.gateway_name}"):
                        async for chunk in super()._astream(*args, **kwargs):
                            yielded_chunk = True
                            _record_stream_chunk(self.gateway_name, chunk)
                            yield chunk
                if restarts:
                    request_metrics.observe_product(
                        "model_zero_chunk_stream_restart_recovered"
                    )
                return
            except Exception as exc:
                if isinstance(exc, ModelBudgetExceeded):
                    raise
                if (
                    not yielded_chunk
                    and restarts < self.zero_chunk_stream_restarts
                ):
                    restarts += 1
                    _claim_budget_call(f"{self.gateway_name}_stream_restart")
                    request_metrics.observe_product(
                        "model_zero_chunk_stream_restart_attempted"
                    )
                    continue
                if restarts and not yielded_chunk:
                    request_metrics.observe_product(
                        "model_zero_chunk_stream_restart_exhausted"
                    )
                if not yielded_chunk and self.fallback_model_name:
                    try:
                        _claim_budget_call(f"{self.gateway_name}_fallback")
                        fallback = self._fallback_copy()
                        async with fallback._async_slot():
                            with request_metrics.dependency(
                                f"model_{self.gateway_name}_fallback"
                            ):
                                async for chunk in ChatOpenAI._astream(
                                    fallback, *args, **kwargs
                                ):
                                    yielded_chunk = True
                                    _record_stream_chunk(
                                        f"{self.gateway_name}_fallback", chunk
                                    )
                                    yield chunk
                        return
                    except Exception as fallback_error:
                        raise ModelUnavailable(
                            f"{self.gateway_name} primary and fallback unavailable"
                        ) from fallback_error
                _raise_gateway_error(self.gateway_name, exc)


class PolicyEmbeddings(OpenAIEmbeddings):
    """对向量化调用应用与聊天模型相同的预算和并发保护。"""

    gateway_name: str = "embeddings"
    input_char_budget: int
    max_concurrency: int

    _sync_limiter: ClassVar[threading.BoundedSemaphore | None] = None
    _sync_limiter_size: ClassVar[int] = 0
    _async_limiters: ClassVar[
        weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]
    ] = weakref.WeakKeyDictionary()
    _limiter_lock: ClassVar[threading.Lock] = threading.Lock()

    def _validate_texts(self, texts: list[str]) -> None:
        size = sum(len(text) for text in texts)
        if size > self.input_char_budget:
            raise ModelBudgetExceeded(
                f"embeddings input budget exceeded: "
                f"{size}>{self.input_char_budget} characters"
            )

    def _sync_slot(self) -> threading.BoundedSemaphore:
        with self._limiter_lock:
            if (
                self._sync_limiter is None
                or self._sync_limiter_size != self.max_concurrency
            ):
                type(self)._sync_limiter = threading.BoundedSemaphore(
                    self.max_concurrency
                )
                type(self)._sync_limiter_size = self.max_concurrency
            return self._sync_limiter

    def _async_slot(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        with self._limiter_lock:
            return self._async_limiters.setdefault(
                loop,
                asyncio.Semaphore(self.max_concurrency),
            )

    def embed_documents(
        self,
        texts: list[str],
        chunk_size: int | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        self._validate_texts(texts)
        limiter = self._sync_slot()
        limiter.acquire()
        try:
            with request_metrics.dependency("model_embeddings"):
                return super().embed_documents(
                    texts,
                    chunk_size=chunk_size,
                    **kwargs,
                )
        except Exception as exc:
            _raise_gateway_error("embeddings", exc)
        finally:
            limiter.release()

    async def aembed_documents(
        self,
        texts: list[str],
        chunk_size: int | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        self._validate_texts(texts)
        try:
            async with self._async_slot():
                with request_metrics.dependency("model_embeddings"):
                    return await super().aembed_documents(
                        texts,
                        chunk_size=chunk_size,
                        **kwargs,
                    )
        except Exception as exc:
            _raise_gateway_error("embeddings", exc)


def create_chat_model(
    purpose: str,
    *,
    temperature: float,
    streaming: bool = False,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    settings: Settings | None = None,
) -> PolicyChatOpenAI:
    """构建带统一策略的对话模型实例（外部模型唯一构造点之一）。

    应用输入预算、最大输出、超时、重试、并发、回退模型与结构化修复模型
    等策略。各参数缺省时回退到配置默认值。

    参数:
        purpose: 模型用途，决定选用哪个模型与是否允许回退。
        temperature: 采样温度。
        streaming: 是否启用流式。
        max_tokens / timeout_seconds / max_retries: 可覆盖配置的相应策略。

    异常:
        RuntimeError: 未配置 ``ZHIPU_API_KEY``。

    返回:
        绑定了全部策略的 ``PolicyChatOpenAI`` 实例。
    """
    current = settings or get_settings()
    if not current.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，无法调用模型。")
    output_limit = min(
        max_tokens or current.llm_max_output_tokens,
        current.llm_max_output_tokens,
    )
    fallback = fallback_policy(current, purpose)
    return PolicyChatOpenAI(
        gateway_name=purpose,
        input_char_budget=current.llm_input_char_budget,
        max_concurrency=current.llm_max_concurrency,
        schema_repair_model_name=model_for_purpose(current, "schema_repair"),
        fallback_model_name=fallback.fallback_model or "",
        zero_chunk_stream_restarts=current.llm_zero_chunk_stream_restarts,
        model=model_for_purpose(current, purpose),
        api_key=current.zhipu_api_key,
        base_url=current.zhipu_api_base,
        temperature=temperature,
        streaming=streaming,
        max_tokens=output_limit,
        timeout=(
            timeout_seconds
            if timeout_seconds is not None
            else current.llm_timeout_seconds
        ),
        max_retries=(
            max_retries
            if max_retries is not None
            else current.llm_max_retries
        ),
    )


def create_embeddings(
    *,
    settings: Settings | None = None,
) -> PolicyEmbeddings:
    """构建带预算与并发保护的向量化模型实例（外部 Embedding 唯一构造点）。

    API Key 优先用 Embedding 专用 Key，回退到通用 Zhipu Key。

    异常:
        RuntimeError: 未配置任何可用 Key。

    返回:
        绑定策略的 ``PolicyEmbeddings`` 实例。
    """
    current = settings or get_settings()
    api_key = current.zhipu_embedding_api_key or current.zhipu_api_key
    if not api_key:
        raise RuntimeError("未配置 ZHIPU_EMBEDDING_API_KEY。")
    return PolicyEmbeddings(
        input_char_budget=current.llm_input_char_budget,
        max_concurrency=current.llm_max_concurrency,
        model=current.zhipu_embedding_model,
        api_key=api_key,
        base_url=current.zhipu_embedding_api_base,
        check_embedding_ctx_length=False,
        chunk_size=8,
        request_timeout=current.llm_timeout_seconds,
        max_retries=current.llm_max_retries,
    )
