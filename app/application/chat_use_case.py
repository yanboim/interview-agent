"""完整聊天用例：统一普通/流式回合的执行、证据、追踪与持久终态。"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging
import time
from typing import Any, Literal, Protocol

from app.agent_context import reset_conversation_context, set_conversation_context
from app.application.chat_execution import ChatAgentExecutor, ChatExecutionRequest
from app.application.chat_service import ChatTurnService
from app.application.execution import SyncExecutor
from app.chat_evidence import build_citation_metadata, extract_sources
from app.model_gateway import ModelBudgetExceeded, ModelGatewayError
from app.model_routing import ModelUnavailable
from app.tool_context import reset_tool_identity, set_tool_identity

logger = logging.getLogger(__name__)


class ChatTraceRepository(Protocol):
    def record_execution_trace(self, **kwargs: Any) -> object: ...


@dataclass(frozen=True, slots=True)
class ChatCommand:
    user_id: str
    role: str
    session_id: str
    message: str
    idempotency_key: str
    request_id: str = ""


@dataclass(frozen=True, slots=True)
class ChatResult:
    user_id: str
    session_id: str
    turn_id: str
    answer: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ChatStreamEvent:
    kind: Literal["token", "sources", "citations", "done", "error"]
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class PreparedChatStream:
    command: ChatCommand
    claim: dict[str, object]


class ChatUseCaseError(RuntimeError):
    """可由 HTTP 适配器稳定映射的聊天用例错误。"""


class ChatExecutionTimeout(ChatUseCaseError):
    pass


class ChatExecutionUnavailable(ChatUseCaseError):
    pass


class ChatExecutionFailed(ChatUseCaseError):
    pass


class ChatUseCase:
    def __init__(
        self,
        *,
        turn_service: ChatTurnService,
        agent_executor: ChatAgentExecutor,
        sync_executor: SyncExecutor,
        trace_repository: ChatTraceRepository,
        metrics: Any,
        settings: Any,
    ) -> None:
        self.turn_service = turn_service
        self.agent_executor = agent_executor
        self.sync_executor = sync_executor
        self.trace_repository = trace_repository
        self.metrics = metrics
        self.settings = settings

    async def _begin(self, command: ChatCommand) -> dict[str, object]:
        return await self.sync_executor.run(
            self.turn_service.begin,
            user_id=command.user_id,
            session_id=command.session_id,
            content=command.message,
            idempotency_key=command.idempotency_key,
            role=command.role,
        )

    async def _record_trace(
        self,
        command: ChatCommand,
        claim: dict[str, object],
        *,
        stage: str,
        status: str,
        duration_ms: int | None = None,
        detail: dict[str, object] | None = None,
        model_version: str | None = None,
    ) -> None:
        try:
            await self.sync_executor.run(
                self.trace_repository.record_execution_trace,
                request_id=command.request_id,
                user_id=command.user_id,
                interaction_type="chat",
                interaction_id=str(claim["turn_id"]),
                stage=stage,
                status=status,
                duration_ms=duration_ms,
                detail=detail or {},
                prompt_version=self.settings.agent_prompt_version,
                schema_version="agent-schema-v1",
                model_version=model_version or self.settings.zhipu_model,
            )
        except Exception:
            logger.warning("Chat execution trace write failed.", exc_info=True)

    @staticmethod
    def _source_map(evidence: list[Any]) -> dict[tuple[str, str, str, str], dict[str, str]]:
        sources: list[dict[str, str]] = []
        for item in evidence:
            sources.extend(extract_sources(item.tool_name, item.content))
        return {
            (
                source["kind"],
                source.get("evidence_id", ""),
                source["label"],
                source.get("url", ""),
            ): source
            for source in sources
        }

    def _metadata(
        self,
        *,
        claim: dict[str, object],
        answer: str,
        source_map: dict[tuple[str, str, str, str], dict[str, str]],
        model_version: str,
    ) -> dict[str, object]:
        sources = list(source_map.values())
        return {
            "turn_id": str(claim["turn_id"]),
            "prompt_version": self.settings.agent_prompt_version,
            "schema_version": "specialist-result-v1",
            "model_version": model_version,
            "knowledge_used": any(source["kind"] == "private" for source in sources),
            "sources": sources,
            **build_citation_metadata(answer, sources),
        }

    def _observe_completion(self, metadata: dict[str, object]) -> None:
        citations = list(metadata["citations"])  # type: ignore[arg-type]
        self.metrics.observe_product("answers_completed")
        self.metrics.observe_product("grounded_claims_total", len(citations))
        self.metrics.observe_product(
            "grounded_claims_supported",
            sum(
                isinstance(item, dict) and item.get("support") == "supported"
                for item in citations
            ),
        )

    @staticmethod
    def _set_context(command: ChatCommand, claim: dict[str, object]):
        identity = set_tool_identity(
            command.user_id,
            command.role,
            request_id=command.request_id,
            interaction_type="chat",
            interaction_id=str(claim["turn_id"]),
        )
        conversation = set_conversation_context(
            [item for item in claim["messages"] if isinstance(item, dict)],
            claim.get("context_snapshot"),
        )
        return identity, conversation

    async def _fail(
        self,
        command: ChatCommand,
        claim: dict[str, object],
        *,
        partial_answer: str,
        error: str,
        status: str,
        started: float,
        retryable: bool = False,
        streaming: bool = False,
    ) -> None:
        await self.sync_executor.run(
            self.turn_service.fail,
            claim,
            partial_answer=partial_answer,
            error=error,
        )
        await self._record_trace(
            command,
            claim,
            stage="agent_execution",
            status=status,
            duration_ms=int((time.monotonic() - started) * 1000),
            detail={
                "error_type": error.split(":", 1)[0],
                "retryable": retryable,
                "streaming": streaming,
            },
        )

    async def execute(self, command: ChatCommand) -> ChatResult:
        claim = await self._begin(command)
        if claim["outcome"] == "completed":
            await self._record_trace(
                command,
                claim,
                stage="response_replay",
                status="completed",
                detail={"idempotent_replay": True},
            )
            return ChatResult(
                user_id=command.user_id,
                session_id=command.session_id,
                turn_id=str(claim["turn_id"]),
                answer=str(claim["answer"]),
                replayed=True,
            )

        identity, conversation = self._set_context(command, claim)
        answer = ""
        started = time.monotonic()
        try:
            execution = await self.agent_executor.invoke(
                ChatExecutionRequest(
                    message=command.message,
                    user_id=command.user_id,
                    role=command.role,
                    messages=list(claim["messages"]),
                )
            )
            answer = execution.answer or "Agent 没有返回文本内容。"
            source_map = self._source_map(execution.evidence)
            metadata = self._metadata(
                claim=claim,
                answer=answer,
                source_map=source_map,
                model_version=execution.model_version,
            )
            self._observe_completion(metadata)
            await self.sync_executor.run(
                self.turn_service.complete,
                claim,
                user_id=command.user_id,
                session_id=command.session_id,
                answer=answer,
                metadata=metadata,
            )
            await self._record_trace(
                command,
                claim,
                stage="agent_execution",
                status="completed",
                duration_ms=int((time.monotonic() - started) * 1000),
                detail={
                    "model": execution.model_version,
                    "knowledge_used": metadata["knowledge_used"],
                    "source_count": len(source_map),
                    "model_run": execution.budget,
                },
                model_version=execution.model_version,
            )
            return ChatResult(
                user_id=command.user_id,
                session_id=command.session_id,
                turn_id=str(claim["turn_id"]),
                answer=answer,
                replayed=False,
            )
        except asyncio.TimeoutError as exc:
            await self._fail(
                command, claim, partial_answer=answer,
                error="TimeoutError: agent timeout", status="timeout", started=started,
            )
            raise ChatExecutionTimeout("Agent 响应超时，请稍后重试。") from exc
        except (ModelBudgetExceeded, ModelGatewayError, ModelUnavailable) as exc:
            await self._fail(
                command, claim, partial_answer=answer,
                error=f"{type(exc).__name__}: recoverable model unavailable",
                status="unavailable", started=started, retryable=True,
            )
            raise ChatExecutionUnavailable(
                "模型服务暂时不可用，本次操作未完成，请稍后安全重试。"
            ) from exc
        except Exception as exc:
            await self._fail(
                command, claim, partial_answer=answer,
                error=f"{type(exc).__name__}: {exc}", status="failed", started=started,
            )
            logger.exception("Agent execution failed for session %s", command.session_id)
            raise ChatExecutionFailed("Agent 执行失败，请稍后重试。") from exc
        finally:
            reset_conversation_context(conversation)
            reset_tool_identity(identity)

    async def prepare_stream(self, command: ChatCommand) -> PreparedChatStream:
        return PreparedChatStream(command=command, claim=await self._begin(command))

    async def stream(
        self, prepared: PreparedChatStream
    ) -> AsyncIterator[ChatStreamEvent]:
        command, claim = prepared.command, prepared.claim
        if claim["outcome"] == "completed":
            answer = str(claim["answer"])
            metadata = dict(claim["metadata"])  # type: ignore[arg-type]
            if answer:
                yield ChatStreamEvent("token", {"content": answer})
            sources = list(metadata.get("sources", []))
            if sources or metadata.get("knowledge_used"):
                yield ChatStreamEvent(
                    "sources",
                    {
                        "knowledge_used": bool(metadata.get("knowledge_used", False)),
                        "sources": sources,
                    },
                )
            if "schema_version" in metadata:
                yield ChatStreamEvent(
                    "citations",
                    {
                        "schema_version": metadata["schema_version"],
                        "citations": metadata.get("citations", []),
                        "unsupported_claims": metadata.get("unsupported_claims", []),
                    },
                )
            await self._record_trace(
                command, claim, stage="response_replay", status="completed",
                detail={"idempotent_replay": True, "streaming": True},
            )
            yield ChatStreamEvent(
                "done",
                {
                    "user_id": command.user_id,
                    "session_id": command.session_id,
                    "turn_id": claim["turn_id"],
                    "replayed": True,
                },
            )
            return

        answer_parts: list[str] = []
        source_map: dict[tuple[str, str, str, str], dict[str, str]] = {}
        identity, conversation = self._set_context(command, claim)
        started = time.monotonic()
        try:
            completed = None
            async for event in self.agent_executor.stream(
                ChatExecutionRequest(
                    message=command.message,
                    user_id=command.user_id,
                    role=command.role,
                    messages=list(claim["messages"]),
                )
            ):
                if event.kind == "token":
                    answer_parts.append(event.content)
                    yield ChatStreamEvent("token", {"content": event.content})
                elif event.kind == "evidence":
                    for source in extract_sources(event.tool_name, event.content):
                        key = (
                            source["kind"], source.get("evidence_id", ""),
                            source["label"], source.get("url", ""),
                        )
                        source_map[key] = source
                else:
                    completed = event
            if completed is None:
                raise RuntimeError("chat executor stream ended without completion")
            answer = "".join(answer_parts) or "Agent 没有返回文本内容。"
            metadata = self._metadata(
                claim=claim,
                answer=answer,
                source_map=source_map,
                model_version=completed.model_version,
            )
            self._observe_completion(metadata)
            if metadata["knowledge_used"] or source_map:
                yield ChatStreamEvent("sources", metadata)
            yield ChatStreamEvent(
                "citations",
                {
                    "schema_version": metadata["schema_version"],
                    "citations": metadata["citations"],
                    "unsupported_claims": metadata["unsupported_claims"],
                },
            )
            await self.sync_executor.run(
                self.turn_service.complete,
                claim,
                user_id=command.user_id,
                session_id=command.session_id,
                answer=answer,
                metadata=metadata,
            )
            await self._record_trace(
                command,
                claim,
                stage="agent_execution",
                status="completed",
                duration_ms=int((time.monotonic() - started) * 1000),
                detail={
                    "model": completed.model_version,
                    "knowledge_used": metadata["knowledge_used"],
                    "source_count": len(source_map),
                    "streaming": True,
                    "model_run": completed.budget or {},
                },
                model_version=completed.model_version,
            )
            yield ChatStreamEvent(
                "done",
                {
                    "user_id": command.user_id,
                    "session_id": command.session_id,
                    "turn_id": claim["turn_id"],
                    "replayed": False,
                },
            )
        except (asyncio.CancelledError, GeneratorExit):
            await self.sync_executor.run(
                self.turn_service.cancel,
                claim,
                partial_answer="".join(answer_parts),
            )
            await self._record_trace(
                command, claim, stage="agent_execution", status="cancelled",
                duration_ms=int((time.monotonic() - started) * 1000),
                detail={"streaming": True},
            )
            raise
        except asyncio.TimeoutError:
            await self._fail(
                command, claim, partial_answer="".join(answer_parts),
                error="TimeoutError: agent timeout", status="timeout", started=started,
                streaming=True,
            )
            yield ChatStreamEvent("error", {"detail": "Agent 响应超时，请稍后重试。"})
        except (ModelBudgetExceeded, ModelGatewayError, ModelUnavailable) as exc:
            await self._fail(
                command, claim, partial_answer="".join(answer_parts),
                error=f"{type(exc).__name__}: recoverable model unavailable",
                status="unavailable", started=started, retryable=True, streaming=True,
            )
            yield ChatStreamEvent(
                "error",
                {
                    "code": "model_unavailable",
                    "retryable": True,
                    "detail": "模型服务暂时不可用，本次操作未完成，请稍后安全重试。",
                },
            )
        except Exception as exc:
            await self._fail(
                command, claim, partial_answer="".join(answer_parts),
                error=f"{type(exc).__name__}: {exc}", status="failed", started=started,
                streaming=True,
            )
            logger.exception("Streaming Agent execution failed for %s", command.session_id)
            yield ChatStreamEvent("error", {"detail": "Agent 执行失败，请稍后重试。"})
        finally:
            reset_conversation_context(conversation)
            reset_tool_identity(identity)
