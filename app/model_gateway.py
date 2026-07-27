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


class ModelGatewayError(RuntimeError):
    """Provider-safe error exposed to application services."""


class ModelBudgetExceeded(ModelGatewayError):
    """The request exceeded its input budget before provider I/O."""


def _content_size(messages: list[BaseMessage]) -> int:
    return sum(len(str(message.content)) for message in messages)


def _raise_gateway_error(name: str, exc: Exception) -> None:
    if isinstance(exc, ModelGatewayError):
        raise exc
    raise ModelGatewayError(
        f"{name} model call failed ({type(exc).__name__})"
    ) from exc


class PolicyChatOpenAI(ChatOpenAI):
    gateway_name: str
    input_char_budget: int
    max_concurrency: int

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
        loop = asyncio.get_running_loop()
        key = (self.gateway_name, self.max_concurrency)
        with self._limiter_lock:
            by_name = self._async_limiters.setdefault(loop, {})
            return by_name.setdefault(
                key,
                asyncio.Semaphore(self.max_concurrency),
            )

    def _record_result(self, result: ChatResult) -> None:
        for generation in result.generations:
            usage = getattr(generation.message, "usage_metadata", None) or {}
            request_metrics.observe_tokens(
                self.gateway_name,
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
            _raise_gateway_error(self.gateway_name, exc)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._validate_budget(messages)
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
            _raise_gateway_error(self.gateway_name, exc)

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        messages = args[0] if args else kwargs.get("messages", [])
        self._validate_budget(messages)
        try:
            with self._sync_slot(), request_metrics.dependency(
                f"model_{self.gateway_name}"
            ):
                for chunk in super()._stream(*args, **kwargs):
                    usage = getattr(chunk.message, "usage_metadata", None) or {}
                    request_metrics.observe_tokens(
                        self.gateway_name,
                        int(usage.get("input_tokens", 0)),
                        int(usage.get("output_tokens", 0)),
                    )
                    yield chunk
        except Exception as exc:
            _raise_gateway_error(self.gateway_name, exc)

    async def _astream(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        messages = args[0] if args else kwargs.get("messages", [])
        self._validate_budget(messages)
        try:
            async with self._async_slot():
                with request_metrics.dependency(f"model_{self.gateway_name}"):
                    async for chunk in super()._astream(*args, **kwargs):
                        usage = (
                            getattr(chunk.message, "usage_metadata", None) or {}
                        )
                        request_metrics.observe_tokens(
                            self.gateway_name,
                            int(usage.get("input_tokens", 0)),
                            int(usage.get("output_tokens", 0)),
                        )
                        yield chunk
        except Exception as exc:
            _raise_gateway_error(self.gateway_name, exc)


class PolicyEmbeddings(OpenAIEmbeddings):
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
    settings: Settings | None = None,
) -> PolicyChatOpenAI:
    current = settings or get_settings()
    if not current.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，无法调用模型。")
    output_limit = min(
        max_tokens or current.llm_max_output_tokens,
        current.llm_max_output_tokens,
    )
    return PolicyChatOpenAI(
        gateway_name=purpose,
        input_char_budget=current.llm_input_char_budget,
        max_concurrency=current.llm_max_concurrency,
        model=current.zhipu_model,
        api_key=current.zhipu_api_key,
        base_url=current.zhipu_api_base,
        temperature=temperature,
        streaming=streaming,
        max_tokens=output_limit,
        timeout=current.llm_timeout_seconds,
        max_retries=current.llm_max_retries,
    )


def create_embeddings(
    *,
    settings: Settings | None = None,
) -> PolicyEmbeddings:
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
