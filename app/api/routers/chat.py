"""聊天 HTTP/NDJSON 适配器：包围持久回合生命周期并处理取消和超时。"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage

from app.api.agent_io import (
    build_citation_metadata,
    extract_message_text,
    extract_sources,
)
from app.api.execution import run_sync
from app.api.runtime import get_runtime
from app.api.schemas import (
    AssistantFeedbackRequest,
    ChatRequest,
    ChatResponse,
    EvaluationCandidateReviewRequest,
)
from app.api.security import resolve_user_id
from app.api.security import require_role
from app.agent_context import (
    reset_conversation_context,
    set_conversation_context,
)
from app.agent import route_purpose, select_interview_agent
from app.agent_budget import agent_execution_budget
from app.application.chat_service import ChatTurnConflict
from app.chat_context import ChatContextBudgetExceeded
from app.operations import request_metrics
from app.model_gateway import ModelBudgetExceeded, ModelGatewayError
from app.model_routing import ModelUnavailable, model_for_purpose
from app.tool_context import reset_tool_identity, set_tool_identity

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put("/api/chat/turns/{turn_id}/feedback")
async def save_assistant_feedback(
    turn_id: str,
    payload: AssistantFeedbackRequest,
    request: Request,
) -> dict[str, object]:
    user_id = resolve_user_id(request, payload.user_id)
    feedback = await run_sync(
        get_runtime().conversation_store.upsert_assistant_feedback,
        user_id=user_id,
        turn_id=turn_id,
        rating=payload.rating,
        reason_code=payload.reason_code,
        comment=payload.comment.strip() if payload.comment else None,
    )
    if not feedback:
        raise HTTPException(status_code=404, detail="可评价的助手回合不存在")
    request_metrics.observe_product("feedback_submitted")
    request_metrics.observe_product(f"feedback_{payload.rating}")
    return feedback


@router.delete("/api/chat/turns/{turn_id}/feedback")
async def delete_assistant_feedback(
    turn_id: str, user_id: str, request: Request
) -> dict[str, bool]:
    user_id = resolve_user_id(request, user_id)
    deleted = await run_sync(
        get_runtime().conversation_store.delete_assistant_feedback,
        user_id=user_id,
        turn_id=turn_id,
    )
    return {"deleted": deleted}


@router.get("/api/admin/evaluation-candidates")
async def list_evaluation_candidates(
    request: Request,
    status: str = "pending_privacy_review",
) -> list[dict[str, object]]:
    require_role(request, {"admin"})
    if status not in {"pending_privacy_review", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="候选状态不合法")
    return await run_sync(
        get_runtime().conversation_store.list_evaluation_candidates,
        status=status,
    )


@router.post("/api/admin/evaluation-candidates/{candidate_id}/review")
async def review_evaluation_candidate(
    candidate_id: str,
    payload: EvaluationCandidateReviewRequest,
    request: Request,
) -> dict[str, object]:
    reviewer = require_role(request, {"admin"})
    try:
        reviewed = await run_sync(
            get_runtime().conversation_store.review_evaluation_candidate,
            candidate_id=candidate_id,
            reviewer_id=reviewer.user_id,
            decision=payload.decision,
            approved_payload=payload.approved_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not reviewed:
        raise HTTPException(status_code=404, detail="待审核评测候选不存在")
    return reviewed


async def _record_chat_trace(
    http_request: Request,
    *,
    user_id: str,
    turn_id: str,
    stage: str,
    status: str,
    duration_ms: int | None = None,
    detail: dict[str, object] | None = None,
    model_version: str | None = None,
) -> None:
    try:
        settings = get_runtime().settings
        await run_sync(
            get_runtime().conversation_store.record_execution_trace,
            request_id=str(getattr(http_request.state, "request_id", "")),
            user_id=user_id,
            interaction_type="chat",
            interaction_id=turn_id,
            stage=stage,
            status=status,
            duration_ms=duration_ms,
            detail=detail or {},
            prompt_version=settings.agent_prompt_version,
            schema_version="agent-schema-v1",
            model_version=model_version or model_for_purpose(settings, "supervisor"),
        )
    except Exception:
        logger.warning("Chat execution trace write failed.", exc_info=True)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> ChatResponse:
    runtime = get_runtime()
    user_id = resolve_user_id(http_request, request.user_id)
    current_user = getattr(http_request.state, "current_user", None)
    try:
        claim = await run_sync(
            runtime.chat_turn_service.begin,
            user_id=user_id,
            session_id=request.session_id,
            content=request.message,
            idempotency_key=idempotency_key,
            role=current_user.role if current_user else "user",
        )
    except ChatContextBudgetExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ChatTurnConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Retry-After": "1"} if exc.retryable else None,
        ) from exc
    if claim["outcome"] == "completed":
        await _record_chat_trace(
            http_request,
            user_id=user_id,
            turn_id=str(claim["turn_id"]),
            stage="response_replay",
            status="completed",
            detail={"idempotent_replay": True},
        )
        return ChatResponse(
            user_id=user_id,
            session_id=request.session_id,
            turn_id=str(claim["turn_id"]),
            answer=str(claim["answer"]),
        )

    identity_token = set_tool_identity(
        user_id,
        current_user.role if current_user else "user",
        request_id=str(getattr(http_request.state, "request_id", "")),
        interaction_type="chat",
        interaction_id=str(claim["turn_id"]),
    )
    answer = ""
    agent_started = time.monotonic()
    context_token = set_conversation_context(
        [item for item in claim["messages"] if isinstance(item, dict)],
        claim.get("context_snapshot"),
    )
    try:
        selected_agent = select_interview_agent(
            message=request.message,
            user_id=user_id,
            role=current_user.role if current_user else "user",
            default_agent=runtime.get_interview_agent(),
            settings=runtime.settings,
        )
        selected_purpose = route_purpose(
            message=request.message, user_id=user_id,
            role=current_user.role if current_user else "user",
            settings=runtime.settings,
        )
        selected_model_version = model_for_purpose(
            runtime.settings, selected_purpose
        )
        with agent_execution_budget(runtime.settings, "chat") as run_budget:
            with request_metrics.dependency("glm"):
                result = await asyncio.wait_for(
                    selected_agent.ainvoke(
                        {"messages": claim["messages"]},
                        config={
                            "recursion_limit": runtime.settings.agent_recursion_limit
                        },
                    ),
                    timeout=runtime.settings.chat_agent_timeout_seconds,
                )
        answer = extract_message_text(result["messages"][-1])
        request_metrics.observe_model_run(run_budget.snapshot())
        sources: list[dict[str, str]] = []
        for result_message in result["messages"]:
            if not isinstance(result_message, ToolMessage):
                continue
            sources.extend(
                extract_sources(
                    str(getattr(result_message, "name", "") or ""),
                    extract_message_text(result_message),
                )
            )
        source_map = {
            (
                source["kind"],
                source.get("evidence_id", ""),
                source["label"],
                source.get("url", ""),
            ): source
            for source in sources
        }
        metadata_payload = {
            "turn_id": str(claim["turn_id"]),
            "prompt_version": runtime.settings.agent_prompt_version,
            "schema_version": "specialist-result-v1",
            "model_version": selected_model_version,
            "knowledge_used": any(
                source["kind"] == "private" for source in source_map.values()
            ),
            "sources": list(source_map.values()),
            **build_citation_metadata(answer, list(source_map.values())),
        }
        request_metrics.observe_product("answers_completed")
        request_metrics.observe_product(
            "grounded_claims_total", len(metadata_payload["citations"])
        )
        request_metrics.observe_product(
            "grounded_claims_supported",
            sum(
                item.get("support") == "supported"
                for item in metadata_payload["citations"]
            ),
        )
        await run_sync(
            runtime.chat_turn_service.complete,
            claim,
            user_id=user_id,
            session_id=request.session_id,
            answer=answer,
            metadata=metadata_payload,
        )
        await _record_chat_trace(
            http_request,
            user_id=user_id,
            turn_id=str(claim["turn_id"]),
            stage="agent_execution",
            status="completed",
            duration_ms=int(
                (time.monotonic() - agent_started) * 1000
            ),
            detail={
                "model": selected_model_version,
                "knowledge_used": metadata_payload["knowledge_used"],
                "source_count": len(source_map),
                "model_run": run_budget.snapshot(),
            },
            model_version=selected_model_version,
        )
        return ChatResponse(
            user_id=user_id,
            session_id=request.session_id,
            turn_id=str(claim["turn_id"]),
            answer=answer,
        )
    except asyncio.TimeoutError as exc:
        await run_sync(
            runtime.chat_turn_service.fail,
            claim,
            partial_answer=answer,
            error=f"{type(exc).__name__}: agent timeout",
        )
        await _record_chat_trace(
            http_request,
            user_id=user_id,
            turn_id=str(claim["turn_id"]),
            stage="agent_execution",
            status="timeout",
            duration_ms=int(
                (time.monotonic() - agent_started) * 1000
            ),
            detail={"error_type": "TimeoutError"},
        )
        logger.warning("Agent execution timed out for session %s", request.session_id)
        raise HTTPException(
            status_code=504,
            detail="Agent 响应超时，请稍后重试。",
        ) from exc
    except (ModelBudgetExceeded, ModelGatewayError, ModelUnavailable) as exc:
        await run_sync(
            runtime.chat_turn_service.fail,
            claim,
            partial_answer=answer,
            error=f"{type(exc).__name__}: recoverable model unavailable",
        )
        await _record_chat_trace(
            http_request,
            user_id=user_id,
            turn_id=str(claim["turn_id"]),
            stage="agent_execution",
            status="unavailable",
            duration_ms=int((time.monotonic() - agent_started) * 1000),
            detail={"error_type": type(exc).__name__, "retryable": True},
        )
        raise HTTPException(
            status_code=503,
            detail="模型服务暂时不可用，本次操作未完成，请稍后安全重试。",
        ) from exc
    except Exception as exc:
        await run_sync(
            runtime.chat_turn_service.fail,
            claim,
            partial_answer=answer,
            error=f"{type(exc).__name__}: {exc}",
        )
        await _record_chat_trace(
            http_request,
            user_id=user_id,
            turn_id=str(claim["turn_id"]),
            stage="agent_execution",
            status="failed",
            duration_ms=int(
                (time.monotonic() - agent_started) * 1000
            ),
            detail={"error_type": type(exc).__name__},
        )
        logger.exception("Agent execution failed for session %s", request.session_id)
        # 不向客户端透传内部异常详情(可能含路径/SQL/供应商错误),只返回通用文案。
        raise HTTPException(
            status_code=500,
            detail="Agent 执行失败，请稍后重试。",
        ) from exc
    finally:
        reset_conversation_context(context_token)
        reset_tool_identity(identity_token)


@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> StreamingResponse:
    runtime = get_runtime()
    user_id = resolve_user_id(http_request, request.user_id)
    current_user = getattr(http_request.state, "current_user", None)
    try:
        claim = await run_sync(
            runtime.chat_turn_service.begin,
            user_id=user_id,
            session_id=request.session_id,
            content=request.message,
            idempotency_key=idempotency_key,
            role=current_user.role if current_user else "user",
        )
    except ChatContextBudgetExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ChatTurnConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Retry-After": "1"} if exc.retryable else None,
        ) from exc

    async def generate():
        if claim["outcome"] == "completed":
            answer = str(claim["answer"])
            metadata = dict(claim["metadata"])  # type: ignore[arg-type]
            if answer:
                yield json.dumps(
                    {"type": "token", "content": answer}, ensure_ascii=False
                ) + "\n"
            if metadata:
                sources = list(metadata.get("sources", []))
                if sources or metadata.get("knowledge_used"):
                    yield json.dumps(
                        {
                            "type": "sources",
                            "knowledge_used": bool(
                                metadata.get("knowledge_used", False)
                            ),
                            "sources": sources,
                        },
                        ensure_ascii=False,
                    ) + "\n"
                if "schema_version" in metadata:
                    yield json.dumps(
                        {
                            "type": "citations",
                            "schema_version": metadata["schema_version"],
                            "citations": metadata.get("citations", []),
                            "unsupported_claims": metadata.get(
                                "unsupported_claims", []
                            ),
                        },
                        ensure_ascii=False,
                    ) + "\n"
            yield json.dumps(
                {
                    "type": "done",
                    "user_id": user_id,
                    "session_id": request.session_id,
                    "turn_id": claim["turn_id"],
                    "replayed": True,
                },
                ensure_ascii=False,
            ) + "\n"
            return

        answer_parts: list[str] = []
        source_map: dict[tuple[str, str, str, str], dict[str, str]] = {}
        knowledge_used = False
        identity_token = set_tool_identity(
            user_id,
            current_user.role if current_user else "user",
            request_id=str(
                getattr(http_request.state, "request_id", "")
            ),
            interaction_type="chat",
            interaction_id=str(claim["turn_id"]),
        )
        agent_started = time.monotonic()
        context_token = set_conversation_context(
            [item for item in claim["messages"] if isinstance(item, dict)],
            claim.get("context_snapshot"),
        )
        try:
            selected_agent = select_interview_agent(
                message=request.message,
                user_id=user_id,
                role=current_user.role if current_user else "user",
                default_agent=runtime.get_interview_agent(),
                settings=runtime.settings,
            )
            selected_purpose = route_purpose(
                message=request.message, user_id=user_id,
                role=current_user.role if current_user else "user",
                settings=runtime.settings,
            )
            selected_model_version = model_for_purpose(
                runtime.settings, selected_purpose
            )
            with agent_execution_budget(runtime.settings, "chat") as run_budget:
                with request_metrics.dependency("glm"):
                    async with asyncio.timeout(
                        runtime.settings.chat_agent_timeout_seconds
                    ):
                        async for message, _ in selected_agent.astream(
                            {"messages": claim["messages"]},
                            stream_mode="messages",
                            config={
                                "recursion_limit": runtime.settings.agent_recursion_limit
                            },
                        ):
                            if isinstance(message, ToolMessage):
                                tool_name = str(
                                    getattr(message, "name", "") or ""
                                )
                                tool_content = extract_message_text(message)
                                for source in extract_sources(
                                    tool_name, tool_content
                                ):
                                    key = (
                                        source["kind"],
                                        source.get("evidence_id", ""),
                                        source["label"],
                                        source.get("url", ""),
                                    )
                                    source_map[key] = source
                                    knowledge_used = (
                                        knowledge_used
                                        or source["kind"] == "private"
                                    )
                                continue
                            if not isinstance(message, AIMessageChunk):
                                continue
                            text = extract_message_text(message)
                            if not text:
                                continue
                            answer_parts.append(text)
                            yield json.dumps(
                                {"type": "token", "content": text}, ensure_ascii=False
                            ) + "\n"

            answer = "".join(answer_parts) or "Agent 没有返回文本内容。"
            request_metrics.observe_model_run(run_budget.snapshot())
            metadata_payload = {
                "turn_id": str(claim["turn_id"]),
                "prompt_version": runtime.settings.agent_prompt_version,
                "schema_version": "specialist-result-v1",
                "model_version": selected_model_version,
                "knowledge_used": knowledge_used,
                "sources": list(source_map.values()),
                **build_citation_metadata(answer, list(source_map.values())),
            }
            request_metrics.observe_product("answers_completed")
            request_metrics.observe_product(
                "grounded_claims_total", len(metadata_payload["citations"])
            )
            request_metrics.observe_product(
                "grounded_claims_supported",
                sum(
                    item.get("support") == "supported"
                    for item in metadata_payload["citations"]
                ),
            )
            if knowledge_used or source_map:
                yield json.dumps(
                    {"type": "sources", **metadata_payload}, ensure_ascii=False
                ) + "\n"
            yield json.dumps(
                {
                    "type": "citations",
                    "schema_version": metadata_payload["schema_version"],
                    "citations": metadata_payload["citations"],
                    "unsupported_claims": metadata_payload[
                        "unsupported_claims"
                    ],
                },
                ensure_ascii=False,
            ) + "\n"
            await run_sync(
                runtime.chat_turn_service.complete,
                claim,
                user_id=user_id,
                session_id=request.session_id,
                answer=answer,
                metadata=metadata_payload,
            )
            await _record_chat_trace(
                http_request,
                user_id=user_id,
                turn_id=str(claim["turn_id"]),
                stage="agent_execution",
                status="completed",
                duration_ms=int(
                    (time.monotonic() - agent_started) * 1000
                ),
                detail={
                    "model": selected_model_version,
                    "knowledge_used": knowledge_used,
                    "source_count": len(source_map),
                    "streaming": True,
                    "model_run": run_budget.snapshot(),
                },
                model_version=selected_model_version,
            )
            yield json.dumps(
                {
                    "type": "done",
                    "user_id": user_id,
                    "session_id": request.session_id,
                    "turn_id": claim["turn_id"],
                    "replayed": False,
                },
                ensure_ascii=False,
            ) + "\n"
        except (asyncio.CancelledError, GeneratorExit):
            runtime.chat_turn_service.cancel(
                claim, partial_answer="".join(answer_parts)
            )
            await _record_chat_trace(
                http_request,
                user_id=user_id,
                turn_id=str(claim["turn_id"]),
                stage="agent_execution",
                status="cancelled",
                duration_ms=int(
                    (time.monotonic() - agent_started) * 1000
                ),
                detail={"streaming": True},
            )
            raise
        except asyncio.TimeoutError:
            await run_sync(
                runtime.chat_turn_service.fail,
                claim,
                partial_answer="".join(answer_parts),
                error="TimeoutError: agent timeout",
            )
            await _record_chat_trace(
                http_request,
                user_id=user_id,
                turn_id=str(claim["turn_id"]),
                stage="agent_execution",
                status="timeout",
                duration_ms=int(
                    (time.monotonic() - agent_started) * 1000
                ),
                detail={"error_type": "TimeoutError", "streaming": True},
            )
            logger.warning(
                "Streaming agent execution timed out for session %s",
                request.session_id,
            )
            yield json.dumps(
                {"type": "error", "detail": "Agent 响应超时，请稍后重试。"},
                ensure_ascii=False,
            ) + "\n"
        except (ModelBudgetExceeded, ModelGatewayError, ModelUnavailable) as exc:
            await run_sync(
                runtime.chat_turn_service.fail,
                claim,
                partial_answer="".join(answer_parts),
                error=f"{type(exc).__name__}: recoverable model unavailable",
            )
            await _record_chat_trace(
                http_request,
                user_id=user_id,
                turn_id=str(claim["turn_id"]),
                stage="agent_execution",
                status="unavailable",
                duration_ms=int((time.monotonic() - agent_started) * 1000),
                detail={
                    "error_type": type(exc).__name__,
                    "retryable": True,
                    "streaming": True,
                },
            )
            yield json.dumps(
                {
                    "type": "error",
                    "code": "model_unavailable",
                    "retryable": True,
                    "detail": "模型服务暂时不可用，本次操作未完成，请稍后安全重试。",
                },
                ensure_ascii=False,
            ) + "\n"
        except Exception as exc:
            await run_sync(
                runtime.chat_turn_service.fail,
                claim,
                partial_answer="".join(answer_parts),
                error=f"{type(exc).__name__}: {exc}",
            )
            await _record_chat_trace(
                http_request,
                user_id=user_id,
                turn_id=str(claim["turn_id"]),
                stage="agent_execution",
                status="failed",
                duration_ms=int(
                    (time.monotonic() - agent_started) * 1000
                ),
                detail={
                    "error_type": type(exc).__name__,
                    "streaming": True,
                },
            )
            logger.exception(
                "Streaming agent execution failed for session %s",
                request.session_id,
            )
            # 不向客户端透传内部异常详情(可能含路径/SQL/供应商错误),只返回通用文案。
            yield json.dumps(
                {"type": "error", "detail": "Agent 执行失败，请稍后重试。"},
                ensure_ascii=False,
            ) + "\n"
        finally:
            reset_conversation_context(context_token)
            reset_tool_identity(identity_token)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
